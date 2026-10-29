"""Case lifecycle manager with audit logging and state tracking."""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from rfq_assistant.ingestion import (
    DocumentParserError,
    DocumentStorage,
    get_parser,
    validate_file_upload,
)
from rfq_assistant.matching import CatalogRepository, ExactMatchEngine
from rfq_assistant.quotation.line_rules import blocking_line_issues
from rfq_assistant.schemas.enums import (
    AuditAction,
    CaseStatus,
    ExtractionStatus,
    MatchStatus,
    ReviewDecision,
    SourceType,
)

from rfq_assistant.schemas.models import (
    AuditEvent,
    BatchReviewRequest,
    ExtractionWarning,
    RFQCase,
    RFQLineItem,
    RFQLineItemUpdate,
    SourceFileMetadata,
    SourceLocator,
)



class CaseManager:
    """Orchestrates case ingestion, catalog matching, line updates, and audit logging."""

    def __init__(self, catalog: CatalogRepository, storage: Optional[DocumentStorage] = None):
        self.catalog = catalog
        self.storage = storage or DocumentStorage()
        self.matcher = ExactMatchEngine(self.catalog)

        # In-memory stores
        self._cases: Dict[str, RFQCase] = {}
        self._lines_by_case: Dict[str, List[RFQLineItem]] = {}
        self._audit_events: Dict[str, List[AuditEvent]] = {}

    def get_case(self, case_id: str) -> Optional[RFQCase]:
        return self._cases.get(case_id)

    def list_cases(self) -> List[RFQCase]:
        return sorted(self._cases.values(), key=lambda c: c.created_at, reverse=True)

    def get_lines(self, case_id: str) -> List[RFQLineItem]:
        return self._lines_by_case.get(case_id, [])

    def get_audit_trail(self, case_id: str) -> List[AuditEvent]:
        return self._audit_events.get(case_id, [])

    def create_case_from_upload(
        self,
        filename: str,
        content: bytes,
        title: Optional[str] = None,
        customer_label: Optional[str] = None,
        actor: str = "Inside Sales",
    ) -> RFQCase:
        """Validates, stores, parses, and matches an uploaded RFQ document."""
        clean_name, src_type, digest = validate_file_upload(filename, content)
        case_id = f"RFQ-{uuid.uuid4().hex[:8].upper()}"

        # Persist original document
        self.storage.save_file(case_id, clean_name, content)

        file_meta = SourceFileMetadata(
            file_id=f"file-{uuid.uuid4().hex[:6]}",
            file_name=clean_name,
            source_type=src_type,
            mime_type="application/octet-stream",
            size_bytes=len(content),
            sha256_digest=digest,
        )

        case = RFQCase(
            case_id=case_id,
            title=title or f"RFQ Intake - {clean_name}",
            customer_label=customer_label,
            status=CaseStatus.PROCESSING,
            source_type=src_type,
            source_file=file_meta,
        )
        self._cases[case_id] = case
        self._audit_events[case_id] = []

        self._record_audit(
            case_id=case_id,
            actor=actor,
            action=AuditAction.CASE_CREATED,
            notes=f"Uploaded document '{clean_name}' (SHA256: {digest[:8]}...)",
        )

        try:
            # Parse document
            parser = get_parser(src_type)
            parse_result = parser.parse(content, clean_name)
            # A "successful" empty RFQ is worse than an explicit parse failure:
            # operators might otherwise export an empty worksheet as complete.
            if not parse_result.lines:
                raise DocumentParserError(
                    "No RFQ line items could be extracted. Please correct the document or paste items manually."
                )
            fatal_warnings = [w for w in parse_result.warnings if w.severity.lower() == "error"]
            if fatal_warnings:
                raise DocumentParserError(
                    "Document extraction failed: " + "; ".join(w.message for w in fatal_warnings)
                )

            # Match lines against catalog
            lines: List[RFQLineItem] = []
            for draft in parse_result.lines:
                line_id = f"line-{uuid.uuid4().hex[:8]}"
                match_res = self.matcher.match_line(draft.requested_mpn, draft.requested_manufacturer)

                extract_status = (
                    ExtractionStatus.NEEDS_CORRECTION
                    if draft.extraction_warnings or draft.quantity is None
                    else ExtractionStatus.EXTRACTED
                )

                line_item = RFQLineItem(
                    line_id=line_id,
                    case_id=case_id,
                    line_number=draft.line_number,
                    raw_text=draft.raw_text,
                    source_locator=draft.source_locator,
                    requested_manufacturer=draft.requested_manufacturer,
                    requested_mpn=draft.requested_mpn,
                    description=draft.description,
                    quantity=draft.quantity,
                    unit=draft.unit,
                    notes=draft.notes,
                    extraction_status=extract_status,
                    extraction_warnings=draft.extraction_warnings,
                    match_status=match_res.match_status,
                    selected_catalog_sku=match_res.selected_sku,
                    candidates=match_res.candidates,
                    review_decision=ReviewDecision.PENDING,
                )
                lines.append(line_item)

            self._lines_by_case[case_id] = lines
            self._record_audit(
                case_id=case_id,
                actor=actor,
                action=AuditAction.PARSED,
                notes=f"Extracted {len(lines)} line items with {len(parse_result.warnings)} document-level warnings.",
            )

            self._refresh_case_metrics(case_id)
            return self._cases[case_id]
        except Exception:
            # Rollback: Clean up stored files and remove partial case record
            self.storage.delete_case(case_id)
            self._cases.pop(case_id, None)
            self._lines_by_case.pop(case_id, None)
            self._audit_events.pop(case_id, None)
            raise


    def create_case_from_text(
        self,
        raw_text: str,
        title: Optional[str] = None,
        customer_label: Optional[str] = None,
        actor: str = "Inside Sales",
    ) -> RFQCase:
        """Parses and matches plain pasted email or inquiry text."""
        content = raw_text.encode("utf-8")
        case = self.create_case_from_upload(
            filename="pasted_inquiry.txt",
            content=content,
            title=title or "RFQ Intake - Pasted Email",
            customer_label=customer_label,
            actor=actor,
        )
        case.source_type = SourceType.EMAIL_TEXT
        case.raw_text = raw_text
        return case

    def update_line(
        self, case_id: str, line_id: str, update: RFQLineItemUpdate
    ) -> Optional[RFQLineItem]:
        """Applies a human reviewer edit or decision to a line item with full audit trail."""
        lines = self._lines_by_case.get(case_id, [])
        line = next((l for l in lines if l.line_id == line_id), None)
        if not line:
            return None

        # Optimistic concurrency check
        if update.expected_version is not None and update.expected_version != line.version:
            raise ValueError(
                f"Stale state / conflict: Line item version is {line.version}, but client expected version {update.expected_version}. Please refresh."
            )

        material_changes = []

        # Validate quantity strictly
        if update.quantity is not None:
            import math
            try:
                q_val = float(update.quantity)
            except (ValueError, TypeError):
                raise ValueError(f"Quantity must be a numeric value, got '{update.quantity}'")
            if math.isnan(q_val) or math.isinf(q_val):
                raise ValueError(f"Quantity cannot be NaN or Infinite: {update.quantity}")
            if q_val <= 0:
                raise ValueError(f"Quantity must be strictly positive (> 0), got {update.quantity}")

            if update.quantity != line.quantity:
                material_changes.append("quantity")
                self._record_audit(
                    case_id=case_id,
                    line_id=line_id,
                    actor=update.actor,
                    action=AuditAction.LINE_EDITED,
                    field_name="quantity",
                    old_value=str(line.quantity),
                    new_value=str(update.quantity),
                    notes=update.reviewer_notes,
                )
                line.quantity = update.quantity
                # Clear missing quantity warning if fixed
                line.extraction_warnings = [w for w in line.extraction_warnings if w.code != "MISSING_QUANTITY"]

        if update.requested_mpn is not None and update.requested_mpn != line.requested_mpn:
            material_changes.append("requested_mpn")
            self._record_audit(
                case_id=case_id,
                line_id=line_id,
                actor=update.actor,
                action=AuditAction.LINE_EDITED,
                field_name="requested_mpn",
                old_value=line.requested_mpn,
                new_value=update.requested_mpn,
            )
            line.requested_mpn = update.requested_mpn
            # Re-match against catalog
            rematch = self.matcher.match_line(line.requested_mpn, line.requested_manufacturer)
            line.match_status = rematch.match_status
            line.selected_catalog_sku = rematch.selected_sku
            line.candidates = rematch.candidates

        if update.requested_manufacturer is not None and update.requested_manufacturer != line.requested_manufacturer:
            material_changes.append("requested_manufacturer")
            self._record_audit(
                case_id=case_id,
                line_id=line_id,
                actor=update.actor,
                action=AuditAction.LINE_EDITED,
                field_name="requested_manufacturer",
                old_value=line.requested_manufacturer,
                new_value=update.requested_manufacturer,
            )
            line.requested_manufacturer = update.requested_manufacturer
            rematch = self.matcher.match_line(line.requested_mpn, line.requested_manufacturer)
            line.match_status = rematch.match_status
            line.selected_catalog_sku = rematch.selected_sku
            line.candidates = rematch.candidates

        if update.selected_catalog_sku is not None and update.selected_catalog_sku != line.selected_catalog_sku:
            material_changes.append("selected_catalog_sku")
            self._record_audit(
                case_id=case_id,
                line_id=line_id,
                actor=update.actor,
                action=AuditAction.LINE_EDITED,
                field_name="selected_catalog_sku",
                old_value=line.selected_catalog_sku,
                new_value=update.selected_catalog_sku,
            )
            line.selected_catalog_sku = update.selected_catalog_sku
            line.match_status = MatchStatus.MANUAL_OVERRIDE

        if update.unit is not None and update.unit != line.unit:
            material_changes.append("unit")
            line.unit = update.unit

        if update.description is not None and update.description != line.description:
            material_changes.append("description")
            line.description = update.description

        if update.notes is not None and update.notes != line.notes:
            material_changes.append("notes")
            line.notes = update.notes

        # Contradiction check: verify selected SKU against requested OEM
        if line.selected_catalog_sku:
            cat_item = self.catalog.get_by_sku(line.selected_catalog_sku)
            if cat_item and line.requested_manufacturer:
                req_oem = line.requested_manufacturer.strip().lower()
                cat_oem = cat_item.manufacturer.strip().lower()
                if req_oem not in cat_oem and cat_oem not in req_oem:
                    # Remove any existing contradiction warning then add high severity alert
                    line.extraction_warnings = [w for w in line.extraction_warnings if w.code != "CONTRADICTION"]
                    line.extraction_warnings.append(
                        ExtractionWarning(
                            code="CONTRADICTION",
                            message=(
                                f"Selected SKU '{line.selected_catalog_sku}' ({cat_item.manufacturer}) "
                                f"contradicts requested manufacturer '{line.requested_manufacturer}'."
                            ),
                            severity="error",
                        )
                    )

                else:
                    line.extraction_warnings = [w for w in line.extraction_warnings if w.code != "CONTRADICTION"]

        # Invariant: If line was previously approved and any material field was changed,
        # approval is revoked unless the update explicitly re-approves with APPROVED.
        if line.review_decision == ReviewDecision.APPROVED and material_changes:
            if update.review_decision != ReviewDecision.APPROVED:
                self._record_audit(
                    case_id=case_id,
                    line_id=line_id,
                    actor=update.actor,
                    action=AuditAction.LINE_FLAGGED,
                    field_name="review_decision",
                    old_value=ReviewDecision.APPROVED.value,
                    new_value=ReviewDecision.PENDING.value,
                    notes=f"Material changes to {', '.join(material_changes)} invalidated prior approval. Re-approval required.",
                )
                line.review_decision = ReviewDecision.PENDING
                line.reviewed_by = None
                line.reviewed_at = None

        if update.review_decision is not None and update.review_decision != line.review_decision:
            action_map = {
                ReviewDecision.APPROVED: AuditAction.LINE_APPROVED,
                ReviewDecision.REJECTED: AuditAction.LINE_REJECTED,
                ReviewDecision.NEEDS_CLARIFICATION: AuditAction.LINE_FLAGGED,
            }
            self._record_audit(
                case_id=case_id,
                line_id=line_id,
                actor=update.actor,
                action=action_map.get(update.review_decision, AuditAction.LINE_EDITED),
                field_name="review_decision",
                old_value=line.review_decision.value,
                new_value=update.review_decision.value,
                notes=update.reviewer_notes,
            )
            line.review_decision = update.review_decision
            line.reviewed_by = update.actor
            line.reviewed_at = datetime.utcnow()

        if update.reviewer_notes is not None:
            line.reviewer_notes = update.reviewer_notes

        line.version += 1
        self._refresh_case_metrics(case_id)
        return line


    def batch_review(self, case_id: str, request: BatchReviewRequest) -> int:
        """Applies batch decision to specified lines."""
        updated = 0
        for lid in request.line_ids:
            upd = RFQLineItemUpdate(
                review_decision=request.decision,
                actor=request.actor,
                reviewer_notes=request.notes,
            )
            if self.update_line(case_id, lid, upd):
                updated += 1
        return updated

    def delete_case(self, case_id: str) -> bool:
        """Deletes case and its associated files."""
        if case_id in self._cases:
            del self._cases[case_id]
            self._lines_by_case.pop(case_id, None)
            self._audit_events.pop(case_id, None)
            self.storage.delete_case(case_id)
            return True
        return False

    def _refresh_case_metrics(self, case_id: str):
        case = self._cases.get(case_id)
        if not case:
            return

        lines = self._lines_by_case.get(case_id, [])
        case.line_count = len(lines)
        case.updated_at = datetime.utcnow()

        # Keep case readiness consistent with the final export gate.
        unresolved = sum(1 for line in lines if blocking_line_issues(line, self.catalog))
        case.unresolved_count = unresolved

        if unresolved == 0 and len(lines) > 0:
            case.status = CaseStatus.READY_TO_EXPORT
        else:
            case.status = CaseStatus.NEEDS_REVIEW

    def _record_audit(
        self,
        case_id: str,
        actor: str,
        action: AuditAction,
        line_id: Optional[str] = None,
        field_name: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        event = AuditEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            case_id=case_id,
            line_id=line_id,
            actor=actor,
            action=action,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            notes=notes,
        )
        if case_id not in self._audit_events:
            self._audit_events[case_id] = []
        self._audit_events[case_id].append(event)
