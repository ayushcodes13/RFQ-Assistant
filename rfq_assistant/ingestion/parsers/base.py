"""Abstract base class and data structures for document parsers."""

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field

from rfq_assistant.schemas.models import ExtractionWarning, SourceLocator


class EvidenceSegment(BaseModel):
    """Bounded source text retained for a later model fallback."""

    segment_id: str
    locator: SourceLocator
    text: str
    warnings: List[ExtractionWarning] = Field(default_factory=list)


class ParsedLineDraft(BaseModel):
    """An extracted candidate line draft with source locator and extracted fields."""
    line_number: int
    raw_text: str
    source_locator: SourceLocator
    requested_manufacturer: Optional[str] = None
    requested_mpn: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = "EA"
    notes: Optional[str] = None
    # Internal link used only while merging a grounded model fallback with a
    # deterministic candidate. It is not copied into the persisted RFQ schema.
    source_segment_id: Optional[str] = None
    extraction_warnings: List[ExtractionWarning] = Field(default_factory=list)


class ParsedDocumentResult(BaseModel):
    """Aggregate result from parsing an RFQ document or text snippet."""
    lines: List[ParsedLineDraft]
    warnings: List[ExtractionWarning] = Field(default_factory=list)
    total_lines_detected: int = 0
    evidence_segments: List[EvidenceSegment] = Field(default_factory=list)
    # Non-empty regions that the deterministic parser could not confidently
    # classify. They must reach grounded fallback or become explicit review rows.
    candidate_segments: List[EvidenceSegment] = Field(default_factory=list)


class DocumentParserError(Exception):
    """Base exception for parsing failures."""
    pass


class BaseDocumentParser(ABC):
    """Abstract interface for all document parsers."""

    @abstractmethod
    def parse(self, content: bytes, filename: str) -> ParsedDocumentResult:
        """Parses document bytes and returns structured line items with locators."""
        pass
