"""Core enumeration types for the RFQ Assistant domain."""

from enum import Enum


class CaseStatus(str, Enum):
    NEW = "NEW"
    PROCESSING = "PROCESSING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    READY_TO_EXPORT = "READY_TO_EXPORT"
    EXPORTED = "EXPORTED"
    FAILED = "FAILED"


class ProcessingStage(str, Enum):
    """Persisted, user-facing stages for an active ingestion job."""

    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    EXTRACTING = "EXTRACTING"
    CHECKING_FIELDS = "CHECKING_FIELDS"
    MATCHING = "MATCHING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    FAILED = "FAILED"


class SourceType(str, Enum):
    EMAIL_TEXT = "EMAIL_TEXT"
    CSV = "CSV"
    XLSX = "XLSX"
    PDF_NATIVE = "PDF_NATIVE"
    PDF_SCANNED = "PDF_SCANNED"


class ExtractionStatus(str, Enum):
    EXTRACTED = "EXTRACTED"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    UNRESOLVED = "UNRESOLVED"


class MatchStatus(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    COLLISION = "COLLISION"
    NO_MATCH = "NO_MATCH"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class ReviewDecision(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    REJECTED = "REJECTED"


class AuditAction(str, Enum):
    CASE_CREATED = "CASE_CREATED"
    PARSED = "PARSED"
    LINE_EDITED = "LINE_EDITED"
    LINE_APPROVED = "LINE_APPROVED"
    LINE_REJECTED = "LINE_REJECTED"
    LINE_FLAGGED = "LINE_FLAGGED"
    CATALOG_IMPORTED = "CATALOG_IMPORTED"
    EXPORTED = "EXPORTED"
