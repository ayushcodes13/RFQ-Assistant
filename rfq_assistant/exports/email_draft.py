"""Generate an unsent customer clarification draft from verified RFQ decisions."""

import math
from typing import List

from rfq_assistant.schemas.enums import MatchStatus, ReviewDecision
from rfq_assistant.schemas.models import RFQCase, RFQLineItem


def _needs_customer_clarification(line: RFQLineItem) -> bool:
    """Distinguish true customer ambiguities from an operator's pending review."""
    if line.review_decision == ReviewDecision.REJECTED:
        return False
    return (
        line.review_decision == ReviewDecision.NEEDS_CLARIFICATION
        or line.match_status in (MatchStatus.COLLISION, MatchStatus.NO_MATCH)
        or not line.requested_mpn
        or not line.unit
        or line.quantity is None
        or not math.isfinite(line.quantity)
        or line.quantity <= 0
        or any(w.severity.lower() == "error" for w in line.extraction_warnings)
    )


def _source_excerpt(text: str, line_number: int, limit: int = 60) -> str:
    """Return a compact excerpt without repeating the row number or cutting a word."""
    normalized = " ".join(text.split())
    if "|" in normalized:
        source_number, remaining = normalized.split("|", 1)
        if source_number.strip() == str(line_number):
            normalized = remaining.strip()
    if len(normalized) <= limit:
        return normalized

    words = []
    for word in normalized.split(" "):
        candidate = " ".join((*words, word))
        if len(candidate) + 1 > limit:  # Reserve one character for the ellipsis.
            break
        words.append(word)
    return f"{' '.join(words)}…" if words else "…"


def generate_unsent_email_draft(case: RFQCase, lines: List[RFQLineItem]) -> str:
    """Create a human-editable draft, without approval or outbound email effects.

    Important: an APPROVED status does not make a collision, missing part or
    unresolved high-severity source contradiction commercially verified.
    """
    clarification = [line for line in lines if _needs_customer_clarification(line)]
    approved = [
        line for line in lines
        if line.review_decision == ReviewDecision.APPROVED
        and not _needs_customer_clarification(line)
    ]
    internally_pending = [
        line for line in lines
        if line.review_decision == ReviewDecision.PENDING
        and not _needs_customer_clarification(line)
    ]

    customer_label = " ".join((case.customer_label or "").splitlines()).strip()
    subject = f"Quote Preparation Update: RFQ #{case.case_id}"
    if customer_label:
        subject += f" - {customer_label}"

    body = [
        "==================================================================",
        "*** UNSENT DRAFT REPLY — HUMAN REVIEW REQUIRED BEFORE SENDING ***",
        "*** NO AUTOMATIC OUTBOUND DISPATCH — STAFF SENDS MANUALLY     ***",
        "==================================================================",
        f"Subject: {subject}",
        "",
        "Hi there,",
        "",
        f"Thank you for your quotation request (#{case.case_id}). We are preparing a reviewed worksheet.",
        "",
    ]

    if approved:
        body.append("Our team has reviewed the following requested items for quote preparation:")
        for line in approved:
            quantity = f"{line.quantity:g} {line.unit or 'EA'}"
            oem = line.requested_manufacturer or "Manufacturer not specified"
            body.append(f"  {line.line_number}. {quantity} - {oem} (Part: {line.requested_mpn})")
        body.append("")

    if clarification:
        body.append("Before finalizing your quote, could you please help clarify the following item(s)?")
        for line in clarification:
            questions: List[str] = []
            if line.quantity is None:
                questions.append(
                    "Quantity was missing from the request — please specify your required quantity and packaging."
                )
            elif not math.isfinite(line.quantity) or line.quantity <= 0:
                questions.append("Please confirm a valid positive quantity and packaging.")

            if not line.requested_mpn:
                questions.append("Please provide the exact manufacturer part number or a datasheet/photo.")
            elif line.match_status == MatchStatus.COLLISION:
                manufacturers = sorted({c.catalog_item.manufacturer for c in line.candidates})
                if len(manufacturers) > 1:
                    questions.append(
                        f"Part number '{line.requested_mpn}' appears under different manufacturers "
                        f"({', '.join(manufacturers)}). Please confirm the exact brand and suffix."
                    )
                elif manufacturers:
                    questions.append(
                        f"Please confirm the manufacturer for part '{line.requested_mpn}' "
                        f"(catalog candidate: {manufacturers[0]})."
                    )
                else:
                    questions.append("Please confirm the exact manufacturer and part-number suffix.")
            elif line.match_status == MatchStatus.NO_MATCH:
                questions.append(
                    f"Part number '{line.requested_mpn}' is not in our current item master. "
                    "Could you provide a datasheet or verify the full manufacturer and suffix?"
                )

            if not line.unit:
                questions.append("Please confirm the requested unit or packaging.")
            quantity_conflicts = [
                warning for warning in line.extraction_warnings
                if warning.code == "SOURCE_QUANTITY_CONFLICT"
            ]
            if quantity_conflicts:
                questions.append(
                    "The provided sources appear to give different quantities for this item. "
                    "Please confirm the required quantity."
                )
            elif any(w.severity.lower() == "error" for w in line.extraction_warnings):
                questions.append(
                    "Our review found contradictory source details. Please confirm the requested "
                    "manufacturer and part number; no substitute has been approved."
                )
            if line.review_decision == ReviewDecision.NEEDS_CLARIFICATION and line.reviewer_notes:
                questions.append(line.reviewer_notes)

            question_text = "; ".join(questions) or "Please confirm the requested specifications."
            original = _source_excerpt(line.raw_text, line.line_number)
            source_context = f" — {original}" if original else ""
            body.append(f"  * Line {line.line_number}{source_context}: {question_text}")
        body.append("")

    if internally_pending:
        body.append(
            "Other requested items are still undergoing internal verification. "
            "No customer action is required for those lines at this stage."
        )
        body.append("")

    body.extend([
        "We will prepare the formal quotation after the required confirmations and internal review.",
        "",
        "Best regards,",
        "Inside Sales & Quotations Team",
        "",
        "------------------------------------------------------------------",
        "NOTICE: This draft was prepared with RFQ Assistant. Commercial terms,",
        "pricing, and technical verification remain the responsibility of staff.",
        "------------------------------------------------------------------",
    ])
    return "\n".join(body)
