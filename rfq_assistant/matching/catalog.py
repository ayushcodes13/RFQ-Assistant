"""Catalog repository and CSV importer."""

import csv
import io
import math
from typing import Dict, List, Optional
from pydantic import ValidationError

from rfq_assistant.matching.normalizer import normalize_manufacturer, normalize_mpn
from rfq_assistant.schemas.models import CatalogItem
from rfq_assistant.persistence import SQLiteStateStore


class CatalogImportError(Exception):
    """Raised when catalog file has invalid schema or structure."""
    pass


class CatalogRepository:
    """Indexed item master with optional durable SQLite backing."""

    def __init__(self, state_store: Optional[SQLiteStateStore] = None):
        self.state_store = state_store
        self._items_by_sku: Dict[str, CatalogItem] = {}
        self._items_by_normalized_mpn: Dict[str, List[CatalogItem]] = {}
        if self.state_store:
            for payload in self.state_store.load_catalog():
                self.add_item(CatalogItem.model_validate(payload))

    def clear(self):
        self._items_by_sku.clear()
        self._items_by_normalized_mpn.clear()
        if self.state_store:
            self.state_store.delete_catalog()

    def add_item(self, item: CatalogItem):
        self._items_by_sku[item.internal_sku] = item
        norm_mpn = normalize_mpn(item.manufacturer_part_number)
        if norm_mpn:
            if norm_mpn not in self._items_by_normalized_mpn:
                self._items_by_normalized_mpn[norm_mpn] = []
            self._items_by_normalized_mpn[norm_mpn].append(item)

    def get_by_sku(self, sku: str) -> Optional[CatalogItem]:
        return self._items_by_sku.get(sku)

    def get_by_normalized_mpn(self, norm_mpn: str) -> List[CatalogItem]:
        return self._items_by_normalized_mpn.get(norm_mpn, [])

    def list_all(self) -> List[CatalogItem]:
        return list(self._items_by_sku.values())

    def count(self) -> int:
        return len(self._items_by_sku)

    def import_csv(self, csv_content: bytes, version: str = "v1") -> Dict[str, int]:
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

            try:
                item = CatalogItem(
                    internal_sku=sku,
                    manufacturer=oem,
                    manufacturer_part_number=mpn,
                    description=desc,
                    list_price=list_price,
                    stock_qty=stock_qty,
                    catalog_version=version,
                )
            except ValidationError as exc:
                raise CatalogImportError(f"Catalog row {row_num} is invalid: {exc}") from exc

            if sku in self._items_by_sku:
                duplicate_count += 1
            else:
                staged.append(item)

        if not staged and duplicate_count == 0:
            raise CatalogImportError("Catalog CSV contains no importable item rows.")

        # Commit only after every input row has passed validation.
        for item in staged:
            self.add_item(item)
        if self.state_store:
            self.state_store.replace_catalog(self.list_all())

        collision_count = sum(
            1 for items in self._items_by_normalized_mpn.values()
            if len({normalize_manufacturer(i.manufacturer) for i in items}) > 1
        )
        return {
            "imported": len(staged),
            "duplicates": duplicate_count,
            "collisions": collision_count,
            "total_catalog_size": len(self._items_by_sku),
        }
