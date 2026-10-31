"""Pydantic schemas and models for RFQ cases, line items, catalogs, matches, and audit."""

from datetime import datetime
import math
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator

from rfq_assistant.schemas.enums import (
    AuditAction,
    CaseStatus,
    ExtractionStatus,
    MatchStatus,
    ReviewDecision,
    SourceType,
)


class SourceLocator(BaseModel):
    """Pinpoints where a line was extracted from within original source document."""
    file_name: str
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


class ExtractionWarning(BaseModel):
    """Specific warning regarding missing, ambiguous, or contradictory extracted values."""
    code: str
    message: str
    severity: str = "warning"  # "warning" or "error"


class CatalogItem(BaseModel):
    """An approved record from the distributor's item master."""
    internal_sku: str
    manufacturer: str
    manufacturer_part_number: str
    description: str
    list_price: Optional[float] = None
    stock_qty: Optional[int] = None
    catalog_version: Optional[str] = "v1"


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
    candidates: List[MatchCandidate] = Field(default_factory=list)
    review_decision: ReviewDecision = ReviewDecision.PENDING
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_notes: Optional[str] = None
    version: int = 1


class RFQLineItemUpdate(BaseModel):
    """Payload for human reviewer correcting or approving a line item."""
    expected_version: Optional[int] = None
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


class BatchReviewRequest(BaseModel):
    """Batch approve or flag multiple lines with actor attribution."""
    line_ids: List[str]
    decision: ReviewDecision
    actor: str = "Inside Sales"
    notes: Optional[str] = None


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
    source_type: SourceType
    mime_type: str
    size_bytes: int
    sha256_digest: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class RFQCase(BaseModel):
    """An RFQ quotation case containing metadata and processing status."""
    case_id: str
    title: str
    customer_label: Optional[str] = None
    status: CaseStatus = CaseStatus.NEW
    source_type: SourceType
    source_file: Optional[SourceFileMetadata] = None
    source_coverage: List[SourceCoverageUnit] = Field(default_factory=list)
    document_warnings: List[ExtractionWarning] = Field(default_factory=list)
    raw_text: Optional[str] = None
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
