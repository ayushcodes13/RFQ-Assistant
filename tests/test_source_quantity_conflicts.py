"""End-to-end safeguards for contradictory quantities across source regions."""

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.exports.email_draft import generate_unsent_email_draft
from rfq_assistant.ingestion import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.quotation.line_rules import blocking_line_issues
from rfq_assistant.schemas.enums import ReviewDecision
from rfq_assistant.schemas.models import RFQLineItemUpdate


def test_conflicting_quantities_are_visible_blocking_and_correctable(tmp_path):
    manager = CaseManager(
        catalog=CatalogRepository(),
        storage=DocumentStorage(tmp_path / "files"),
    )
    case = manager.create_case_from_text(
        "Email: Please quote 20 pcs Schneider Electric LC1D09BD\n"
        "Attachment row: 200 pcs Schneider Electric LC1D09BD",
        title="Synthetic conflicting source quantities",
    )

    lines = manager.get_lines(case.case_id)
    sibling_version = lines[1].version
    assert len(lines) == 2
    assert [line.quantity for line in lines] == [20, 200]
    assert [line.source_locator.row_number for line in lines] == [1, 2]
    for line in lines:
        warning = next(
            warning
            for warning in line.extraction_warnings
            if warning.code == "SOURCE_QUANTITY_CONFLICT"
        )
        assert warning.severity == "error"
        assert "line 1: 20" in warning.message
        assert "line 2: 200" in warning.message
        assert any(
            "unresolved extraction error (SOURCE_QUANTITY_CONFLICT)" in issue
            for issue in blocking_line_issues(line, manager.catalog)
        )

    assert case.status.value == "NEEDS_REVIEW"
    draft = generate_unsent_email_draft(case, lines)
    assert "provided sources appear to give different quantities" in draft

    corrected = manager.update_line(
        case.case_id,
        lines[0].line_id,
        RFQLineItemUpdate(
            expected_version=lines[0].version,
            quantity=200,
            review_decision=ReviewDecision.APPROVED,
            reviewer_notes="Confirmed against the attached source.",
            actor="Synthetic Reviewer",
        ),
    )

    assert corrected is not None
    assert corrected.quantity == 200
    assert corrected.raw_text.startswith("Email:")
    assert corrected.field_provenance["quantity"].origin.value == "HUMAN"
    assert lines[1].version == sibling_version + 1
    assert any(
        event.line_id == corrected.line_id
        and event.action.value == "LINE_EDITED"
        and event.field_name == "quantity"
        for event in manager.get_audit_trail(case.case_id)
    )
    assert all(
        warning.code != "SOURCE_QUANTITY_CONFLICT"
        for line in manager.get_lines(case.case_id)
        for warning in line.extraction_warnings
    )
