"""Deterministic text parser for pasted email bodies and plain text RFQs."""

import re
from typing import List, Optional, Tuple

from rfq_assistant.ingestion.parsers.base import (
    BaseDocumentParser,
    ParsedDocumentResult,
    ParsedLineDraft,
)
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


class TextParser(BaseDocumentParser):
    """Parses plain text RFQs and email bodies deterministically."""

    def parse(self, content: bytes, filename: str = "pasted_email.txt") -> ParsedDocumentResult:
        text = content.decode("utf-8", errors="replace")
        raw_lines = text.splitlines()

        lines: List[ParsedLineDraft] = []
        warnings: List[ExtractionWarning] = []
        line_counter = 1

        for row_idx, rline in enumerate(raw_lines, start=1):
            clean = rline.strip()
            if not clean or len(clean) < 4:
                continue

            # Ignore conversational email headers/salutations/closings
            if re.match(
                r"^(?:from:|to:|subject:|date:|hi|hello|dear|thanks|best regards|sincerely|please|urgent|confidential|synthetic notice)",
                clean,
                re.IGNORECASE,
            ):
                continue

            # Check if this line is a bullet/numbered item or contains part/quantity clues
            is_item = bool(
                re.match(r"^(?:\d+[\.\)]|\-|\*|\•)\s*", clean)
                or re.search(r"\b(?:\d+\s*(?:pcs|units?|ea|x)\b)", clean, re.IGNORECASE)
                or any(oem.lower() in clean.lower() for oem in KNOWN_OEMS)
            )

            if not is_item:
                continue

            # Check for vague item reference (Scenario 2: "the sensor from last time")
            if re.search(r"sensor from last time|same as previous|the one from last|custom bracket", clean, re.IGNORECASE):
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
                line_counter += 1
                continue

            # Parse standard item line
            parsed = self._parse_item_line(clean, filename, row_idx, line_counter)
            if parsed:
                lines.append(parsed)
                line_counter += 1

        if not lines:
            warnings.append(
                ExtractionWarning(
                    code="NO_LINES_EXTRACTED",
                    message="No line items could be extracted from text.",
                    severity="warning",
                )
            )

        return ParsedDocumentResult(lines=lines, warnings=warnings, total_lines_detected=len(lines))

    def _parse_item_line(
        self, raw_line: str, filename: str, row_idx: int, line_counter: int
    ) -> Optional[ParsedLineDraft]:
        # Strip leading bullet/index: e.g. "1. ", "- ", "3) "
        cleaned = re.sub(r"^(?:\d+[\.\)]|\-|\*|\•)\s*", "", raw_line).strip()

        # Extract quantity and unit
        qty, unit = self._extract_quantity_unit(cleaned)

        # Detect manufacturer
        detected_oem: Optional[str] = None
        for oem in KNOWN_OEMS:
            if re.search(rf"\b{re.escape(oem)}\b", cleaned, re.IGNORECASE):
                detected_oem = oem
                break

        # Extract MPN candidate
        mpn = self._extract_mpn(cleaned)

        line_warnings: List[ExtractionWarning] = []
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
    def _extract_quantity_unit(text: str) -> Tuple[Optional[float], Optional[str]]:
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
    def _extract_vague_quantity(text: str) -> Optional[float]:
        m = re.search(r"(?:about|need|around|qty:?)\s*(\d+)", text, re.IGNORECASE)
        if m:
            return float(m.group(1))
        return None

    @staticmethod
    def _extract_mpn(text: str) -> Optional[str]:
        # Tokens with uppercase letters, numbers, hyphens, slashes
        tokens = text.split()
        for t in tokens:
            cleaned = t.strip(".,;:()[]{}'\"")
            # Must contain at least one digit and one letter, or uppercase letters and hyphen
            if re.search(r"[A-Za-z]", cleaned) and re.search(r"[0-9]", cleaned) and len(cleaned) >= 4:
                # Exclude common tokens like "Plant4", "Line3", "24VDC", "4PDT"
                if cleaned.upper() in ["24VDC", "100-240VAC", "4PDT", "LINE3", "PLANT4", "NET30"]:
                    continue
                return cleaned
            elif re.search(r"^[A-Z]{2,}\-[0-9]+[A-Z0-9\-]*$", cleaned):
                return cleaned
        return None
