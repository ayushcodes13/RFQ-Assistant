"""Deterministic parser for CSV and Excel (XLSX) workbooks with multi-sheet support."""

import csv
import io
import re
from typing import Dict, List, Optional, Tuple
import openpyxl

from rfq_assistant.ingestion.parsers.base import (
    BaseDocumentParser,
    DocumentParserError,
    ParsedDocumentResult,
    ParsedLineDraft,
)
from rfq_assistant.schemas.models import ExtractionWarning, SourceLocator


def parse_quantity_and_unit(raw_val) -> Tuple[Optional[float], Optional[str]]:
    """Safely extracts numeric quantity and unit of measure string."""
    if raw_val is None or str(raw_val).strip() == "":
        return None, "EA"

    val_str = str(raw_val).strip()

    # Direct float/int check
    try:
        num = float(val_str)
        return num, "EA"
    except ValueError:
        pass

    # Pattern: "10 pcs", "25 x", "4 units", "100EA"
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)?", val_str)
    if match:
        qty_num = float(match.group(1))
        unit = (match.group(2) or "EA").upper()
        return qty_num, unit

    return None, "EA"


def identify_columns(headers: List[str]) -> Dict[str, int]:
    """
    Identifies column indexes for standard RFQ attributes from header labels.
    Returns mapping: attribute_name -> column_index
    """
    mapping: Dict[str, int] = {}
    patterns = {
        "mpn": [r"^part\s*(?:#|number|no)?$", r"^mpn$", r"^catalog\s*(?:#|no)?$", r"^model$", r"^p/n$", r"^item\s*code$"],
        "manufacturer": [r"^manufacturer$", r"^mfr$", r"^brand$", r"^oem$", r"^make$", r"^vendor$"],
        "quantity": [r"^qty$", r"^quantity$", r"^count$", r"^pcs$", r"^amount$"],
        "description": [r"^desc$", r"^description$", r"^item\s*description$", r"^specification$", r"^details$"],
        "unit": [r"^uom$", r"^unit$", r"^unit\s*of\s*measure$"],
        "notes": [r"^notes?$", r"^remarks?$", r"^comments?$"],
    }

    for col_idx, header in enumerate(headers):
        if not header:
            continue
        cleaned = header.strip().lower()
        for attr, regex_list in patterns.items():
            if attr not in mapping:
                for rgx in regex_list:
                    if re.search(rgx, cleaned):
                        mapping[attr] = col_idx
                        break

    return mapping


