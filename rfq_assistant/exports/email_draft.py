"""Generator for unsent customer clarification and quotation reply drafts."""

from typing import List, Optional
from rfq_assistant.schemas.enums import MatchStatus, ReviewDecision
from rfq_assistant.schemas.models import RFQCase, RFQLineItem


def generate_unsent_email_draft(case: RFQCase, lines: List[RFQLineItem]) -> str:
    """
    Constructs a polite, structured email draft summarizing approved items and asking specific
    clarification questions for ambiguous or unquoted items.
    NEVER automatically sends emails. Prominently labeled as UNSENT DRAFT.
    """
    approved_lines = [l for l in lines if l.review_decision == ReviewDecision.APPROVED]
    clarification_lines = [
        l for l in lines
        if l.review_decision in (ReviewDecision.NEEDS_CLARIFICATION, ReviewDecision.PENDING)
        or l.match_status in (MatchStatus.COLLISION, MatchStatus.NO_MATCH)
        or l.quantity is None
    ]

    subject = f"Quote Preparation Update: RFQ #{case.case_id}"
    if case.customer_label:
        subject += f" - {case.customer_label}"

    body_lines = [
        "==================================================================",
        "*** UNSENT DRAFT REPLY — HUMAN REVIEW REQUIRED BEFORE SENDING ***",
        "*** NO AUTOMATIC OUTBOUND DISPATCH — STAFF SENDS MANUALLY     ***",
        "==================================================================",
        f"Subject: {subject}",
        "",
        "Hi there,",
        "",
        f"Thank you for your quotation request (#{case.case_id}). We have reviewed your line items.",
        "",
    ]

    if approved_lines:
        body_lines.append("We have verified the following items and are preparing your quotation:")
        for idx, item in enumerate(approved_lines, start=1):
            qty_str = f"{item.quantity:g} {item.unit}" if item.quantity is not None else "Qty TBD"
            oem_str = item.requested_manufacturer or "Brand not specified"
            mpn_str = item.requested_mpn or "Part not specified"
            body_lines.append(f"  {idx}. {qty_str} - {oem_str} (Part: {mpn_str})")
        body_lines.append("")

    if clarification_lines:
        body_lines.append("Before finalizing your quote, could you please help clarify the following item(s)?")
        for idx, item in enumerate(clarification_lines, start=1):
            notes = []
            if item.quantity is None:
                notes.append("Quantity was missing from the request — please specify your required quantity and packaging.")
            if item.match_status == MatchStatus.COLLISION:
                candidates_oem = {c.catalog_item.manufacturer for c in item.candidates}
                if candidates_oem:
                    notes.append(
                        f"Part number '{item.requested_mpn}' is supplied by multiple manufacturers ({', '.join(sorted(candidates_oem))}). "
                        "Please confirm your preferred brand or equipment specification."
                    )
                else:
                    notes.append(f"Multiple options exist for part '{item.requested_mpn}'. Please confirm exact suffix or manufacturer.")
            elif item.match_status == MatchStatus.NO_MATCH:
                notes.append(
                    f"Part number '{item.requested_mpn or item.description}' is not currently in our standard catalog. "
                    "Could you send a datasheet, label photo, or acceptable approved alternate?"
                )
            elif item.review_decision == ReviewDecision.NEEDS_CLARIFICATION and item.reviewer_notes:
                notes.append(item.reviewer_notes)

            clarif_text = "; ".join(notes) if notes else "Please confirm required specifications."
            body_lines.append(f"  * Line {item.line_number} ({item.raw_text[:60]}...): {clarif_text}")
        body_lines.append("")

    body_lines.extend([
        "We will send over the formal quotation as soon as these details are confirmed.",
        "",
        "Best regards,",
        "Inside Sales & Quotations Team",
        "",
        "------------------------------------------------------------------",
        "NOTICE: This draft was prepared with RFQ Assistant. Commercial terms,",
        "pricing, and technical verification remain the responsibility of staff.",
        "------------------------------------------------------------------",
    ])

    return "\n".join(body_lines)
