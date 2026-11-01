"""Catalog repository and CSV importer."""

import csv
import io
import math
import hashlib
import json
import re
import threading
from typing import Dict, List, Optional
from pydantic import ValidationError

from rfq_assistant.matching.normalizer import normalize_manufacturer, normalize_mpn
from rfq_assistant.schemas.models import CatalogItem
from rfq_assistant.persistence import StateStore


class CatalogImportError(Exception):
    """Raised when catalog file has invalid schema or structure."""
    pass


class CatalogRepository:
    """Indexed item master with optional durable SQLite backing."""

    def __init__(self, state_store: Optional[StateStore] = None):
        self.state_store = state_store
        self._lock = threading.RLock()
        self._items_by_sku: Dict[str, CatalogItem] = {}
        self._items_by_normalized_mpn: Dict[str, List[CatalogItem]] = {}
        if self.state_store:
            for payload in self.state_store.load_catalog():
                self.add_item(CatalogItem.model_validate(payload))

    def clear(self):
        with self._lock:
            if self.state_store:
                self.state_store.delete_catalog()
            self._items_by_sku.clear()
            self._items_by_normalized_mpn.clear()

    def upsert_item(self, item: CatalogItem) -> str:
        """Apply one human-approved item and version the complete active snapshot."""
        with self._lock:
            next_items = dict(self._items_by_sku)
            next_items[item.internal_sku] = item
            canonical = [
                value.model_dump(mode="json", exclude={"catalog_version"})
                for _, value in sorted(next_items.items())
            ]
            version = "sha256:" + hashlib.sha256(
                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            versioned = [
                value.model_copy(update={"catalog_version": version})
                for _, value in sorted(next_items.items())
            ]
            if self.state_store:
                self.state_store.replace_catalog(versioned)
            self._replace_indexes(versioned)
            return version

    def add_item(self, item: CatalogItem):
        with self._lock:
            self._items_by_sku[item.internal_sku] = item
            norm_mpn = normalize_mpn(item.manufacturer_part_number)
            if norm_mpn:
                if norm_mpn not in self._items_by_normalized_mpn:
                    self._items_by_normalized_mpn[norm_mpn] = []
                self._items_by_normalized_mpn[norm_mpn].append(item)

    def get_by_sku(self, sku: str) -> Optional[CatalogItem]:
        with self._lock:
            return self._items_by_sku.get(sku)

    def get_by_normalized_mpn(self, norm_mpn: str) -> List[CatalogItem]:
        with self._lock:
            return list(self._items_by_normalized_mpn.get(norm_mpn, []))

    def list_all(self) -> List[CatalogItem]:
        with self._lock:
            return list(self._items_by_sku.values())

    def snapshot(self) -> "CatalogRepository":
        """Return an isolated read-only-by-convention view of one active catalog state."""
        with self._lock:
            snapshot = CatalogRepository()
            snapshot._replace_indexes(list(self._items_by_sku.values()))
            return snapshot

    def count(self) -> int:
        with self._lock:
            return len(self._items_by_sku)

    def import_csv(
        self, csv_content: bytes, version: str = "v1"
    ) -> Dict[str, int | str | None]:
        """Add validated rows to the existing catalog (legacy additive behavior)."""
        with self._lock:
            return self._import_csv(csv_content, version, replace_snapshot=False)

    def replace_csv(self, csv_content: bytes) -> Dict[str, int | str | None]:
        """Atomically replace the active item-master snapshot from a complete CSV."""
        version = f"sha256:{hashlib.sha256(csv_content).hexdigest()}"
        with self._lock:
            return self._import_csv(csv_content, version, replace_snapshot=True)

    def _import_csv(
        self, csv_content: bytes, version: str, *, replace_snapshot: bool
    ) -> Dict[str, int | str | None]:
        """Validate every row before changing the item master.

        Failures are all-or-nothing: never leave half an imported catalog or
        silently erase a malformed OEM, MPN, price or stock quantity.
        """
        from decimal import Decimal, InvalidOperation

        text = csv_content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text), restkey="__extra_columns__")
        required = {"internal_sku", "manufacturer", "manufacturer_part_number", "description"}
        columns = reader.fieldnames or []
        missing = required.difference(columns)
        if missing:
            raise CatalogImportError(
                f"Catalog CSV is missing required columns: {', '.join(sorted(missing))}"
            )
        if len(columns) != len(set(columns)):
            raise CatalogImportError("Catalog CSV has duplicate column headers.")

        staged: List[CatalogItem] = []
        seen_skus = set()
        duplicate_count = 0

        for row_num, row in enumerate(reader, start=2):
            if row.get("__extra_columns__"):
                raise CatalogImportError(f"Catalog row {row_num} has more fields than its header.")
            if all(not (value or "").strip() for key, value in row.items() if key != "__extra_columns__"):
                continue

            sku = (row.get("internal_sku") or "").strip()
            oem = (row.get("manufacturer") or "").strip()
            mpn = (row.get("manufacturer_part_number") or "").strip()
            desc = (row.get("description") or "").strip()
            if not sku or not oem or not mpn:
                raise CatalogImportError(
                    f"Catalog row {row_num} requires a nonempty SKU, manufacturer and MPN."
                )
            if sku in seen_skus:
                raise CatalogImportError(
                    f"Catalog row {row_num} repeats SKU '{sku}' in the uploaded file."
                )
            seen_skus.add(sku)

            price_raw = (row.get("list_price") or "").strip()
            list_price = None
            if price_raw:
                try:
                    price = Decimal(price_raw)
                except InvalidOperation:
                    raise CatalogImportError(f"Catalog row {row_num} has invalid list_price.")
                if not price.is_finite() or price < 0:
                    raise CatalogImportError(
                        f"Catalog row {row_num} requires a finite nonnegative list_price."
                    )
                list_price = float(price)
                if not math.isfinite(list_price):
                    raise CatalogImportError(f"Catalog row {row_num} has an overflowing list_price.")

            stock_raw = (row.get("stock_qty") or "").strip()
            stock_qty = None
            if stock_raw:
                try:
                    stock = Decimal(stock_raw)
                except InvalidOperation:
                    raise CatalogImportError(f"Catalog row {row_num} has invalid stock_qty.")
                if not stock.is_finite() or stock < 0 or stock != stock.to_integral_value():
                    raise CatalogImportError(
                        f"Catalog row {row_num} requires a nonnegative whole-number stock_qty."
                    )
                stock_qty = int(stock)

            currency = (row.get("currency") or "").strip().upper() or None
            if currency and not re.fullmatch(r"[A-Z]{3}", currency):
                raise CatalogImportError(f"Catalog row {row_num} has invalid currency.")

            try:
                item = CatalogItem(
                    internal_sku=sku,
                    manufacturer=oem,
                    manufacturer_part_number=mpn,
                    description=desc,
                    list_price=list_price,
                    currency=currency,
                    stock_qty=stock_qty,
                    catalog_version=version,
                )
            except ValidationError as exc:
                raise CatalogImportError(f"Catalog row {row_num} is invalid: {exc}") from exc

            if not replace_snapshot and sku in self._items_by_sku:
                duplicate_count += 1
            else:
                staged.append(item)

        if not staged and (replace_snapshot or duplicate_count == 0):
            raise CatalogImportError("Catalog CSV contains no importable item rows.")

        # Persist first, then atomically publish the new in-memory indexes. If
        # storage fails, readers continue to observe the prior complete snapshot.
        next_items = staged if replace_snapshot else [*self._items_by_sku.values(), *staged]
        if self.state_store:
            self.state_store.replace_catalog(next_items)
        self._replace_indexes(next_items)

        collision_count = sum(
            1 for items in self._items_by_normalized_mpn.values()
            if len({normalize_manufacturer(i.manufacturer) for i in items}) > 1
        )
        return {
            "imported": len(staged),
            "duplicates": duplicate_count,
            "collisions": collision_count,
            "total_catalog_size": len(self._items_by_sku),
            "catalog_version": version if replace_snapshot else self.active_version,
        }

    def _replace_indexes(self, items: List[CatalogItem]) -> None:
        by_sku = {item.internal_sku: item for item in items}
        by_mpn: Dict[str, List[CatalogItem]] = {}
        for item in items:
            norm_mpn = normalize_mpn(item.manufacturer_part_number)
            if norm_mpn:
                by_mpn.setdefault(norm_mpn, []).append(item)
        self._items_by_sku = by_sku
        self._items_by_normalized_mpn = by_mpn

    @property
    def active_version(self) -> Optional[str]:
        with self._lock:
            versions = {item.catalog_version for item in self._items_by_sku.values()}
            return next(iter(versions)) if len(versions) == 1 else None
