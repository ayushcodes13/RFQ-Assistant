"""Pydantic schemas and models for RFQ cases, line items, catalogs, matches, and audit."""

import math
from datetime import datetime
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from rfq_assistant.schemas.enums import (
    AuditAction,
    CaseStatus,
    ExtractionOrigin,
    ExtractionStatus,
    MatchStatus,
    ProcessingStage,
    ReviewDecision,
    SourceType,
)


class SourceLocator(BaseModel):
    """Pinpoints where a line was extracted from within original source document."""
    file_name: str
    source_file_id: Optional[str] = None
    page_number: Optional[int] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    text_snippet: Optional[str] = None
    # Normalized 0..1 PDF page coordinates, after applying page rotation.
    page_bbox: Optional[Tuple[float, float, float, float]] = None
    ocr_confidence: Optional[float] = None
    field_source_cells: Dict[str, str] = Field(default_factory=dict)

    @field_validator("page_bbox")
    @classmethod
    def page_bbox_is_valid(cls, value):
        if value is None:
            return value
        if any(not math.isfinite(coordinate) or not 0 <= coordinate <= 1 for coordinate in value):
            raise ValueError("page_bbox coordinates must be finite values from 0 to 1")
        x0, y0, x1, y1 = value
        if x0 >= x1 or y0 >= y1:
            raise ValueError("page_bbox must have positive width and height")
        return value

    @field_validator("ocr_confidence")
    @classmethod
    def ocr_confidence_is_valid(cls, value):
        if value is not None and (not math.isfinite(value) or not 0 <= value <= 100):
            raise ValueError("ocr_confidence must be between 0 and 100")
        return value


class SourceCoverageUnit(BaseModel):
    """Compact, hash-backed accounting for one PDF page, workbook sheet, or text document."""
    unit_id: str
    locator: SourceLocator
    content_sha256: Optional[str] = None
    unit_kind: str = "document"
    processing_status: str = "processed"
    is_empty: bool = False
    truncated: bool = False
    error_code: Optional[str] = None
    ocr_status: Optional[str] = None
    ocr_duration_ms: Optional[float] = None
    sheet_visibility: Optional[str] = None
    header_row_number: Optional[int] = None
    hidden_row_count: int = 0
    hidden_column_count: int = 0
    formula_backed_fields: int = 0
    page_rotation_degrees: Optional[int] = None
    nonempty_regions: int = 0
    structured_regions: int = 0
    review_regions: int = 0
    filtered_regions: int = 0
    ocr_failures: int = 0

    @computed_field
    @property
    def coverage_basis(self) -> str:
        """Distinguish deterministic spreadsheet scanning from heuristic text regions."""
        if self.unit_kind in {"csv_document", "workbook_sheet"}:
            return "structured_rows"
        return "heuristic_regions"


class SourcePreviewCell(BaseModel):
    coordinate: str
    value: str
    is_formula: bool = False
    selected: bool = False


class SourcePreviewRow(BaseModel):
    row_number: int
    is_target: bool = False
    cells: List[SourcePreviewCell] = Field(default_factory=list)


class SpreadsheetSourcePreview(BaseModel):
    file_name: str
    sheet_name: str
    target_row: int
    target_cells: List[str] = Field(default_factory=list)
    rows: List[SourcePreviewRow] = Field(default_factory=list)


class ExtractionWarning(BaseModel):
    """Specific warning regarding missing, ambiguous, or contradictory extracted values."""
    code: str
    message: str
    severity: str = "warning"  # "warning" or "error"


class FieldProvenance(BaseModel):
    """Versioned source and review record for one extracted line field."""

    raw_value: Optional[str] = None
    proposed_value: Optional[str] = None
    origin: ExtractionOrigin = ExtractionOrigin.DETERMINISTIC
    source_locator: SourceLocator
    evidence: Optional[str] = None
    validation_status: str = "source_grounded"
    revision: int = 1
    review_status: ReviewDecision = ReviewDecision.PENDING
    warnings: List[ExtractionWarning] = Field(default_factory=list)


