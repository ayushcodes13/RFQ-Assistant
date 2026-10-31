"""Pydantic schemas and models for RFQ cases, line items, catalogs, matches, and audit."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

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
    document_warnings: List[ExtractionWarning] = Field(default_factory=list)
    raw_text: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    line_count: int = 0
    unresolved_count: int = 0
    parser_version: str = "v1-deterministic"
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
