"""Adversarial reproduction tests for review integrity and quote validation.

Verifies:
1. An approved RFQ line edited from quantity 10 to 1,000 revokes prior approval.
2. A manufacturer, MPN, selected SKU, description, unit, or commercial note changed after approval revokes approval.
3. A quote cannot be approved while underlying RFQ lines are still pending.
4. Material modification to any line changes the quote approval hash.
5. Missing, zero, negative, NaN, infinite, or malformed quantities and prices are rejected.
6. Manually selected SKU that contradicts requested OEM surfaces an explicit contradiction warning.
"""

from decimal import Decimal
import pytest

from rfq_assistant.agents.tools import ApprovalGateError, QuotationCommercialService
from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.quotation.validate import (
    ProposedQuote,
    QuoteLine,
    validate_proposed_quote,
    validate_quote_line,
)
from rfq_assistant.schemas.enums import ReviewDecision
from rfq_assistant.schemas.models import CatalogItem, RFQLineItemUpdate


@pytest.fixture
def catalog_repo():
    repo = CatalogRepository()
    repo.add_item(
        CatalogItem(
            internal_sku="SKU-SCH-001",
            manufacturer="Schneider Electric",
            manufacturer_part_number="LC1D09BD",
            description="TeSys D contactor 24VDC",
            list_price=42.50,
        )
    )
    repo.add_item(
        CatalogItem(
            internal_sku="SKU-SIEM-001",
            manufacturer="Siemens",
            manufacturer_part_number="6ES7214-1AG40-0XB0",
            description="SIMATIC S7-1200 CPU",
            list_price=285.00,
        )
    )
    return repo



@pytest.fixture
def case_manager(catalog_repo):
    return CaseManager(catalog=catalog_repo)


