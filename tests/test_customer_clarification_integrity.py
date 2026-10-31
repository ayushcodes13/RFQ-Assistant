"""Customer clarification draft safety tests using synthetic RFQ line states."""

from rfq_assistant.exports.email_draft import generate_unsent_email_draft
from rfq_assistant.schemas.enums import MatchStatus, ReviewDecision, SourceType
from rfq_assistant.schemas.models import ExtractionWarning, RFQCase, RFQLineItem, SourceLocator


def make_case():
    return RFQCase(case_id="RFQ-SYN-123", title="Synthetic buyer sample", source_type=SourceType.EMAIL_TEXT)


def make_line(*, review=ReviewDecision.PENDING, match=MatchStatus.EXACT_MATCH,
              mpn="LC1D09BD", quantity=10.0, warnings=None, line_number=1,
              raw_text="10 pcs Schneider Electric LC1D09BD"):
    return RFQLineItem(
        line_id="syn-1",
        case_id="RFQ-SYN-123",
        line_number=line_number,
        raw_text=raw_text,
        source_locator=SourceLocator(file_name="synthetic.txt", row_number=1),
        requested_manufacturer="Schneider Electric",
        requested_mpn=mpn,
        quantity=quantity,
        review_decision=review,
        match_status=match,
        extraction_warnings=warnings or [],
    )


def test_pending_exact_match_is_not_a_customer_clarification():
    email = generate_unsent_email_draft(make_case(), [make_line()])
    assert "No customer action is required" in email
    assert "Before finalizing your quote" not in email
    assert "Our team has reviewed the following" not in email


def test_approved_ambiguous_part_is_never_reported_as_verified():
    email = generate_unsent_email_draft(make_case(), [
        make_line(review=ReviewDecision.APPROVED, match=MatchStatus.COLLISION)
    ])
    assert "Before finalizing your quote" in email
    assert "confirm the exact manufacturer" in email
    assert "Our team has reviewed the following" not in email


def test_approved_critical_source_contradiction_requires_clarification():
    email = generate_unsent_email_draft(make_case(), [
        make_line(
            review=ReviewDecision.APPROVED,
            match=MatchStatus.MANUAL_OVERRIDE,
            warnings=[ExtractionWarning(
                code="CONTRADICTION", severity="error", message="Conflicting manufacturer",
            )],
        ),
    ])
    assert "contradictory source details" in email
    assert "no substitute has been approved" in email
    assert "Our team has reviewed the following" not in email


def test_missing_quantity_requires_specific_customer_question():
    email = generate_unsent_email_draft(make_case(), [make_line(quantity=None)])
    assert "Quantity was missing from the request" in email


def test_confirmed_exact_match_only_is_listed_as_reviewed():
    email = generate_unsent_email_draft(make_case(), [
        make_line(review=ReviewDecision.APPROVED)
    ])
    assert "Our team has reviewed the following requested items" in email
    assert "LC1D09BD" in email
    assert "Before finalizing your quote" not in email
    assert "NO AUTOMATIC OUTBOUND DISPATCH" in email


def test_rejected_item_is_not_presented_as_verified_or_customer_question():
    email = generate_unsent_email_draft(make_case(), [
        make_line(review=ReviewDecision.REJECTED, match=MatchStatus.NO_MATCH)
    ])
    assert "Our team has reviewed the following" not in email
    assert "Before finalizing your quote" not in email


def test_email_draft_preserves_original_line_numbers_across_sections():
    approved = make_line(review=ReviewDecision.APPROVED, line_number=18)
    clarification = make_line(
        match=MatchStatus.NO_MATCH,
        mpn=None,
        quantity=None,
        line_number=1,
        raw_text=(
            "1 | 2 units sensor from last time request reference "
            "supersupercalifragilisticlongidentifierXYZ, manufacturer unknown"
        ),
    )
    approved.line_id = "syn-approved-18"
    approved.source_locator.row_number = 18
    clarification.line_id = "syn-clarification-1"

    email = generate_unsent_email_draft(make_case(), [approved, clarification])

    assert "  18. 10 EA - Schneider Electric (Part: LC1D09BD)" in email
    assert "  1. 10 EA - Schneider Electric (Part: LC1D09BD)" not in email
    assert "  * Line 1 — 2 units sensor from last time request reference…:" in email
    assert "Line 1 — 1 |" not in email
    assert "supersupercalifragilisticlongidentifierXYZ" not in email
    assert "NO AUTOMATIC OUTBOUND DISPATCH" in email
