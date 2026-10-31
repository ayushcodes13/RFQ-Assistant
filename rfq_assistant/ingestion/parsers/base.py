"""Abstract base class and data structures for document parsers."""

from abc import ABC, abstractmethod
import hashlib
from typing import List, Optional
from pydantic import BaseModel, Field

from rfq_assistant.schemas.models import ExtractionWarning, SourceCoverageUnit, SourceLocator

MAX_CANDIDATE_REGIONS = 500


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
    source_coverage: List[SourceCoverageUnit] = Field(default_factory=list)
    llm_model: Optional[str] = None
    llm_deployment_version: Optional[str] = None
    llm_prompt_sha256: Optional[str] = None
    llm_call_count: int = 0
    llm_repair_call_count: int = 0
    llm_review_call_count: int = 0
    llm_input_tokens: Optional[int] = None
    llm_output_tokens: Optional[int] = None


def make_coverage_entry(
    region_id: str,
    locator: SourceLocator,
    source_text: str,
    disposition: str,
    rule_code: str,
) -> dict:
    """Create a content-free receipt tied to a precise source location."""
    digest = hashlib.sha256(source_text.encode("utf-8", errors="replace")).hexdigest()
    return {
        "region_id": region_id,
        "locator": locator,
        "content_sha256": digest,
        "disposition": disposition,
        "rule_code": rule_code,
    }


class SourceCoverageAccumulator:
    """Aggregate receipts as the parser walks the file, without retaining all row text."""

    def __init__(self) -> None:
        self._groups: dict[str, dict] = {}

    def record_unit(
        self,
        unit_id: str,
        locator: SourceLocator,
        *,
        unit_kind: str,
        processing_status: str = "processed",
        is_empty: bool = False,
        truncated: bool = False,
        error_code: Optional[str] = None,
        ocr_status: Optional[str] = None,
        sheet_visibility: Optional[str] = None,
        header_row_number: Optional[int] = None,
        formula_backed_fields: Optional[int] = None,
        page_rotation_degrees: Optional[int] = None,
    ) -> None:
        """Record source units even when they contain no extractable text."""
        group = self._groups.setdefault(unit_id, {
            "locator": locator.model_copy(update={"row_number": None, "text_snippet": None}),
            "digest": hashlib.sha256(),
            "unit_kind": unit_kind,
            "processing_status": processing_status,
            "is_empty": is_empty,
            "truncated": truncated,
            "error_code": error_code,
            "ocr_status": ocr_status,
            "sheet_visibility": sheet_visibility,
            "header_row_number": header_row_number,
            "formula_backed_fields": 0,
            "page_rotation_degrees": page_rotation_degrees,
            "nonempty_regions": 0,
            "structured_regions": 0,
            "review_regions": 0,
            "filtered_regions": 0,
            "ocr_failures": 0,
        })
        # Later parser stages enrich, rather than replace, the unit receipt.
        for key, value in {
            "processing_status": processing_status,
            "is_empty": is_empty,
            "truncated": truncated,
            "error_code": error_code,
            "ocr_status": ocr_status,
            "sheet_visibility": sheet_visibility,
            "header_row_number": header_row_number,
            "page_rotation_degrees": page_rotation_degrees,
        }.items():
            if value is not None and (value is not False or key in {"is_empty", "truncated"}):
                group[key] = value

    def add_formula_backed_fields(self, unit_id: str, count: int) -> None:
        if unit_id in self._groups:
            self._groups[unit_id]["formula_backed_fields"] += count

    def append(self, receipt: dict) -> None:
        locator = receipt["locator"]
        if locator.page_number is not None:
            unit_id = f"page:{locator.page_number}"
        elif locator.sheet_name is not None:
            unit_id = f"sheet:{locator.sheet_name}"
        else:
            unit_id = "document"
        group = self._groups.setdefault(unit_id, {
            "locator": locator.model_copy(update={"row_number": None, "text_snippet": None}),
            "digest": hashlib.sha256(),
            "nonempty_regions": 0,
            "structured_regions": 0,
            "review_regions": 0,
            "filtered_regions": 0,
            "ocr_failures": 0,
            "unit_kind": "pdf_page" if locator.page_number is not None else "workbook_sheet" if locator.sheet_name is not None else "document",
            "processing_status": "processed",
            "is_empty": False,
            "truncated": False,
            "error_code": None,
            "ocr_status": None,
            "sheet_visibility": None,
            "header_row_number": None,
            "formula_backed_fields": 0,
            "page_rotation_degrees": None,
        })
        group["digest"].update(
            f"{receipt['region_id']}:{receipt['content_sha256']}:{receipt['disposition']}\n".encode("utf-8")
        )
        if receipt["disposition"] == "ocr_error":
            group["ocr_failures"] += 1
        else:
            group["is_empty"] = False
            group["nonempty_regions"] += 1
            if receipt["disposition"] == "structured_line":
                group["structured_regions"] += 1
            elif receipt["disposition"] == "review_candidate":
                group["review_regions"] += 1
            else:
                group["filtered_regions"] += 1

    def build(self) -> List[SourceCoverageUnit]:
        return [
            SourceCoverageUnit(
                unit_id=unit_id,
                locator=group["locator"],
                content_sha256=group["digest"].hexdigest(),
                unit_kind=group["unit_kind"],
                processing_status=group["processing_status"],
                is_empty=group["is_empty"],
                truncated=group["truncated"],
                error_code=group["error_code"],
                ocr_status=group["ocr_status"],
                sheet_visibility=group["sheet_visibility"],
                header_row_number=group["header_row_number"],
                formula_backed_fields=group["formula_backed_fields"],
                page_rotation_degrees=group["page_rotation_degrees"],
                nonempty_regions=group["nonempty_regions"],
                structured_regions=group["structured_regions"],
                review_regions=group["review_regions"],
                filtered_regions=group["filtered_regions"],
                ocr_failures=group["ocr_failures"],
            )
            for unit_id, group in sorted(self._groups.items())
        ]


class DocumentParserError(Exception):
    """Base exception for parsing failures."""

    def __init__(self, message: str, source_coverage=None):
        super().__init__(message)
        self.source_coverage = source_coverage or []


def enforce_candidate_region_limit(
    segments: List[EvidenceSegment], source_coverage: Optional[List] = None
) -> None:
    """Fail explicitly rather than create an unbounded manual-review queue."""
    if len(segments) > MAX_CANDIDATE_REGIONS:
        raise DocumentParserError(
            f"Document contains more than {MAX_CANDIDATE_REGIONS} unresolved non-empty regions. "
            "Split the source into smaller files or use manual review; the original upload is retained.",
            source_coverage=source_coverage,
        )


class BaseDocumentParser(ABC):
    """Abstract interface for all document parsers."""

    artifact_version = "rfq-parser-v2"
    cache_dependencies: tuple[str, ...] = ()

    def cache_profile(self) -> dict:
        """Stable parser identity; increment artifact_version when rules change."""
        return {
            "parser": f"{type(self).__module__}.{type(self).__qualname__}",
            "version": self.artifact_version,
        }

    @abstractmethod
    def parse(self, content: bytes, filename: str) -> ParsedDocumentResult:
        """Parses document bytes and returns structured line items with locators."""
        pass