class TestReviewIntegrityAdversarial:
    """Tests that human approval is strictly bound and cannot be bypassed via post-approval edits."""

    def test_approved_line_quantity_edit_revokes_approval(self, case_manager):
        """Scenario: Approved line edited from 10 to 1,000 without explicit re-approval."""
        case = case_manager.create_case_from_text(
            raw_text="10 pcs LC1D09BD Schneider",
            title="Integrity Test",
        )
        lines = case_manager.get_lines(case.case_id)
        assert len(lines) == 1
        line_id = lines[0].line_id

        # 1. Human approves the line with quantity 10
        case_manager.update_line(
            case.case_id,
            line_id,
            RFQLineItemUpdate(expected_version=lines[0].version,
                review_decision=ReviewDecision.APPROVED,
                actor="Auditor #1",
                reviewer_notes="Verified against specification",
            ),
        )
        line = case_manager.get_lines(case.case_id)[0]
        assert line.review_decision == ReviewDecision.APPROVED
        assert line.reviewed_by == "Auditor #1"

        # 2. Adversarial / post-approval edit: Change quantity from 10 to 1,000
        case_manager.update_line(
            case.case_id,
            line_id,
            RFQLineItemUpdate(expected_version=line.version, quantity=1000.0, actor="Staff #2"),
        )
        line_after = case_manager.get_lines(case.case_id)[0]

        # Approval MUST be revoked back to PENDING and reviewed_by cleared!
        assert line_after.quantity == 1000.0
        assert line_after.review_decision == ReviewDecision.PENDING
        assert line_after.reviewed_by is None

        # Verify audit event records revocation
        trail = case_manager.get_audit_trail(case.case_id)
        assert any(
            "invalidated prior approval" in (e.notes or "")
            for e in trail
        )

    @pytest.mark.parametrize("field,new_val", [
        ("requested_mpn", "LC1D12BD"),
        ("requested_manufacturer", "Siemens"),
        ("selected_catalog_sku", "SKU-SIEM-001"),
        ("unit", "BOX"),
        ("description", "Modified description"),
        ("notes", "Urgent delivery terms"),
    ])
    def test_material_field_edit_revokes_prior_approval(self, case_manager, field, new_val):
        """Any material modification after approval invalidates approval."""
        case = case_manager.create_case_from_text(
            raw_text="10 pcs LC1D09BD Schneider",
            title="Integrity Test",
        )
        line_id = case_manager.get_lines(case.case_id)[0].line_id

        # Approve line
        case_manager.update_line(
            case.case_id,
            line_id,
            RFQLineItemUpdate(expected_version=case_manager.get_lines(case.case_id)[0].version, review_decision=ReviewDecision.APPROVED, actor="Lead Estimator"),
        )
        assert case_manager.get_lines(case.case_id)[0].review_decision == ReviewDecision.APPROVED

        # Modify material field
        kwargs = {field: new_val, "actor": "Sales Rep"}
        case_manager.update_line(case.case_id, line_id, RFQLineItemUpdate(expected_version=case_manager.get_lines(case.case_id)[0].version, **kwargs))

        # Must be reverted to PENDING
        updated_line = case_manager.get_lines(case.case_id)[0]
        assert updated_line.review_decision == ReviewDecision.PENDING
        assert updated_line.reviewed_by is None

    def test_contradictory_sku_selection_surfaces_warning(self, case_manager):
        """Scenario: Manually selected SKU contradicts requested manufacturer."""
        case = case_manager.create_case_from_text(
            raw_text="5 pcs 6ES7214-1AG40-0XB0 Schneider",  # Contradiction: Siemens part with Schneider OEM
        )
        line_id = case_manager.get_lines(case.case_id)[0].line_id

        # Assign Siemens SKU to a line requesting Schneider
        case_manager.update_line(
            case.case_id,
            line_id,
            RFQLineItemUpdate(expected_version=case_manager.get_lines(case.case_id)[0].version,
                selected_catalog_sku="SKU-SIEM-001",
                requested_manufacturer="Schneider",
            ),
        )
        line = case_manager.get_lines(case.case_id)[0]
        contradiction_warnings = [w for w in line.extraction_warnings if w.code == "CONTRADICTION"]
        assert len(contradiction_warnings) >= 1
        assert "contradicts requested manufacturer" in contradiction_warnings[0].message

    def test_quote_cannot_be_approved_with_pending_lines(self):
        """Scenario: Quote approval blocked when an underlying line is still pending review."""
        service = QuotationCommercialService()
        line = QuoteLine(
            line_no=1,
            requested_mpn="LC1D09BD",
            catalogue_part_id="SKU-SCH-001",
            quantity=Decimal("10"),
            unit_price=Decimal("42.50"),
            source_price_id="CAT-1",
            match_status="exact",
            requires_human_review=True,  # Still pending review!
        )
        quote = ProposedQuote(
            quote_id="Q-TEST",
            case_id="RFQ-TEST",
            lines=[line],
        )
        service.register_draft(quote)
        draft_hash = quote.draft_hash

        # Attempting to approve must fail
        with pytest.raises(ApprovalGateError) as exc_info:
            service.approve_draft(
                quote_id="Q-TEST",
                expected_hash=draft_hash,
                approver_name="Approver",
            )
        assert "still pending reviewer approval" in str(exc_info.value)

    def test_draft_hash_changes_on_any_material_line_modification(self):
        """Scenario: Verify draft hash changes when any significant commercial field is modified."""
        base_line = QuoteLine(
            line_no=1,
            requested_mpn="LC1D09BD",
            requested_manufacturer="Schneider",
            catalogue_part_id="SKU-SCH-001",
            description="Contactor",
            quantity=Decimal("10"),
            unit="EA",
            unit_price=Decimal("42.50"),
            currency="USD",
            source_price_id="CAT-1",
            match_status="exact",
            requires_human_review=False,
            line_notes="Original note",
        )
        draft1 = ProposedQuote(
            quote_id="Q-1",
            case_id="RFQ-1",
            lines=[base_line],
        )
        base_hash = draft1.compute_draft_hash()

        # Test changing each field alters hash
        mutations = [
            ("quantity", Decimal("100")),
            ("unit_price", Decimal("50.00")),
            ("requested_mpn", "LC1D12BD"),
            ("requested_manufacturer", "Siemens"),
            ("catalogue_part_id", "SKU-SCH-002"),
            ("description", "Altered description"),
            ("unit", "SET"),
            ("source_price_id", "CAT-2"),
            ("line_notes", "Tampered note"),
            ("requires_human_review", True),
        ]

        for field, new_val in mutations:
            mut_line = base_line.model_copy(update={field: new_val})
            draft_mut = ProposedQuote(
                quote_id="Q-1",
                case_id="RFQ-1",
                lines=[mut_line],
            )
            mut_hash = draft_mut.compute_draft_hash()
            assert mut_hash != base_hash, f"Hash did not change when mutating {field}"

    @pytest.mark.parametrize("invalid_qty", [-5, 0, float("nan"), float("inf"), -1.0])
    def test_invalid_quantities_rejected_in_manager(self, case_manager, invalid_qty):
        """Scenario: Missing, zero, negative, NaN, infinite quantities rejected."""
        case = case_manager.create_case_from_text(raw_text="10 pcs LC1D09BD Schneider")
        line_id = case_manager.get_lines(case.case_id)[0].line_id

        with pytest.raises(ValueError):
            case_manager.update_line(
                case.case_id,
                line_id,
                RFQLineItemUpdate(expected_version=case_manager.get_lines(case.case_id)[0].version, quantity=invalid_qty),
            )

    def test_invalid_prices_rejected_in_quote_validator(self):
        """Scenario: Negative, NaN, infinite prices rejected in quotation validator."""
        from pydantic import ValidationError

        # 1. Non-finite prices rejected at schema level
        for non_finite in [Decimal("NaN"), Decimal("Infinity")]:
            with pytest.raises(ValidationError):
                QuoteLine(
                    line_no=1,
                    requested_mpn="LC1D09BD",
                    quantity=Decimal("10"),
                    unit_price=non_finite,
                    source_price_id="CAT-1",
                    match_status="exact",
                    requires_human_review=False,
                )

        # 2. Negative prices rejected by business validator
        negative_line = QuoteLine(
            line_no=1,
            requested_mpn="LC1D09BD",
            quantity=Decimal("10"),
            unit_price=Decimal("-10.0"),
            source_price_id="CAT-1",
            match_status="exact",
            requires_human_review=False,
        )
        errors = validate_quote_line(negative_line)
        assert any("cannot be negative" in e for e in errors)

