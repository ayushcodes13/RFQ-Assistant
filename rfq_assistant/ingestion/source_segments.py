"""Convert supported RFQ inputs into bounded, locatable text excerpts."""

from __future__ import annotations

import csv
import io
from typing import List

import openpyxl
import pypdf

from rfq_assistant.ingestion.parsers.base import EvidenceSegment
from rfq_assistant.schemas.enums import SourceType
from rfq_assistant.schemas.models import ExtractionWarning, SourceLocator

MAX_SEGMENTS = 500
MAX_SEGMENT_CHARACTERS = 40_000
MAX_SOURCE_ROWS_PER_SHEET = 20_000


class SourceSegmentLimitError(ValueError):
    """The source is too large to safely construct an LLM fallback prompt."""


def _append_bounded(segments: List[EvidenceSegment], segment: EvidenceSegment, total_chars: int) -> int:
    next_total = total_chars + len(segment.text)
    if len(segments) >= MAX_SEGMENTS or next_total > MAX_SEGMENT_CHARACTERS:
        raise SourceSegmentLimitError(
            "Source exceeds the bounded LLM fallback excerpt limit; use manual review or a smaller input."
        )
    segments.append(segment)
    return next_total


def source_segments(content: bytes, filename: str, source_type: SourceType) -> List[EvidenceSegment]:
    """Return source excerpts for fallback extraction without executing content.

    Spreadsheet formulas are preserved as formula strings, never evaluated.
    Callers should pass only the relevant segments to an external model.
    """
    if source_type == SourceType.PDF_NATIVE:
        reader = pypdf.PdfReader(io.BytesIO(content))
        segments: List[EvidenceSegment] = []
        total_chars = 0
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                total_chars = _append_bounded(segments, EvidenceSegment(
                    segment_id=f"page-{page_number}",
                    locator=SourceLocator(file_name=filename, page_number=page_number),
                    text=text,
                ), total_chars)
        return segments

    if source_type == SourceType.CSV:
        text = content.decode("utf-8", errors="replace")
        segments = []
        total_chars = 0
        for row_number, row in enumerate(csv.reader(io.StringIO(text)), start=1):
            row_text = " | ".join(str(value).strip() for value in row if str(value).strip())
            if row_text:
                total_chars = _append_bounded(segments, EvidenceSegment(
                    segment_id=f"row-{row_number}",
                    locator=SourceLocator(file_name=filename, sheet_name="Default", row_number=row_number),
                    text=row_text,
                ), total_chars)
        return segments

    if source_type == SourceType.XLSX:
        if filename.lower().endswith(".xls"):
            from rfq_assistant.ingestion.xls_conversion import convert_legacy_xls

            content = convert_legacy_xls(content)
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=False, read_only=True)
        try:
            segments: List[EvidenceSegment] = []
            total_chars = 0
            for sheet in workbook.worksheets:
                hidden = sheet.sheet_state != "visible"
                for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                    if row_number > MAX_SOURCE_ROWS_PER_SHEET:
                        raise SourceSegmentLimitError(
                            "Workbook exceeds the bounded LLM fallback row limit; use manual review or a smaller input."
                        )
                    values = [str(value).strip() for value in row if value is not None and str(value).strip()]
                    if values:
                        total_chars = _append_bounded(segments, EvidenceSegment(
                            segment_id=f"{sheet.title}-row-{row_number}",
                            locator=SourceLocator(file_name=filename, sheet_name=sheet.title, row_number=row_number),
                            text=" | ".join(values),
                            warnings=(
                                [ExtractionWarning(
                                    code="HIDDEN_SHEET_REVIEW",
                                    message=f"This source row came from hidden sheet '{sheet.title}'; verify it is part of the RFQ.",
                                    severity="warning",
                                )]
                                if hidden else []
                            ),
                        ), total_chars)
            return segments
        finally:
            workbook.close()

    # EMAIL_TEXT and TXT share the same line-oriented source representation.
    text = content.decode("utf-8", errors="replace")
    segments = []
    total_chars = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            total_chars = _append_bounded(segments, EvidenceSegment(
                segment_id=f"line-{line_number}",
                locator=SourceLocator(file_name=filename, row_number=line_number),
                text=line,
            ), total_chars)
    return segments
