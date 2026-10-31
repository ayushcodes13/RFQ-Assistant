"""Deterministic parser for native text PDFs with explicit scanned document detection."""

import io
import re
from typing import List, Optional, Tuple
import pypdf

from rfq_assistant.ingestion.parsers.base import (
    BaseDocumentParser,
    DocumentParserError,
    ParsedDocumentResult,
    ParsedLineDraft,
)
from rfq_assistant.schemas.models import ExtractionWarning, SourceLocator

# Known industrial OEMs for line identification
KNOWN_OEMS = [
    "Schneider Electric",
    "Schneider",
    "Siemens",
    "Omron",
    "Eaton",
    "Phoenix Contact",
    "Acme Industrial",
    "Apex Automation",
    "Delta Electronics",
    "Allen-Bradley",
    "ABB",
]


class PDFParser(BaseDocumentParser):
    """Deterministic parser for native PDFs. Safely detects scanned PDFs and rejects them when OCR is disabled."""

    def __init__(self, allow_ocr: bool = False):
        self.allow_ocr = allow_ocr

    def parse(self, content: bytes, filename: str) -> ParsedDocumentResult:
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
        except Exception as e:
            raise DocumentParserError(f"Corrupted or invalid PDF file: {str(e)}")

        total_pages = len(reader.pages)
        if total_pages == 0:
            raise DocumentParserError("PDF contains 0 pages.")
        if total_pages > 50:
            raise DocumentParserError(f"PDF page count ({total_pages}) exceeds maximum permitted limit (50 pages).")

        all_text = ""
        page_texts: List[Tuple[int, str]] = []
        for idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            page_texts.append((idx, text))
            all_text += text.strip()

        # Check if PDF is scanned (empty text layer)
        if len(all_text.strip()) == 0:
            if not self.allow_ocr:
                raise DocumentParserError(
                    "Scanned or image-only PDF detected. OCR is disabled by policy. "
                    "Please provide a native PDF, spreadsheet, or paste lines manually."
                )
            else:
                # OCR feature flag placeholder
                raise DocumentParserError("OCR engine is not configured in this local environment.")

        lines: List[ParsedLineDraft] = []
        warnings: List[ExtractionWarning] = []
        line_counter = 1

        for page_num, ptext in page_texts:
            raw_lines = ptext.splitlines()
            for rline in raw_lines:
                rline_clean = rline.strip()
                if not rline_clean or len(rline_clean) < 5:
                    continue

                # Skip header/title lines
                if re.search(r"request for quotation|issue date|ref:|line\s+oem", rline_clean, re.IGNORECASE):
                    continue

                # Attempt to extract line item: e.g. "1 Schneider Electric LC1D09BD TeSys D Contactor 9A 24VDC 10 EA"
                parsed_draft = self._parse_pdf_line(rline_clean, filename, page_num, line_counter)
                if parsed_draft:
                    lines.append(parsed_draft)
                    line_counter += 1

        if not lines:
            warnings.append(
                ExtractionWarning(
                    code="NO_LINES_EXTRACTED",
                    message="Could not extract tabular line items from PDF text. Manual review required.",
                    severity="warning",
                )
            )

        return ParsedDocumentResult(lines=lines, warnings=warnings, total_lines_detected=len(lines))

    def _parse_pdf_line(
        self, raw_line: str, filename: str, page_num: int, line_counter: int
    ) -> Optional[ParsedLineDraft]:
        # Check if line contains known OEM
        detected_oem: Optional[str] = None
        for oem in KNOWN_OEMS:
            if re.search(rf"\b{re.escape(oem)}\b", raw_line, re.IGNORECASE):
                detected_oem = oem
                break

        # Check for quantity pattern at end or middle: e.g. "10 EA", "4 PCS", "20"
        qty: Optional[float] = None
        unit: Optional[str] = "EA"

        qty_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(EA|PCS|UNITS|M|FT|SET)?\b\s*$", raw_line, re.IGNORECASE)
        if qty_match:
            qty = float(qty_match.group(1))
            unit = (qty_match.group(2) or "EA").upper()

        # Prefer an identifier after the detected manufacturer. This avoids
        # mistaking later specification tokens (for example, 24VDC) for the
        # requested part number. Some legitimate MPNs are digits-only, so
        # allow those when they occur after the manufacturer and are long
        # enough to be an identifier.
        search_text = raw_line
        if detected_oem:
            manufacturer = re.search(re.escape(detected_oem), raw_line, re.IGNORECASE)
            if manufacturer:
                search_text = raw_line[manufacturer.end():]

        tokens = re.findall(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9._/-]{2,}(?![A-Za-z0-9])", search_text)
        mpn = None
        for token in tokens:
            candidate = token.strip(".,;:()")
            if not any(char.isdigit() for char in candidate):
                continue
            if re.fullmatch(r"\d+(?:V(?:AC|DC)?|A|HZ|W|KW)", candidate, re.IGNORECASE):
                continue
            if candidate.isdigit() and len(candidate) < 5:
                continue
            mpn = candidate
            break

        if not detected_oem and not mpn:
            return None

        locator = SourceLocator(
            file_name=filename,
            page_number=page_num,
            text_snippet=raw_line[:120],
        )

        line_warnings: List[ExtractionWarning] = []
        if qty is None:
            line_warnings.append(
                ExtractionWarning(
                    code="MISSING_QUANTITY",
                    message=f"Missing quantity on page {page_num}",
                    severity="warning",
                )
            )

        return ParsedLineDraft(
            line_number=line_counter,
            raw_text=raw_line,
            source_locator=locator,
            requested_manufacturer=detected_oem,
            requested_mpn=mpn,
            description=raw_line,
            quantity=qty,
            unit=unit,
            extraction_warnings=line_warnings,
        )
