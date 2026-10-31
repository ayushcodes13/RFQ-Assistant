"""Deterministic parser for native text PDFs with explicit scanned document detection."""

import io
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple
import pypdf

from rfq_assistant.ingestion.parsers.base import (
    BaseDocumentParser,
    DocumentParserError,
    EvidenceSegment,
    MAX_CANDIDATE_REGIONS,
    make_coverage_entry,
    ParsedDocumentResult,
    ParsedLineDraft,
    SourceCoverageAccumulator,
)
from rfq_assistant.schemas.models import ExtractionWarning, SourceLocator
from rfq_assistant.ingestion.ocr.local_tesseract import (
    LocalOCRError, engine_profile, page_needs_ocr, recognize_page,
)

MAX_OCR_PAGES_PER_DOCUMENT = 10
MAX_CONCURRENT_OCR_PAGES = 2
log = logging.getLogger(__name__)

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

    cache_dependencies = ("pypdf", "PyMuPDF")

    def cache_profile(self) -> dict:
        return {
            **super().cache_profile(),
            "allow_ocr": self.allow_ocr,
            "ocr_profile": "pymupdf-triage+tesseract-psm6-180dpi-v1",
            "ocr_engine": engine_profile() if self.allow_ocr else "disabled",
            "max_ocr_pages": MAX_OCR_PAGES_PER_DOCUMENT,
            "max_concurrent_ocr_pages": MAX_CONCURRENT_OCR_PAGES,
        }

    def parse(self, content: bytes, filename: str) -> ParsedDocumentResult:
        started = time.perf_counter()
        try:
            reader = pypdf.PdfReader(io.BytesIO(content))
        except Exception as e:
            raise DocumentParserError(f"Corrupted or invalid PDF file: {str(e)}")

        try:
            total_pages = len(reader.pages)
        except pypdf.errors.FileNotDecryptedError:
            raise DocumentParserError(
                "Password-protected PDF detected. This file is encrypted and cannot "
                "be processed without the password. Remove the password or provide a "
                "native text PDF for manual review."
            )
        except Exception as e:
            raise DocumentParserError(f"Corrupted or invalid PDF file: {str(e)}")

        if total_pages == 0:
            raise DocumentParserError("PDF contains 0 pages.")
        if total_pages > 50:
            coverage = SourceCoverageAccumulator()
            coverage.record_unit(
                "document", SourceLocator(file_name=filename), unit_kind="pdf_document",
                processing_status="rejected", truncated=True, error_code="PDF_PAGE_LIMIT_EXCEEDED",
            )
            raise DocumentParserError(
                f"PDF page count ({total_pages}) exceeds maximum permitted limit (50 pages).",
                source_coverage=coverage.build(),
            )

        all_text = ""
        warnings: List[ExtractionWarning] = []
        source_coverage = SourceCoverageAccumulator()
        native_text_failures: set[int] = set()
        page_texts: List[Tuple[int, str]] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                text = ""
                native_text_failures.add(idx)
                warnings.append(ExtractionWarning(
                    code="PDF_NATIVE_TEXT_PAGE_FAILED",
                    message=f"Native text extraction failed on PDF page {idx}; the page was routed to bounded OCR or manual review.",
                    severity="warning",
                ))
                log.warning("[rfq_pdf] native_text=failed page=%d error=%s", idx, type(exc).__name__)
            page_texts.append((idx, text))

        ocr_text_by_page: dict[int, str] = {}
        pages_needing_ocr: List[int] = []
        page_rotations: dict[int, int] = {}
        triage_unavailable = False
        # pypdf preserves row-shaped text better for tabular RFQs. PyMuPDF is
        # used for visual triage/rendering, not to reshape native RFQ rows.
        try:
            import fitz

            visual_doc = fitz.open(stream=content, filetype="pdf")
            try:
                for page_number, (_, native_text) in enumerate(page_texts, start=1):
                    page = visual_doc[page_number - 1]
                    page_rotations[page_number] = int(page.rotation)
                    if page_number in native_text_failures or page_needs_ocr(page, native_text):
                        pages_needing_ocr.append(page_number)
            finally:
                visual_doc.close()
        except Exception as exc:
            # Classification failure must never imply that a page is safe. Fall
            # back to OCR for every page; the existing OCR page cap and errors
            # make the failure visible rather than silently accepting partial text.
            triage_unavailable = True
            pages_needing_ocr = list(range(1, total_pages + 1))
            warnings.append(ExtractionWarning(
                code="PDF_PAGE_TRIAGE_UNAVAILABLE",
                message="Image-page detection failed. Every page was sent through the bounded OCR fallback; verify OCR-derived lines against the original.",
                severity="warning",
            ))
            log.warning("[rfq_pdf] page_triage=unavailable fallback=all_pages error=%s", type(exc).__name__)

        if pages_needing_ocr and not self.allow_ocr:
            warnings.append(ExtractionWarning(
                code="OCR_REQUIRED_BUT_DISABLED",
                message=f"Image-heavy PDF pages require OCR before extraction: {', '.join(map(str, pages_needing_ocr))}.",
                severity="error",
            ))
            for page_number in pages_needing_ocr:
                source_coverage.append(make_coverage_entry(
                    f"pdf-page-{page_number}-ocr",
                    SourceLocator(file_name=filename, page_number=page_number),
                    page_texts[page_number - 1][1],
                    "ocr_error",
                    "OCR_DISABLED",
                ))
        elif pages_needing_ocr:
            if len(pages_needing_ocr) > MAX_OCR_PAGES_PER_DOCUMENT:
                warnings.append(ExtractionWarning(
                    code="OCR_PAGE_LIMIT_EXCEEDED",
                    message=f"{len(pages_needing_ocr)} pages need OCR; the local limit is {MAX_OCR_PAGES_PER_DOCUMENT}. The document needs manual handling.",
                    severity="error",
                ))
                for page_number in pages_needing_ocr:
                    source_coverage.append(make_coverage_entry(
                        f"pdf-page-{page_number}-ocr",
                        SourceLocator(file_name=filename, page_number=page_number),
                        page_texts[page_number - 1][1],
                        "ocr_error",
                        "OCR_PAGE_LIMIT_EXCEEDED",
                    ))
            else:
                # Render/OCR a small number of selected pages concurrently to
                # reduce scan latency without unbounded CPU or memory use.
                with ThreadPoolExecutor(
                    max_workers=min(MAX_CONCURRENT_OCR_PAGES, len(pages_needing_ocr))
                ) as pool:
                    future_pages = {
                        pool.submit(recognize_page, content, page_number): page_number
                        for page_number in pages_needing_ocr
                    }
                    for future in as_completed(future_pages):
                        page_number = future_pages[future]
                        try:
                            ocr_text = future.result()
                            if not ocr_text:
                                raise LocalOCRError("OCR returned no readable text for this page.")
                            # The page was selected because its native text is
                            # incomplete or the classifier failed. Prefer OCR
                            # for the whole page instead of discarding it solely
                            # because its text happens to be shorter.
                            ocr_text_by_page[page_number] = ocr_text
                        except LocalOCRError as exc:
                            warnings.append(ExtractionWarning(
                                code="OCR_PAGE_FAILED",
                                message=f"OCR could not safely read PDF page {page_number}: {exc}",
                                severity="error",
                            ))
                            source_coverage.append(make_coverage_entry(
                                f"pdf-page-{page_number}-ocr",
                                SourceLocator(file_name=filename, page_number=page_number),
                                page_texts[page_number - 1][1],
                                "ocr_error",
                                "OCR_PAGE_FAILED",
                            ))
                        except Exception as exc:
                            # A bad page must be visible and must not discard
                            # usable OCR text from the other selected pages.
                            log.warning(
                                "[rfq_pdf] page_ocr=failed page=%d error=%s",
                                page_number, type(exc).__name__,
                            )
                            warnings.append(ExtractionWarning(
                                code="OCR_PAGE_FAILED",
                                message=f"OCR could not safely read PDF page {page_number} because of an unexpected processing error. The original page needs manual review.",
                                severity="error",
                            ))
                            source_coverage.append(make_coverage_entry(
                                f"pdf-page-{page_number}-ocr",
                                SourceLocator(file_name=filename, page_number=page_number),
                                page_texts[page_number - 1][1],
                                "ocr_error",
                                "OCR_PAGE_FAILED_UNEXPECTED",
                            ))
                for page_number, ocr_text in ocr_text_by_page.items():
                    page_texts[page_number - 1] = (page_number, ocr_text)
                if ocr_text_by_page:
                    warnings.append(ExtractionWarning(
                        code="LOCAL_OCR_USED",
                        message=f"Local OCR supplied text for {len(ocr_text_by_page)} PDF page(s); verify those lines against the source image.",
                        severity="warning",
                    ))

        for page_number, page_text in page_texts:
            ocr_status = (
                "succeeded" if page_number in ocr_text_by_page
                else "failed" if page_number in pages_needing_ocr and self.allow_ocr and len(pages_needing_ocr) <= MAX_OCR_PAGES_PER_DOCUMENT
                else "limit_exceeded" if page_number in pages_needing_ocr and self.allow_ocr
                else "disabled" if page_number in pages_needing_ocr
                else "not_needed"
            )
            source_coverage.record_unit(
                f"page:{page_number}",
                SourceLocator(file_name=filename, page_number=page_number),
                unit_kind="pdf_page",
                processing_status=("needs_review" if ocr_status in {"disabled", "limit_exceeded", "failed"} else "processed"),
                is_empty=not bool(page_text.strip()),
                error_code=(
                    "PDF_NATIVE_TEXT_PAGE_FAILED" if page_number in native_text_failures
                    else f"OCR_{ocr_status.upper()}" if ocr_status in {"disabled", "limit_exceeded", "failed"}
                    else None
                ),
                ocr_status=ocr_status,
                page_rotation_degrees=page_rotations.get(page_number),
            )

        all_text = "".join(text.strip() for _, text in page_texts)

        # Check if PDF is scanned (empty text layer)
        if len(all_text.strip()) == 0:
            blocked = [w.message for w in warnings if w.severity.lower() == "error"]
            if blocked:
                raise DocumentParserError(
                    "; ".join(blocked), source_coverage=source_coverage.build()
                )
            raise DocumentParserError(
                "Scanned or image-only PDF detected. No readable text was found. "
                "Install Tesseract and enable bounded local OCR, or use the manual-entry path.",
                source_coverage=source_coverage.build(),
            )

        lines: List[ParsedLineDraft] = []
        candidate_segments: List[EvidenceSegment] = []
        line_counter = 1

        for page_num, ptext in page_texts:
            raw_lines = ptext.splitlines()
            for source_line_number, rline in enumerate(raw_lines, start=1):
                rline_clean = rline.strip()
                if not rline_clean:
                    continue
                locator = SourceLocator(
                    file_name=filename,
                    page_number=page_num,
                    row_number=source_line_number,
                    text_snippet=rline_clean[:120],
                )
                region_id = f"pdf-page-{page_num}-line-{source_line_number}"
                if len(rline_clean) < 5:
                    source_coverage.append(make_coverage_entry(
                        region_id, locator, rline, "filtered_metadata", "SHORT_PDF_TEXT_REGION"
                    ))
                    continue

                # Skip header/title lines
                if re.search(
                    r"request for quotation|issue date|ref:|customer:|^\s*(?:rfq|synthetic rfq)[-\s#]|"
                    r"^\s*(?:line|item)\s*(?:\||\s).*(?:oem|brand|description).*(?:part number|mpn|qty|quantity)|"
                    r"^\s*(?:---\s*page\s+\d+\s*---|total\b|subtotal\b|prepared by:)",
                    rline_clean,
                    re.IGNORECASE,
                ):
                    source_coverage.append(make_coverage_entry(
                        region_id, locator, rline, "filtered_metadata", "PDF_HEADER_OR_FOOTER"
                    ))
                    continue

                # Attempt to extract line item: e.g. "1 Schneider Electric LC1D09BD TeSys D Contactor 9A 24VDC 10 EA"
                parsed_draft = self._parse_pdf_line(rline_clean, filename, page_num, line_counter)
                if parsed_draft:
                    if page_num in ocr_text_by_page:
                        parsed_draft.extraction_warnings.append(ExtractionWarning(
                            code="OCR_TEXT_REVIEW",
                            message=f"This line came from OCR on PDF page {page_num}; compare it with the source image.",
                            severity="warning",
                        ))
                    lines.append(parsed_draft)
                    source_coverage.append(make_coverage_entry(
                        region_id, locator, rline, "structured_line", "DETERMINISTIC_PDF_PARSE"
                    ))
                    line_counter += 1
                else:
                    candidate_warnings = []
                    if page_num in ocr_text_by_page:
                        candidate_warnings.append(ExtractionWarning(
                            code="OCR_TEXT_REVIEW",
                            message=f"This unresolved excerpt came from OCR on PDF page {page_num}; compare it with the source image.",
                            severity="warning",
                        ))
                    candidate_segments.append(EvidenceSegment(
                        segment_id=region_id,
                        locator=locator,
                        text=rline_clean,
                        warnings=candidate_warnings,
                    ))
                    source_coverage.append(make_coverage_entry(
                        region_id, locator, rline, "review_candidate", "PDF_LINE_NOT_CONFIDENTLY_PARSED"
                    ))

        if not lines:
            warnings.append(
                ExtractionWarning(
                    code="NO_LINES_EXTRACTED",
                    message="Could not extract tabular line items from PDF text. Manual review required.",
                    severity="warning",
                )
            )

        log.info(
            "[rfq_pdf] pages=%d triage_fallback=%s ocr_selected=%d ocr_succeeded=%d lines=%d elapsed_ms=%.1f",
            total_pages,
            triage_unavailable,
            len(pages_needing_ocr),
            len(ocr_text_by_page),
            len(lines),
            (time.perf_counter() - started) * 1000,
        )
        evidence_segments = [
            EvidenceSegment(
                segment_id=f"page-{page_number}",
                locator=SourceLocator(file_name=filename, page_number=page_number),
                text=page_text,
                warnings=(
                    [ExtractionWarning(
                        code="OCR_TEXT_REVIEW",
                        message=f"This excerpt came from OCR on PDF page {page_number}; verify it against the original image.",
                        severity="warning",
                    )]
                    if page_number in ocr_text_by_page else []
                ),
            )
            for page_number, page_text in page_texts if page_text.strip()
        ]
        if len(candidate_segments) > MAX_CANDIDATE_REGIONS:
            raise DocumentParserError(
                f"Document contains more than {MAX_CANDIDATE_REGIONS} unresolved non-empty regions. Split the source into smaller files or use manual review; the original upload is retained.",
                source_coverage=source_coverage.build(),
            )
        return ParsedDocumentResult(
            lines=lines,
            warnings=warnings,
            total_lines_detected=len(lines),
            evidence_segments=evidence_segments,
            candidate_segments=candidate_segments,
            source_coverage=source_coverage.build(),
        )

    def _parse_pdf_line(
        self, raw_line: str, filename: str, page_num: int, line_counter: int
    ) -> Optional[ParsedLineDraft]:
        # Check if line contains known OEM
        detected_oem: Optional[str] = None
        for oem in KNOWN_OEMS:
            if re.search(rf"\b{re.escape(oem)}\b", raw_line, re.IGNORECASE):
                detected_oem = oem
                break

        # Check for quantity pattern. Look for "N UNIT" or "N x" patterns
        # anywhere in the line (not just at the end), since in tab-delimited
        # table rows the quantity column may appear before the manufacturer.
        qty: Optional[float] = None
        unit: Optional[str] = "EA"

        # First try end-of-line pattern (most common for free-text formats)
        qty_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(EA|PCS|UNITS|M|FT|SET)?\b\s*$", raw_line, re.IGNORECASE)
        if qty_match:
            qty = float(qty_match.group(1))
            unit = (qty_match.group(2) or "EA").upper()

        # If no quantity found at end of line, search for quantity+unit anywhere
        if qty is None:
            qty_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(EA|PCS|UNITS?|M|FT|SET|X)\b", raw_line, re.IGNORECASE)
            if qty_match:
                qty = float(qty_match.group(1))
                unit = (qty_match.group(2) or "EA").upper()
                if unit in ["PCS", "UNITS", "UNIT"]:
                    unit = "EA"

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
            # Exclude document reference numbers (e.g., RFQ-2026-001, PO-12345)
            if re.match(r"^(?:RFQ|PO|QUO|SO|QUOTE)[\-_]\d", candidate, re.IGNORECASE):
                continue
            # Exclude pole/contact specification tokens (e.g., 3-pole, SPST, DPDT)
            if re.fullmatch(r"\d+-pole|spst|spdt|dpst|dpdt|spsc|npdt", candidate, re.IGNORECASE):
                continue
            # Exclude decimal quantity+unit specification tokens (e.g., 9A, 100mA, 5VA, 24V)
            if re.fullmatch(r"\d+(?:\.\d+)?(?:A|VA|V|W|HZ|KW|MA)\d*", candidate, re.IGNORECASE):
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
