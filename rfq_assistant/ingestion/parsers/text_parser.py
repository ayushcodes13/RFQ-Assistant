"""Deterministic text parser for pasted email bodies and plain text RFQs."""

import re

from rfq_assistant.ingestion.parsers.base import (
    BaseDocumentParser,
    EvidenceSegment,
    ParsedDocumentResult,
    ParsedLineDraft,
    SourceCoverageAccumulator,
    enforce_candidate_region_limit,
    make_coverage_entry,
)
from rfq_assistant.matching.normalizer import normalize_manufacturer, normalize_mpn
from rfq_assistant.schemas.models import ExtractionWarning, SourceLocator

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
VAGUE_ITEM_REFERENCE = r"sensor from last time|same as previous|the one from last|custom bracket|same .{1,50} as last time"


def _is_electrical_specification_token(value: str) -> bool:
    """Recognize quantity-like electrical specs without backtracking regexes."""
    token = value.upper()
    index = 0
    while index < len(token) and "0" <= token[index] <= "9":
        index += 1
    if index == 0:
        return False

    if index < len(token) and token[index] == ".":
        index += 1
        decimal_start = index
        while index < len(token) and "0" <= token[index] <= "9":
            index += 1
        if index == decimal_start:
            return False

    units = ("VA", "HZ", "KW", "MA", "V", "W", "A")
    suffix = next((unit for unit in units if token.startswith(unit, index)), None)
    if suffix is None:
        return False
    index += len(suffix)
    while index < len(token) and "0" <= token[index] <= "9":
        index += 1
    return index == len(token)


def _is_prefixed_numeric_mpn(value: str) -> bool:
    """Recognize PREFIX-123 style identifiers without regex on untrusted text."""
    prefix, separator, suffix = value.partition("-")
    if not separator or len(prefix) < 2 or not prefix.isalpha() or not prefix.isupper():
        return False
    index = 0
    while index < len(suffix) and "0" <= suffix[index] <= "9":
        index += 1
    if index == 0:
        return False
    return all(char.isascii() and char.isalnum() or char == "-" for char in suffix[index:])


