"""Approval-gated commercial quotation and transmission tools.

Enforces version-bound human approval before any commercial side-effect:
- A human approving revision v7 does not approve v8.
- Mutations to line items, prices, or quantities invalidate prior approval.
- An unapproved quote cannot be sent.
"""

from datetime import datetime, timezone
from typing import Dict, Optional
from pydantic import BaseModel

from rfq_assistant.quotation.validate import ProposedQuote, validate_proposed_quote


class ApprovalGateError(Exception):
    """Raised when an approval gate check fails."""
    pass


class QuoteApprovalRecord(BaseModel):
    """Immutable record of a human approval action."""
    quote_id: str
    approved_hash: str
    approver_name: str
    approved_at: str
    commercial_status: str  # APPROVED, REJECTED


class QuotationCommercialService:
    """Manages quotation lifecycle and version-bound approvals."""

    def __init__(self):
        self._drafts: Dict[str, ProposedQuote] = {}
        self._approvals: Dict[str, QuoteApprovalRecord] = {}
        self._sent_quotes: Dict[str, Dict] = {}

    def register_draft(self, draft: ProposedQuote) -> ProposedQuote:
        """Registers a draft and computes its version hash."""
        draft.draft_hash = draft.compute_draft_hash()
        draft.validation_errors = validate_proposed_quote(draft)
        self._drafts[draft.quote_id] = draft
        return draft

    def get_draft(self, quote_id: str) -> Optional[ProposedQuote]:
        return self._drafts.get(quote_id)

    def approve_draft(
        self,
        quote_id: str,
        expected_hash: str,
        approver_name: str,
    ) -> QuoteApprovalRecord:
        """Approves draft strictly bound to the exact expected content hash."""
        draft = self._drafts.get(quote_id)
        if not draft:
            raise ApprovalGateError(f"Quotation draft '{quote_id}' not found.")

        # Recompute hash to ensure no in-flight mutation occurred
        current_hash = draft.compute_draft_hash()
        if current_hash != expected_hash:
            raise ApprovalGateError(
                f"Version mismatch: Draft has been modified. Expected {expected_hash[:8]}, current {current_hash[:8]}."
            )

        # Validate commercial invariants
        errors = validate_proposed_quote(draft)
        if errors:
            raise ApprovalGateError(
                f"Cannot approve draft with commercial errors: {'; '.join(errors)}"
            )

        record = QuoteApprovalRecord(
            quote_id=quote_id,
            approved_hash=current_hash,
            approver_name=approver_name,
            approved_at=datetime.now(timezone.utc).isoformat(),
            commercial_status="APPROVED",
        )

        draft.is_approved = True
        draft.approved_by = approver_name
        draft.approved_at = record.approved_at
        self._approvals[quote_id] = record
        return record

    def reject_draft(
        self,
        quote_id: str,
        approver_name: str,
        reason: str,
    ) -> QuoteApprovalRecord:
        """Rejects draft and records reason."""
        draft = self._drafts.get(quote_id)
        if not draft:
            raise ApprovalGateError(f"Quotation draft '{quote_id}' not found.")

        current_hash = draft.compute_draft_hash()
        record = QuoteApprovalRecord(
            quote_id=quote_id,
            approved_hash=current_hash,
            approver_name=approver_name,
            approved_at=datetime.now(timezone.utc).isoformat(),
            commercial_status="REJECTED",
        )
        draft.is_approved = False
        self._approvals[quote_id] = record
        return record

    def send_approved_quote(
        self,
        quote_id: str,
        expected_hash: str,
        sender_name: str,
    ) -> Dict:
        """Transmits quotation ONLY after verifying human approval and matching hash."""
        approval = self._approvals.get(quote_id)
        if not approval or approval.commercial_status != "APPROVED":
            raise ApprovalGateError(
                f"Blocked: Quotation '{quote_id}' has not been approved by an authorized employee."
            )

        draft = self._drafts.get(quote_id)
        if not draft:
            raise ApprovalGateError(f"Draft '{quote_id}' no longer exists.")

        current_hash = draft.compute_draft_hash()
        if current_hash != expected_hash or current_hash != approval.approved_hash:
            raise ApprovalGateError(
                "Blocked: Draft was modified after approval. Re-approval is required."
            )

        transmission_record = {
            "quote_id": quote_id,
            "hash": current_hash,
            "sender": sender_name,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "status": "SENT",
        }
        self._sent_quotes[quote_id] = transmission_record
        return transmission_record
