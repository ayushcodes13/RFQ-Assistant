"""ERPNext reference domain model and DocType schema mapping.

Maps RFQ cases, supplier quotations, and approved customer quotations
into ERPNext standard Frappe DocTypes without copying GPL-3.0 code.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from rfq_assistant.quotation.validate import ProposedQuote, QuoteLine


class ERPNextQuotationItem(BaseModel):
    """ERPNext 'Quotation Item' child DocType."""
    item_code: str
    item_name: Optional[str] = None
    description: Optional[str] = None
    qty: float
    uom: str = "Nos"
    rate: float
    amount: float
    stock_qty: float = 0.0


class ERPNextQuotation(BaseModel):
    """ERPNext 'Quotation' parent DocType for sales quotations."""
    doctype: str = "Quotation"
    party_name: str  # Customer
    transaction_date: str
    order_type: str = "Sales"
    currency: str = "USD"
    items: List[ERPNextQuotationItem] = Field(default_factory=list)
    total: float = 0.0
    status: str = "Draft"  # Draft, Submitted, Cancelled
    tc_name: Optional[str] = None  # Terms and Conditions
    remarks: Optional[str] = None


def map_proposed_quote_to_erpnext(quote: ProposedQuote) -> Dict[str, Any]:
    """Maps an approved ProposedQuote into an ERPNext Quotation DocType payload."""
    items: List[ERPNextQuotationItem] = []
    total = 0.0

    for line in quote.lines:
        if line.unit_price is None:
            raise ValueError("An ERPNext quotation item requires an authoritative unit price.")
        if line.quantity is None:
            raise ValueError("An ERPNext quotation item requires a confirmed quantity.")
        rate = float(line.unit_price)
        qty = float(line.quantity)
        amount = rate * qty
        total += amount

        items.append(
            ERPNextQuotationItem(
                item_code=line.catalogue_part_id or line.requested_mpn,
                item_name=line.requested_mpn,
                description=line.description or f"Part {line.requested_mpn}",
                qty=qty,
                uom=line.unit if line.unit != "EA" else "Nos",
                rate=rate,
                amount=amount,
            )
        )

    erpnext_quote = ERPNextQuotation(
        party_name=quote.customer_name or "Standard Commercial Prospect",
        transaction_date=quote.approved_at[:10] if quote.approved_at else "2026-10-27",
        currency=quote.currency,
        items=items,
        total=total,
        status="Draft" if not quote.is_approved else "Submitted",
        remarks=f"RFQ Assistant Quote #{quote.quote_id} (Digest: {quote.draft_hash[:8]})",
    )
    return erpnext_quote.model_dump()