class TextParser(BaseDocumentParser):
    """Parses plain text RFQs and email bodies deterministically."""

    def parse(self, content: bytes, filename: str = "pasted_email.txt") -> ParsedDocumentResult:
        text = content.decode("utf-8", errors="replace")
        raw_lines = text.splitlines()

        lines: list[ParsedLineDraft] = []
        warnings: list[ExtractionWarning] = []
        candidate_segments: list[EvidenceSegment] = []
        source_coverage = SourceCoverageAccumulator()
        source_coverage.record_unit(
            "document", SourceLocator(file_name=filename), unit_kind="text_document", is_empty=True,
        )
        line_counter = 1
        in_signature = False

        for row_idx, rline in enumerate(raw_lines, start=1):
            clean = rline.strip()
            if not clean:
                continue
            locator = SourceLocator(file_name=filename, row_number=row_idx, text_snippet=clean[:120])

            def record(disposition: str, rule_code: str) -> None:
                source_coverage.append(make_coverage_entry(
                    f"text-row-{row_idx}", locator, rline, disposition, rule_code
                ))

            if len(clean) < 4:
                record("filtered_metadata", "SHORT_TEXT_REGION")
                continue

            # Unwrap quoted email lines before classifying them so forwarded
            # item rows retain their numbered-list structure.
            clean = re.sub(r"^(?:>\s*)+", "", clean).strip()

            # Strip common email inquiry prefixes like 'Please quote:' or 'Urgent:'
            stripped = re.sub(
                r"^(?:please\s+(?:quote|quote\s+for|provide\s+pricing\s+for|quote\s+us\s+on)?\s*:?|urgent\s*[:-]?\s*)",
                "",
                clean,
                flags=re.IGNORECASE,
            ).strip()
            if stripped:
                clean = stripped

            if re.match(
                r"^(?:from:|to:|cc:|subject:|date:|hi\b|hello\b|dear\b|thanks\b|best regards\b|sincerely\b|confidential\b|synthetic notice\b)",
                clean,
                re.IGNORECASE,
            ):
                record("filtered_metadata", "EMAIL_HEADER_OR_GREETING")
                if re.match(r"^(?:thanks|best regards|sincerely)\b", clean, re.IGNORECASE):
                    in_signature = True
                continue

            if in_signature:
                record("filtered_metadata", "EMAIL_SIGNATURE")
                continue
            if self._is_known_non_item_text(clean):
                record("filtered_metadata", "KNOWN_EMAIL_METADATA")
                continue

            # Check if this line contains component, quantity, or item clues
            has_item_indicator = bool(
                re.match(r"^(?:\d+[\.\)]|\-|\*|\•)\s*", clean)
                or re.search(r"\b(?:\d+\s*(?:pcs|units?|ea|x)\b)", clean, re.IGNORECASE)
                or any(oem.lower() in clean.lower() for oem in KNOWN_OEMS)
                or re.search(r"\b[A-Z0-9]{3,}[-_][A-Z0-9]+\b", clean)
                or re.search(VAGUE_ITEM_REFERENCE, clean, re.IGNORECASE)
            )

            if not has_item_indicator:
                # Narrow email metadata/salutations were filtered above. Keep
                # every other non-empty region so unfamiliar wording reaches
                # grounded fallback or the explicit manual-review path.
                candidate_segments.append(EvidenceSegment(
                    segment_id=f"candidate-text-{row_idx}",
                    locator=SourceLocator(file_name=filename, row_number=row_idx, text_snippet=clean[:120]),
                    text=clean,
                ))
                record("review_candidate", "NO_DETERMINISTIC_ITEM_INDICATOR")
                continue

            # Do not let a recognizable part on a line hide a second vague
            # item such as "and the same relay as last time". Route the whole
            # region to grounded/manual review so the tail is not lost.
            if re.search(
                VAGUE_ITEM_REFERENCE,
                clean,
                re.IGNORECASE,
            ) and re.search(r"\b[A-Z0-9]{3,}[-_][A-Z0-9]+\b|\b\d{5,}\b", clean):
                candidate_segments.append(EvidenceSegment(
                    segment_id=f"candidate-text-{row_idx}",
                    locator=locator,
                    text=clean,
                ))
                record("review_candidate", "KNOWN_AND_VAGUE_ITEMS_IN_ONE_REGION")
                continue


            # Check for vague item reference (Scenario 2: "the sensor from last time")
            if re.search(VAGUE_ITEM_REFERENCE, clean, re.IGNORECASE):
                locator = SourceLocator(
                    file_name=filename,
                    row_number=row_idx,
                    text_snippet=clean[:120],
                )
                lines.append(
                    ParsedLineDraft(
                        line_number=line_counter,
                        raw_text=clean,
                        source_locator=locator,
                        requested_manufacturer=None,
                        requested_mpn=None,
                        description=clean,
                        quantity=self._extract_vague_quantity(clean),
                        unit="EA",
                        notes="Vague customer reference",
                        extraction_warnings=[
                            ExtractionWarning(
                                code="UNKNOWN_PART_REFERENCE",
                                message="Vague item reference requires customer clarification (e.g. part number, photo, or drawing).",
                                severity="warning",
                            )
                        ],
                    )
                )
                record("structured_line", "VAGUE_ITEM_REFERENCE_PRESERVED")
                line_counter += 1
                continue

            # Parse standard item line
            parsed = self._parse_item_line(clean, filename, row_idx, line_counter)
            if parsed:
                lines.append(parsed)
                record("structured_line", "DETERMINISTIC_TEXT_PARSE")
                line_counter += 1
            else:
                candidate_segments.append(EvidenceSegment(
                    segment_id=f"candidate-text-{row_idx}",
                    locator=SourceLocator(file_name=filename, row_number=row_idx, text_snippet=clean[:120]),
                    text=clean,
                ))
                record("review_candidate", "DETERMINISTIC_PARSE_UNRESOLVED")

        # Repeated manufacturer+MPN rows with different quantities may be
        # separate requests or a correction in an email thread. Preserve all
        # rows and require a human to decide; never choose the latest/first one.
        by_identity: dict[tuple[str, str], list[ParsedLineDraft]] = {}
        for line in lines:
            if not line.requested_mpn:
                continue
            identity = (
                normalize_manufacturer(line.requested_manufacturer or ""),
                normalize_mpn(line.requested_mpn),
            )
            by_identity.setdefault(identity, []).append(line)
        for duplicates in by_identity.values():
            quantities = {(line.quantity, line.unit) for line in duplicates}
            if len(duplicates) > 1 and len(quantities) > 1:
                for line in duplicates:
                    line.extraction_warnings.append(ExtractionWarning(
                        code="REPEATED_PART_QUANTITY_REQUIRES_REVIEW",
                        message="This manufacturer and part number appears with different quantities in the source. Review both locations to determine whether one corrects the other or they are separate request lines.",
                        severity="error",
                    ))

        if not lines:
            warnings.append(
                ExtractionWarning(
                    code="NO_LINES_EXTRACTED",
                    message="No line items could be extracted from text.",
                    severity="warning",
                )
            )

        enforce_candidate_region_limit(candidate_segments, source_coverage.build())

        return ParsedDocumentResult(
            lines=lines,
            warnings=warnings,
            total_lines_detected=len(lines),
            candidate_segments=candidate_segments,
            source_coverage=source_coverage.build(),
        )

    def _parse_item_line(
        self, raw_line: str, filename: str, row_idx: int, line_counter: int
    ) -> ParsedLineDraft | None:
        # Strip leading bullet/index: e.g. "1. ", "- ", "3) "
        cleaned = re.sub(r"^(?:\d+[\.\)]|\-|\*|\•)\s*", "", raw_line).strip()

        # Extract quantity and unit
        qty, unit = self._extract_quantity_unit(cleaned)

        # Detect manufacturer
        detected_oem: str | None = None
        for oem in KNOWN_OEMS:
            if re.search(rf"\b{re.escape(oem)}\b", cleaned, re.IGNORECASE):
                detected_oem = oem
                break

        # Extract MPN candidate
        mpn = self._extract_mpn(cleaned)

        line_warnings: list[ExtractionWarning] = []
        if qty is None:
            line_warnings.append(
                ExtractionWarning(
                    code="MISSING_QUANTITY",
                    message=f"Line {line_counter} does not have a recognizable quantity.",
                    severity="warning",
                )
            )

        if not detected_oem and not mpn:
            return None

        locator = SourceLocator(
            file_name=filename,
            row_number=row_idx,
            text_snippet=raw_line[:120],
        )

        return ParsedLineDraft(
            line_number=line_counter,
            raw_text=raw_line,
            source_locator=locator,
            requested_manufacturer=detected_oem,
            requested_mpn=mpn,
            description=cleaned,
            quantity=qty,
            unit=unit or "EA",
            extraction_warnings=line_warnings,
        )

    @staticmethod
    def _is_known_non_item_text(text: str) -> bool:
        """Discard narrow email context patterns while retaining unknown prose."""
        return bool(re.match(
            r"^(?:synthetic\b|customer\s*:|rfq\s*ref\s*:|date\s*:|"
            r"(?:please\s+)?provide unit price and stock for\s*:|could you please quote .*following items|please quote the following items:?|"
            r"also,? our .* added:?|i can confirm the above\b|please include pricing\b|"
            r"the following(?::| items:)?|find below the list\b|some items may have alternative manufacturers\b|"
            r"for the exact mpns listed\b|please confirm (?:current )?pricing\b|confirm current pricing\b|please let us know\b|"
            r"please provide pricing and lead time\b|[-_ ]{3,})",
            text,
            re.IGNORECASE,
        ))

    @staticmethod
    def _extract_quantity_unit(text: str) -> tuple[float | None, str | None]:
        # Pattern 1: "10 pcs of", "4 units", "5 pcs", "12 EA of", "25x"
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:x|pcs|units?|ea|m|ft|set)\b", text, re.IGNORECASE)
        if m:
            qty = float(m.group(1))
            unit_str = re.search(r"\b(pcs|units?|ea|m|ft|set)\b", text, re.IGNORECASE)
            unit = unit_str.group(1).upper() if unit_str else "EA"
            if unit in ["PCS", "UNITS", "UNIT"]:
                unit = "EA"
            return qty, unit

        # Pattern 2: leading number "10 Schneider Electric..."
        m2 = re.match(r"^(\d+(?:\.\d+)?)\s+", text)
        if m2:
            return float(m2.group(1)), "EA"

        return None, "EA"

    @staticmethod
    def _extract_vague_quantity(text: str) -> float | None:
        m = re.search(r"(?:about|need|around|qty:?)\s*(\d+)", text, re.IGNORECASE)
        if m:
            return float(m.group(1))
        return None

    @staticmethod
    def _extract_mpn(text: str) -> str | None:
        # Tokens with uppercase letters, numbers, hyphens, slashes
        tokens = text.split()
        for t in tokens:
            cleaned = t.strip(".,;:()[]{}'\"")
            # Exclude document reference numbers (e.g., RFQ-2026-001, PO-12345)
            if re.match(r"^(?:RFQ|PO|QUO|SO|QUOTE)[\-_]\d", cleaned, re.IGNORECASE):
                continue
            # Must contain at least one digit and one letter, or uppercase letters and hyphen
            if re.search(r"[A-Za-z]", cleaned) and re.search(r"[0-9]", cleaned) and len(cleaned) >= 4:
                # Exclude common tokens like "Plant4", "Line3", "24VDC", "4PDT"
                if cleaned.upper() in ["24VDC", "100-240VAC", "4PDT", "LINE3", "PLANT4", "NET30"]:
                    continue
                # Exclude voltage/amperage specification tokens (e.g., 24VDC, 100-240VAC)
                if re.fullmatch(r"\d+(?:V(?:AC|DC)?|A|HZ|W|KW)", cleaned, re.IGNORECASE):
                    continue
                # Exclude pole/contact specification tokens (e.g., 3-pole, 2NO, SPST, DPDT)
                if re.fullmatch(r"\d+-pole|spst|spdt|dpst|dpdt|spsc|npdt", cleaned, re.IGNORECASE):
                    continue
                # Exclude decimal quantity+unit specification tokens (e.g., 9A, 100mA, 5VA, 24V)
                if _is_electrical_specification_token(cleaned):
                    continue
                return cleaned
            # Allow numeric-only MPNs (e.g., Phoenix Contact 2900364) when long enough
            elif (cleaned.isdigit() and len(cleaned) >= 5) or _is_prefixed_numeric_mpn(cleaned):
                return cleaned
        return None
