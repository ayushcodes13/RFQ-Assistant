"""Catalog repository and CSV importer."""

import csv
import io
from typing import Dict, List, Optional
from pydantic import ValidationError

from rfq_assistant.matching.normalizer import normalize_manufacturer, normalize_mpn
from rfq_assistant.schemas.models import CatalogItem


class CatalogImportError(Exception):
    """Raised when catalog file has invalid schema or structure."""
    pass


class CatalogRepository:
    """In-memory item master repository with indexed normalized MPN lookups."""

    def __init__(self):
        self._items_by_sku: Dict[str, CatalogItem] = {}
        self._items_by_normalized_mpn: Dict[str, List[CatalogItem]] = {}

    def clear(self):
        self._items_by_sku.clear()
        self._items_by_normalized_mpn.clear()

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
        """
        Imports and validates distributor catalog CSV.
        Returns validation summary: {"imported": count, "duplicates": count, "collisions": count}
        """
        text = csv_content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))

        required_cols = {"internal_sku", "manufacturer", "manufacturer_part_number", "description"}
        if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
            missing = required_cols - set(reader.fieldnames or [])
            raise CatalogImportError(f"Catalog CSV is missing required columns: {', '.join(sorted(missing))}")

        imported_count = 0
        duplicate_count = 0

        for row in reader:
            sku = (row.get("internal_sku") or "").strip()
            oem = (row.get("manufacturer") or "").strip()
            mpn = (row.get("manufacturer_part_number") or "").strip()
            desc = (row.get("description") or "").strip()

            if not sku or not mpn or not oem:
                continue

            if sku in self._items_by_sku:
                duplicate_count += 1
                continue

            list_price = None
            if row.get("list_price") and row["list_price"].strip():
                try:
                    list_price = float(row["list_price"].strip())
                except ValueError:
                    list_price = None

            stock_qty = None
            if row.get("stock_qty") and row["stock_qty"].strip():
                try:
                    stock_qty = int(float(row["stock_qty"].strip()))
                except ValueError:
                    stock_qty = None

            item = CatalogItem(
                internal_sku=sku,
                manufacturer=oem,
                manufacturer_part_number=mpn,
                description=desc,
                list_price=list_price,
                stock_qty=stock_qty,
                catalog_version=version,
            )
            self.add_item(item)
            imported_count += 1

        # Count cross-brand collisions
        collision_count = sum(
            1 for items in self._items_by_normalized_mpn.values()
            if len({normalize_manufacturer(i.manufacturer) for i in items}) > 1
        )

        return {
            "imported": imported_count,
            "duplicates": duplicate_count,
            "collisions": collision_count,
            "total_catalog_size": len(self._items_by_sku),
        }
