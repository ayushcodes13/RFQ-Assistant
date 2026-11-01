"""Deterministic quotation validator and domain models.

Keeps commercial and safety validation rules outside the LLM:
- Match status must be exact or explicitly human-approved.
- Unit prices must have authoritative source IDs and provenance.
- Quantities must be positive.
- Currencies must be explicitly defined and consistent.
"""

import hashlib
import json
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, computed_field, model_validator


class SourceRef(BaseModel):
    """Source provenance reference linking extracted values to original files."""
    file_id: str
    page: Optional[int] = None
    sheet: Optional[str] = None
    cell_range: Optional[str] = None
    text_excerpt: Optional[str] = None
    bbox: Optional[List[float]] = None


class QuoteLine(BaseModel):
    """Commercial line item in a quotation draft."""
    line_no: int
    requested_mpn: str
    requested_manufacturer: Optional[str] = None
    catalogue_part_id: Optional[str] = None
    description: Optional[str] = None
    # Keep unresolved quantities visible in a draft instead of fabricating a
    # value or raising a schema error while building the review artifact.
    quantity: Optional[Decimal] = Field(default=None, gt=0)
    stock_qty: Optional[int] = Field(default=None, ge=0)
    unit: str = "EA"
    unit_price: Optional[Decimal] = None
    currency: Optional[str] = None
    source_price_id: Optional[str] = None
    match_status: str = "unmatched"  # exact, candidate, unmatched
    requires_human_review: bool = True
    sources: List[SourceRef] = Field(default_factory=list)
    line_notes: Optional[str] = None

    @computed_field  # type: ignore[prop-decorator]  # Pydantic descriptor typing limitation
    @property
    def line_total(self) -> Optional[Decimal]:
        """Deterministic unrounded extension; never trust a model-supplied total."""
        if self.unit_price is None or self.quantity is None or not self.currency:
            return None
        return self.quantity * self.unit_price


class ProposedQuote(BaseModel):
    """Complete quotation proposal draft."""
    quote_id: str
    case_id: str
    customer_name: Optional[str] = None
    customer_reference: Optional[str] = None
    currency: Optional[str] = None
    lines: List[QuoteLine] = Field(default_factory=list)
    total_amount: Optional[Decimal] = None
    source_state_hash: Optional[str] = None  # Snapshot of RFQ rows and catalog at draft creation
    draft_hash: str = ""
    is_approved: bool = False
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    requires_human_review: bool = True
    validation_errors: List[str] = Field(default_factory=list)
    quote_proposal_status: Literal["grounded", "not_configured", "failed", "no_retrieved_prices"] = "not_configured"
    quote_proposal_warnings: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def calculate_total_when_all_prices_are_present(self):
        """Fill a missing grand total from Decimal line extensions; retain supplied totals for checking."""
        if self.total_amount is None and self.lines:
            self.total_amount = calculate_quote_total(self.lines)
        return self

    def compute_draft_hash(self) -> str:
        """Computes cryptographic digest of the draft for version-bound approvals.

        Binds to quote_id, case_id, customer_name, currency, and every material line field.
        Any modification to quantities, prices, MPNs, manufacturers, notes, or review status
        changes the hash and invalidates prior approvals.
        """
        payload = {
            "quote_id": self.quote_id,
            "case_id": self.case_id,
            "customer_name": self.customer_name,
            "currency": self.currency,
            "source_state_hash": self.source_state_hash,
            "lines": [
                {
                    "line_no": l.line_no,
                    "mpn": l.requested_mpn,
                    "manufacturer": l.requested_manufacturer,
                    "cat_id": l.catalogue_part_id,
                    "description": l.description,
                    "qty": str(l.quantity),
                    "stock_qty": l.stock_qty,
                    "unit": l.unit,
                    "price": str(l.unit_price) if l.unit_price is not None else None,
                    "currency": l.currency,
                    "source_price_id": l.source_price_id,
                    "match_status": l.match_status,
                    "requires_review": l.requires_human_review,
                    "notes": l.line_notes,
                }
                for l in self.lines
            ],
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_quote_line(line: QuoteLine) -> List[str]:
    """Validates an individual quote line against strict commercial invariants."""
    import math
    errors: List[str] = []

    if line.match_status != "exact":
        errors.append(f"Line {line.line_no}: Part '{line.requested_mpn}' has non-exact status ({line.match_status}) and requires human match approval.")

    if line.requires_human_review:
        errors.append(f"Line {line.line_no}: Part '{line.requested_mpn}' is still pending reviewer approval.")

    if line.unit_price is None:
        errors.append(f"Line {line.line_no}: No authoritative unit price for '{line.requested_mpn}'.")
    else:
        try:
            p_val = float(line.unit_price)
            if math.isnan(p_val) or math.isinf(p_val):
                errors.append(f"Line {line.line_no}: Unit price cannot be NaN or Infinite.")
            elif line.unit_price < Decimal("0"):
                errors.append(f"Line {line.line_no}: Unit price cannot be negative.")
        except (ValueError, TypeError):
            errors.append(f"Line {line.line_no}: Malformed unit price '{line.unit_price}'.")

    if line.source_price_id is None:
        errors.append(f"Line {line.line_no}: Price has no authoritative source ID.")

    try:
        if line.quantity is None:
            errors.append(f"Line {line.line_no}: Quantity is missing and needs reviewer confirmation.")
            return errors
        q_val = float(line.quantity)
        if math.isnan(q_val) or math.isinf(q_val):
            errors.append(f"Line {line.line_no}: Quantity cannot be NaN or Infinite.")
        elif line.quantity <= Decimal("0"):
            errors.append(f"Line {line.line_no}: Quantity must be greater than zero.")
        elif line.stock_qty is not None and line.quantity > Decimal(line.stock_qty):
            errors.append(
                f"Line {line.line_no}: Requested quantity {line.quantity} exceeds catalog stock {line.stock_qty}; confirm availability before preparing a quote."
            )
    except (ValueError, TypeError):
        errors.append(f"Line {line.line_no}: Malformed quantity '{line.quantity}'.")

    if not line.currency:
        errors.append(f"Line {line.line_no}: Currency is missing.")

    return errors


def validate_proposed_quote(quote: ProposedQuote) -> List[str]:
    """Validates entire proposed quote draft before allowing approval or export."""
    errors: List[str] = []

    if not quote.lines:
        errors.append("Quotation draft contains no line items.")

    if quote.quote_proposal_status == "failed":
        errors.append("The evidence-bounded quote proposal stage failed. Retry it before approval.")

    currencies = set()
    for line in quote.lines:
        line_errs = validate_quote_line(line)
        errors.extend(line_errs)
        if line.currency:
            currencies.add(line.currency)

    if len(currencies) > 1:
        errors.append(f"Mixed currencies detected ({', '.join(currencies)}). Commercial policy requires unified currency.")

    calculated = calculate_quote_total(quote.lines)
    if calculated is not None:
        if quote.total_amount is None:
            errors.append("Grand total is missing; deterministic recalculation is required.")
        elif quote.total_amount != calculated:
            errors.append(
                f"Grand total mismatch: supplied {quote.total_amount}, calculated {calculated}."
            )

    return errors


def calculate_quote_total(lines: List[QuoteLine]) -> Optional[Decimal]:
    """Return a total only when every line has a price, quantity, and one known currency."""
    if not lines:
        return None
    currencies = {line.currency for line in lines}
    if None in currencies or "" in currencies or len(currencies) != 1:
        return None
    total = Decimal("0")
    for line in lines:
        if line.unit_price is None or line.quantity is None:
            return None
        total += line.quantity * line.unit_price
    return total