class SpreadsheetParser(BaseDocumentParser):
    """Parses CSV and multi-sheet XLSX documents into structured line drafts."""

    def parse(self, content: bytes, filename: str) -> ParsedDocumentResult:
        if filename.lower().endswith(".csv"):
            return self._parse_csv(content, filename)
        elif filename.lower().endswith(".xlsx"):
            return self._parse_xlsx(content, filename)
        else:
            raise DocumentParserError(f"Unsupported spreadsheet format for file: {filename}")

    def _parse_csv(self, content: bytes, filename: str) -> ParsedDocumentResult:
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        if len(rows) > 5000:
            raise DocumentParserError(f"CSV row count ({len(rows)}) exceeds maximum permitted limit (5000 rows).")

        if not rows:
            return ParsedDocumentResult(lines=[], warnings=[
                ExtractionWarning(code="EMPTY_CSV", message="CSV file contains no rows.")
            ])

        # Scan first 10 rows for header row
        header_row_idx = -1
        col_map: Dict[str, int] = {}
        for idx, row in enumerate(rows[:10]):
            col_map = identify_columns([str(c) for c in row])
            if "mpn" in col_map or ("description" in col_map and "quantity" in col_map):
                header_row_idx = idx
                break

        if header_row_idx == -1:
            # Headerless distributor CSVs are common. Preserve the very first
            # line as data rather than silently discarding it as a header.
            header_row_idx = -1
            col_map = {"mpn": 0, "quantity": 1, "description": 2}

        lines: List[ParsedLineDraft] = []
        warnings: List[ExtractionWarning] = []
        line_counter = 1

        for row_idx, row in enumerate(rows[header_row_idx + 1:], start=header_row_idx + 2):
            if not row or all(str(c).strip() == "" for c in row):
                continue  # Skip completely empty rows

            row_text = " | ".join(str(c).strip() for c in row if str(c).strip())
            locator = SourceLocator(
                file_name=filename,
                sheet_name="Default",
                row_number=row_idx,
                text_snippet=row_text[:120],
            )

            mpn = self._get_col_value(row, col_map.get("mpn"))
            oem = self._get_col_value(row, col_map.get("manufacturer"))
            desc = self._get_col_value(row, col_map.get("description"))
            raw_qty = self._get_col_value(row, col_map.get("quantity"))
            raw_unit = self._get_col_value(row, col_map.get("unit"))
            notes = self._get_col_value(row, col_map.get("notes"))

            qty, parsed_unit = parse_quantity_and_unit(raw_qty)
            unit = raw_unit or parsed_unit or "EA"

            line_warnings: List[ExtractionWarning] = []
            if qty is None:
                line_warnings.append(
                    ExtractionWarning(
                        code="MISSING_QUANTITY",
                        message=f"Missing or unparseable quantity in row {row_idx}",
                        severity="warning",
                    )
                )

            if not mpn and not desc:
                if not oem and qty is None and not notes:
                    continue
                line_warnings.append(
                    ExtractionWarning(
                        code="MISSING_PART_REFERENCE",
                        message=f"Cannot identify requested part on row {row_idx}; review original row.",
                        severity="warning",
                    )
                )

            lines.append(
                ParsedLineDraft(
                    line_number=line_counter,
                    raw_text=row_text,
                    source_locator=locator,
                    requested_manufacturer=oem,
                    requested_mpn=mpn,
                    description=desc,
                    quantity=qty,
                    unit=unit,
                    notes=notes,
                    extraction_warnings=line_warnings,
                )
            )
            line_counter += 1

        if not lines:
            warnings.append(ExtractionWarning(
                code="NO_LINES_EXTRACTED",
                message="No RFQ line items found in CSV. Manual entry or a corrected file is required.",
                severity="error",
            ))

        return ParsedDocumentResult(lines=lines, warnings=warnings, total_lines_detected=len(lines))

    def _parse_xlsx(self, content: bytes, filename: str) -> ParsedDocumentResult:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
        if len(wb.sheetnames) > 20:
            raise DocumentParserError(f"Spreadsheet sheet count ({len(wb.sheetnames)}) exceeds maximum permitted limit (20 sheets).")

        lines: List[ParsedLineDraft] = []
        warnings: List[ExtractionWarning] = []
        line_counter = 1

        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            if ws.max_row and ws.max_row > 5000:
                raise DocumentParserError(f"Spreadsheet sheet '{sheet_name}' row count ({ws.max_row}) exceeds limit (5000 rows).")
            if ws.max_column and ws.max_column > 100:
                raise DocumentParserError(f"Spreadsheet sheet '{sheet_name}' column count ({ws.max_column}) exceeds limit (100 columns).")

            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows:
                continue

            # Detect header row in first 10 rows
            header_row_idx = -1
            col_map: Dict[str, int] = {}
            for idx, row in enumerate(all_rows[:10]):
                if not row:
                    continue
                col_map = identify_columns([str(c) if c is not None else "" for c in row])
                if "mpn" in col_map or ("description" in col_map and "quantity" in col_map):
                    header_row_idx = idx
                    break

            if header_row_idx == -1:
                # Check if sheet contains line-item-like data
                continue

            for row_idx, row in enumerate(all_rows[header_row_idx + 1:], start=header_row_idx + 2):
                if not row or all(c is None or str(c).strip() == "" for c in row):
                    continue

                row_text = " | ".join(str(c).strip() for c in row if c is not None and str(c).strip())
                locator = SourceLocator(
                    file_name=filename,
                    sheet_name=sheet_name,
                    row_number=row_idx,
                    text_snippet=row_text[:120],
                )

                mpn = self._get_col_value(row, col_map.get("mpn"))
                oem = self._get_col_value(row, col_map.get("manufacturer"))
                desc = self._get_col_value(row, col_map.get("description"))
                raw_qty = self._get_col_value(row, col_map.get("quantity"))
                raw_unit = self._get_col_value(row, col_map.get("unit"))
                notes = self._get_col_value(row, col_map.get("notes"))

                qty, parsed_unit = parse_quantity_and_unit(raw_qty)
                unit = raw_unit or parsed_unit or "EA"

                line_warnings: List[ExtractionWarning] = []
                if qty is None:
                    line_warnings.append(
                        ExtractionWarning(
                            code="MISSING_QUANTITY",
                            message=f"Missing or unparseable quantity in row {row_idx} of sheet '{sheet_name}'",
                            severity="warning",
                        )
                    )

                if not mpn and not desc:
                    if not oem and qty is None and not notes:
                        continue
                    line_warnings.append(
                        ExtractionWarning(
                            code="MISSING_PART_REFERENCE",
                            message=f"Cannot identify requested part on row {row_idx} of sheet '{sheet_name}'.",
                            severity="warning",
                        )
                    )

                lines.append(
                    ParsedLineDraft(
                        line_number=line_counter,
                        raw_text=row_text,
                        source_locator=locator,
                        requested_manufacturer=oem,
                        requested_mpn=mpn,
                        description=desc,
                        quantity=qty,
                        unit=unit,
                        notes=notes,
                        extraction_warnings=line_warnings,
                    )
                )
                line_counter += 1

        if not lines:
            warnings.append(
                ExtractionWarning(
                    code="NO_LINES_EXTRACTED",
                    message="No valid part lines could be extracted from workbook sheets.",
                    severity="error",
                )
            )

        return ParsedDocumentResult(lines=lines, warnings=warnings, total_lines_detected=len(lines))

    @staticmethod
    def _get_col_value(row: Tuple, col_idx: Optional[int]) -> Optional[str]:
        if col_idx is None or col_idx >= len(row):
            return None
        val = row[col_idx]
        if val is None:
            return None
        val_str = str(val).strip()
        return val_str if val_str != "" else None
