"""InvenTree domain models and reference schema integration.

Provides mapping between RFQ Assistant internal representations and InvenTree's
parts, supplier parts, BOM items, and stock models.
"""

from decimal import Decimal
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from rfq_assistant.quotation.validate import QuoteLine
from rfq_assistant.schemas.models import CatalogItem


class InvenTreePart(BaseModel):
    """InvenTree internal Part representation."""
    pk: Optional[int] = None
    name: str
    IPN: Optional[str] = None  # Internal Part Number
    description: Optional[str] = None
    category: Optional[int] = None
    default_location: Optional[int] = None
    units: str = "EA"
    active: bool = True
    virtual: bool = False


class InvenTreeSupplierPart(BaseModel):
    """InvenTree SupplierPart linking an external MPN/OEM to an internal Part."""
    pk: Optional[int] = None
    part: int  # Link to InvenTreePart pk
    supplier: int
    SKU: str
    manufacturer: Optional[str] = None
    MPN: Optional[str] = None  # Manufacturer Part Number
    packaging: Optional[str] = None
    pack_quantity: Decimal = Decimal("1.0")


def map_catalog_item_to_inventree(item: CatalogItem, part_pk: int = 1, supplier_pk: int = 1) -> Dict[str, Any]:
    """Maps a distributor catalog item into InvenTree Part & SupplierPart records."""
    part = InvenTreePart(
        pk=part_pk,
        name=item.manufacturer_part_number,
        IPN=item.internal_sku,
        description=item.description,
        units="EA",
    )
    supplier_part = InvenTreeSupplierPart(
        part=part_pk,
        supplier=supplier_pk,
        SKU=item.internal_sku,
        manufacturer=item.manufacturer,
        MPN=item.manufacturer_part_number,
    )
    return {
        "part": part.model_dump(),
        "supplier_part": supplier_part.model_dump(),
    }


def map_quote_line_to_inventree_bom(line: QuoteLine, bom_pk: int = 1, parent_part_pk: int = 100) -> Dict[str, Any]:
    """Maps a quotation line into an InvenTree BOM item."""
    return {
        "pk": bom_pk,
        "part": parent_part_pk,
        "sub_part": line.catalogue_part_id or 0,
        "quantity": float(line.quantity),
        "reference": f"Line {line.line_no} - {line.requested_mpn}",
        "note": line.line_notes or "",
    }
