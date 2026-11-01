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
    unit: str = "EA"
    unit_price: Optional[Decimal] = None
    currency: Optional[str] = "USD"
    source_price_id: Optional[str] = None
    match_status: str = "unmatched"  # exact, candidate, unmatched
    requires_human_review: bool = True
    sources: List[SourceRef] = Field(default_factory=list)
    line_notes: Optional[str] = None

    @computed_field
    @property
    def line_total(self) -> Optional[Decimal]:
        """Deterministic unrounded extension; never trust a model-supplied total."""
        if self.unit_price is None or self.quantity is None:
            return None
        return self.quantity * self.unit_price


class ProposedQuote(BaseModel):
    """Complete quotation proposal draft."""
    quote_id: str
    case_id: str
    customer_name: Optional[str] = None
    customer_reference: Optional[str] = None
    currency: str = "USD"
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
        if self.total_amount is None and self.lines and all(
            line.unit_price is not None and line.quantity is not None for line in self.lines
        ):
            self.total_amount = sum(
                (line.quantity * line.unit_price for line in self.lines),
                start=Decimal("0"),
            )
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
    """Return a Decimal total only when every line has quantity and authoritative price."""
    if not lines or any(line.unit_price is None or line.quantity is None for line in lines):
        return None
    return sum((line.quantity * line.unit_price for line in lines), start=Decimal("0"))