class CatalogItem(BaseModel):
    """An approved record from the distributor's item master."""
    internal_sku: str
    manufacturer: str
    manufacturer_part_number: str
    description: str
    list_price: Optional[float] = None
    currency: Optional[str] = None
    stock_qty: Optional[int] = None
    catalog_version: Optional[str] = "v1"


CatalogClearField = Literal["list_price", "currency", "stock_qty"]


class CatalogUpdateProposal(BaseModel):
    """Unapplied distributor-data change with source evidence and review history."""

    proposal_id: str
    batch_id: str
    revision_of: Optional[str] = None
    source_name: str
    source_sha256: str
    source_locator: SourceLocator
    evidence_quote: str
    change_type: Literal["new", "changed", "unchanged", "conflict"]
    review_status: Literal["pending", "accepted", "rejected"] = "pending"
    current_item: Optional[CatalogItem] = None
    proposed_values: Dict[str, object] = Field(default_factory=dict)
    changed_fields: Dict[str, Dict[str, object]] = Field(default_factory=dict)
    clear_fields: List[CatalogClearField] = Field(default_factory=list)
    blocking_reasons: List[str] = Field(default_factory=list)
    source_warnings: List[str] = Field(default_factory=list)
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_note: Optional[str] = None
    version: int = 1


class CatalogUpdateReviewRequest(BaseModel):
    """Optional reviewer note for an explicit proposal decision."""

    note: Optional[str] = Field(default=None, max_length=2000)


class MatchCandidate(BaseModel):
    """Proposed catalog match backed by exact OEM and MPN evidence."""
    catalog_item: CatalogItem
    match_type: MatchStatus
    explanation: str
    confidence_note: str


class RFQLineItem(BaseModel):
    """Individual extracted and human-reviewed line item."""
    line_id: str
    case_id: str
    line_number: int
    raw_text: str
    source_locator: SourceLocator
    field_provenance: Dict[str, FieldProvenance] = Field(default_factory=dict)
    requested_manufacturer: Optional[str] = None
    requested_mpn: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = "EA"
    required_by: Optional[str] = None
    notes: Optional[str] = None
    extraction_status: ExtractionStatus = ExtractionStatus.EXTRACTED
    extraction_warnings: List[ExtractionWarning] = Field(default_factory=list)
    match_status: MatchStatus = MatchStatus.NO_MATCH
    selected_catalog_sku: Optional[str] = None
    matched_catalog_version: Optional[str] = None
    catalog_rematch_required: bool = False
    candidates: List[MatchCandidate] = Field(default_factory=list)
    review_decision: ReviewDecision = ReviewDecision.PENDING
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
    version: int = 1


class RFQLineItemUpdate(BaseModel):
    """Payload for human reviewer correcting or approving a line item."""
    expected_version: int = Field(ge=1)
    requested_manufacturer: Optional[str] = None
    requested_mpn: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    notes: Optional[str] = None
    selected_catalog_sku: Optional[str] = None
    review_decision: Optional[ReviewDecision] = None
    reviewer_notes: Optional[str] = None
    actor: str = "Inside Sales"


class RFQLineItemUpdateRequest(RFQLineItemUpdate):
    """Public reviewer edit contract; every API write must be version-checked."""
    expected_version: int = Field(..., ge=1)


class RematchLineRequest(BaseModel):
    """Explicitly rematch one stale line against the active catalog snapshot."""

    expected_version: int = Field(..., ge=1)
    actor: str = "Inside Sales"


class BatchReviewRequest(BaseModel):
    """Batch approve or flag lines only from the reviewer’s visible versions."""
    line_ids: List[str]
    expected_versions: Dict[str, int]
    decision: ReviewDecision
    actor: str = "Inside Sales"
    notes: Optional[str] = None


class ApproveRemainingRequest(BaseModel):
    """Snapshot versions for every line when approving a review-plan remainder."""
    expected_versions: Dict[str, int]


class ReviewPlan(BaseModel):
    """Risk-based human review worklist for one extracted RFQ case."""
    case_id: str
    total_lines: int
    exception_line_ids: List[str]
    sample_line_ids: List[str]
    sample_rationale: Dict[str, str] = Field(default_factory=dict)
    remaining_line_ids: List[str]
    sample_approved: bool
    sample_correction_found: bool
    can_batch_approve: bool


class SourceFileMetadata(BaseModel):
    """Metadata describing the uploaded RFQ document."""
    file_id: str
    file_name: str
    storage_key: Optional[str] = None
    source_type: SourceType
    mime_type: str
    size_bytes: int
    sha256_digest: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class RFQSourceDocument(BaseModel):
    """One original email or attachment and its independent processing result."""

    source_file: SourceFileMetadata
    processing_status: Literal["queued", "processing", "processed", "failed", "duplicate"] = "queued"
    line_count: int = 0
    error_code: Optional[str] = None


class RFQCaseSummary(BaseModel):
    """Case-list projection without customer RFQ text."""
    case_id: str
    title: str
    customer_label: Optional[str] = None
    status: CaseStatus = CaseStatus.NEW
    processing_stage: Optional[ProcessingStage] = None
    source_type: SourceType
    source_file: Optional[SourceFileMetadata] = None
    source_documents: List[RFQSourceDocument] = Field(default_factory=list)
    source_coverage: List[SourceCoverageUnit] = Field(default_factory=list)
    document_warnings: List[ExtractionWarning] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    line_count: int = 0
    unresolved_count: int = 0
    parser_version: str = "v1-deterministic"
    processing_profile_sha256: Optional[str] = None
    parse_cache_hit: bool = False
    stage_timings_ms: Dict[str, float] = Field(default_factory=dict)
    llm_model: Optional[str] = None
    llm_deployment_version: Optional[str] = None
    llm_cache_hit: bool = False
    llm_prompt_sha256: Optional[str] = None
    llm_schema_version: Optional[str] = None
    llm_validator_version: Optional[str] = None
    llm_call_count: int = 0
    llm_repair_call_count: int = 0
    llm_review_call_count: int = 0
    llm_input_tokens: Optional[int] = None
    llm_output_tokens: Optional[int] = None
    catalog_id: Optional[str] = "default"
    catalog_version: Optional[str] = None


class RFQCase(RFQCaseSummary):
    """An RFQ quotation case, including source text on the case-detail route."""
    raw_text: Optional[str] = None

    @model_validator(mode="after")
    def preserve_legacy_single_source(self):
        if not self.source_documents and self.source_file:
            status = "processed"
            if self.status == CaseStatus.PROCESSING:
                status = "queued"
            elif self.status == CaseStatus.FAILED:
                status = "failed"
            self.source_documents = [RFQSourceDocument(
                source_file=self.source_file,
                processing_status=status,
                line_count=self.line_count,
            )]
        return self


class HealthResponse(BaseModel):
    """Minimal public liveness response for local and hosted health probes."""
    status: Literal["healthy"]


class AuditEvent(BaseModel):
    """Immutable audit entry for traceability."""
    event_id: str
    case_id: str
    line_id: Optional[str] = None
    actor: str
    action: AuditAction
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None


class ExportRequest(BaseModel):
    """Parameters for exporting quotation preparation sheet and email draft."""
    case_id: str
    actor: str = "Inside Sales"
    allow_partial: bool = False
    format: str = "xlsx"  # xlsx or csv


class ExportManifest(BaseModel):
    """Result of an authorized export operation."""
    export_id: str
    case_id: str
    file_name: str
    format: str
    is_draft: bool = True
    total_lines: int
    approved_lines: int
    unresolved_lines_omitted: int
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    reviewer_name: str
    unsent_email_draft: str
    download_url: str


class ExportDocumentSummary(BaseModel):
    """A locally generated RFQ document available in a case's document list."""

    export_id: str
    file_name: str
    format: Literal["xlsx", "csv"]
    is_draft: bool = True
    total_lines: int = 0
    approved_lines: int = 0
    unresolved_lines_omitted: int = 0
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    file_available: bool = True
    problem: Optional[str] = None
    download_url: str
