"""Deterministic parser for CSV and Excel (XLSX) workbooks with multi-sheet support."""

import csv
import io
import itertools
import re
from bisect import bisect_right
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import openpyxl
from openpyxl.utils import get_column_letter

from rfq_assistant.ingestion.parsers.base import (
    BaseDocumentParser,
    DocumentParserError,
    EvidenceSegment,
    enforce_candidate_region_limit,
    make_coverage_entry,
    ParsedDocumentResult,
    ParsedLineDraft,
    SourceCoverageAccumulator,
)
from rfq_assistant.schemas.models import ExtractionWarning, SourceLocator
from rfq_assistant.ingestion.excel_values import (
    format_excel_value,
    numeric_identifier_precision_risk,
    render_excel_cell,
)
from rfq_assistant.ingestion.excel_visibility import (
    VerticalMerge,
    read_hidden_dimensions,
)


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

    artifact_version = "rfq-spreadsheet-v5"

    cache_dependencies = ("openpyxl",)

    def parse(self, content: bytes, filename: str) -> ParsedDocumentResult:
        if filename.lower().endswith(".csv"):
            return self._parse_csv(content, filename)
        elif filename.lower().endswith(".xls"):
            return self._parse_xls(content, filename)
        elif filename.lower().endswith(".xlsx"):
            return self._parse_xlsx(content, filename)
        else:
            raise DocumentParserError(f"Unsupported spreadsheet format for file: {filename}")

    def _parse_xls(self, content: bytes, filename: str) -> ParsedDocumentResult:
        """Convert legacy BIFF files in a bounded subprocess, then use XLSX parsing."""
        from rfq_assistant.ingestion.xls_conversion import (
            LegacyXLSConversionError,
            convert_legacy_xls,
        )

        try:
            converted = convert_legacy_xls(content)
        except LegacyXLSConversionError as exc:
            raise DocumentParserError(str(exc)) from exc
        result = self._parse_xlsx(converted, filename)
        result.warnings.insert(0, ExtractionWarning(
            code="LEGACY_XLS_CONVERTED",
            message="This legacy Excel file was converted in an isolated temporary profile before parsing. Verify the five sampled rows against the original workbook.",
            severity="warning",
        ))
        return result

    def _parse_csv(self, content: bytes, filename: str) -> ParsedDocumentResult:
        text = content.decode("utf-8", errors="replace")
        reader = iter(csv.reader(io.StringIO(text)))
        header_sample = list(itertools.islice(reader, 10))
        if not header_sample:
            source_coverage = SourceCoverageAccumulator()
            source_coverage.record_unit(
                "document", SourceLocator(file_name=filename), unit_kind="csv_document",
                is_empty=True,
            )
            return ParsedDocumentResult(lines=[], warnings=[
                ExtractionWarning(code="EMPTY_CSV", message="CSV file contains no rows.")
            ], source_coverage=source_coverage.build())

        # Scan first 10 rows for header row
        header_row_idx = -1
        col_map: Dict[str, int] = {}
        for idx, row in enumerate(header_sample):
            col_map = identify_columns([str(c) for c in row])
            if "mpn" in col_map or ("description" in col_map and "quantity" in col_map):
                header_row_idx = idx
                break

        source_coverage = SourceCoverageAccumulator()
        source_coverage.record_unit(
            "sheet:Default",
            SourceLocator(file_name=filename, sheet_name="Default"),
            unit_kind="csv_table", is_empty=True,
        )

        warnings: List[ExtractionWarning] = []
        if header_row_idx == -1:
            # Headerless distributor CSVs are common. Preserve the very first
            # line as data rather than silently discarding it as a header.
            col_map = {"mpn": 0, "quantity": 1, "description": 2}
            data_rows = itertools.chain(header_sample, reader)
            first_row_number = 1
            warnings.append(ExtractionWarning(
                code="HEADERLESS_CSV_LAYOUT_GUESSED",
                message="No recognized CSV header was found. The first three columns are treated as part, quantity, and description; verify the rows.",
                severity="warning",
            ))
        else:
            for skipped_idx, skipped_row in enumerate(header_sample[: header_row_idx + 1], start=1):
                skipped_text = " | ".join(str(value).strip() for value in skipped_row if str(value).strip())
                if skipped_text:
                    source_coverage.append(make_coverage_entry(
                        f"csv-row-{skipped_idx}",
                        SourceLocator(file_name=filename, sheet_name="Default", row_number=skipped_idx,
                                      text_snippet=skipped_text[:120]),
                        skipped_text,
                        "filtered_metadata",
                        "CSV_PREAMBLE_OR_HEADER",
                    ))
            data_rows = itertools.chain(header_sample[header_row_idx + 1:], reader)
            first_row_number = header_row_idx + 2

        lines: List[ParsedLineDraft] = []
        candidate_segments: List[EvidenceSegment] = []
        line_counter = 1

        for row_idx, row in enumerate(data_rows, start=first_row_number):
            if row_idx > 5000:
                source_coverage.record_unit(
                    "sheet:Default", SourceLocator(file_name=filename, sheet_name="Default"),
                    unit_kind="csv_table", processing_status="rejected", truncated=True,
                    error_code="CSV_ROW_LIMIT_EXCEEDED",
                )
                raise DocumentParserError(
                    "CSV row count exceeds maximum permitted limit (5000 rows).",
                    source_coverage=source_coverage.build(),
                )
            if len(row) > 100:
                source_coverage.record_unit(
                    "sheet:Default", SourceLocator(file_name=filename, sheet_name="Default"),
                    unit_kind="csv_table", processing_status="rejected", truncated=True,
                    error_code="CSV_COLUMN_LIMIT_EXCEEDED",
                )
                raise DocumentParserError(
                    f"CSV row {row_idx} column count ({len(row)}) exceeds maximum permitted limit (100 columns).",
                    source_coverage=source_coverage.build(),
                )
            if not row or all(str(c).strip() == "" for c in row):
                continue  # Skip completely empty rows

            row_text = " | ".join(str(c).strip() for c in row if str(c).strip())
            locator = SourceLocator(
                file_name=filename,
                sheet_name="Default",
                row_number=row_idx,
                text_snippet=row_text[:120],
            )
            region_id = f"csv-row-{row_idx}"

            mpn = self._get_col_value(row, col_map.get("mpn"))
            oem = self._get_col_value(row, col_map.get("manufacturer"))
            desc = self._get_col_value(row, col_map.get("description"))
            raw_qty = self._get_col_value(row, col_map.get("quantity"))
            raw_unit = self._get_col_value(row, col_map.get("unit"))
            notes = self._get_col_value(row, col_map.get("notes"))

            qty, parsed_unit = parse_quantity_and_unit(raw_qty)
            unit = raw_unit or parsed_unit or "EA"

            line_warnings: List[ExtractionWarning] = []
            if header_row_idx == -1:
                line_warnings.append(ExtractionWarning(
                    code="HEADERLESS_LAYOUT_REVIEW",
                    message=f"Column roles were guessed for CSV row {row_idx}.",
                    severity="warning",
                ))
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
                    candidate_segments.append(EvidenceSegment(
                        segment_id=region_id,
                        locator=locator,
                        text=row_text,
                        warnings=[ExtractionWarning(
                            code="SOURCE_ROW_UNCLASSIFIED",
                            message=f"Non-empty CSV row {row_idx} did not map to recognized RFQ fields; classify it or review it.",
                            severity="warning",
                        )],
                    ))
                    source_coverage.append(make_coverage_entry(
                        region_id, locator, row_text, "review_candidate", "CSV_ROW_NOT_MAPPED"
                    ))
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
                    field_raw_values={
                        "requested_manufacturer": oem if oem not in (None, "") else None,
                        "requested_mpn": mpn if mpn not in (None, "") else None,
                        "description": desc if desc not in (None, "") else None,
                        "quantity": raw_qty if raw_qty not in (None, "") else None,
                        "unit": str(raw_unit) if raw_unit not in (None, "") else None,
                    },
                    extraction_warnings=line_warnings,
                )
            )
            source_coverage.append(make_coverage_entry(
                region_id, locator, row_text, "structured_line", "CSV_ROW_PARSED"
            ))
            line_counter += 1

        if not lines:
            warnings.append(ExtractionWarning(
                code="NO_LINES_EXTRACTED",
                message="No RFQ line items found in CSV. Manual entry or a corrected file is required.",
                severity="error",
            ))

        enforce_candidate_region_limit(candidate_segments, source_coverage.build())
        return ParsedDocumentResult(
            lines=lines,
            warnings=warnings,
            total_lines_detected=len(lines),
            candidate_segments=candidate_segments,
            source_coverage=source_coverage.build(),
        )

    def _parse_xlsx(self, content: bytes, filename: str) -> ParsedDocumentResult:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=False, read_only=True)
        except Exception as exc:
            raise DocumentParserError(f"Workbook could not be opened safely: {type(exc).__name__}") from exc
        if len(wb.sheetnames) > 20:
            wb.close()
            raise DocumentParserError(f"Spreadsheet sheet count ({len(wb.sheetnames)}) exceeds maximum permitted limit (20 sheets).")
        try:
            visibility_by_sheet = read_hidden_dimensions(content)
        except Exception as exc:
            wb.close()
            raise DocumentParserError(
                "Workbook row/column visibility could not be verified safely; the original file is retained for manual review."
            ) from exc
        cached_wb = None
        if any(sheet.has_formulas for sheet in visibility_by_sheet.values()):
            try:
                cached_wb = openpyxl.load_workbook(
                    io.BytesIO(content), data_only=True, read_only=True
                )
            except Exception as exc:
                wb.close()
                raise DocumentParserError(
                    f"Workbook formula cache could not be opened safely: {type(exc).__name__}"
                ) from exc

        lines: List[ParsedLineDraft] = []
        warnings: List[ExtractionWarning] = []
        candidate_segments: List[EvidenceSegment] = []
        source_coverage = SourceCoverageAccumulator()
        line_counter = 1
        try:
            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                unit_id = f"sheet:{sheet_name}"
                locator = SourceLocator(file_name=filename, sheet_name=sheet_name)
                hidden_sheet = ws.sheet_state != "visible"
                visibility = visibility_by_sheet[sheet_name]
                source_coverage.record_unit(
                    unit_id, locator, unit_kind="workbook_sheet",
                    is_empty=True, sheet_visibility="hidden" if hidden_sheet else "visible",
                    hidden_row_count=len(visibility.hidden_rows),
                    hidden_column_count=len(visibility.hidden_columns),
                )
                if ws.max_row and ws.max_row > 5000:
                    source_coverage.record_unit(
                        unit_id, locator, unit_kind="workbook_sheet", processing_status="rejected",
                        truncated=True, error_code="XLSX_ROW_LIMIT_EXCEEDED",
                        sheet_visibility="hidden" if hidden_sheet else "visible",
                    )
                    raise DocumentParserError(
                        f"Spreadsheet sheet '{sheet_name}' row count ({ws.max_row}) exceeds limit (5000 rows).",
                        source_coverage=source_coverage.build(),
                    )
                if ws.max_column and ws.max_column > 100:
                    source_coverage.record_unit(
                        unit_id, locator, unit_kind="workbook_sheet", processing_status="rejected",
                        truncated=True, error_code="XLSX_COLUMN_LIMIT_EXCEEDED",
                        sheet_visibility="hidden" if hidden_sheet else "visible",
                    )
                    raise DocumentParserError(
                        f"Spreadsheet sheet '{sheet_name}' column count ({ws.max_column}) exceeds limit (100 columns).",
                        source_coverage=source_coverage.build(),
                    )

                if cached_wb is not None:
                    cached_ws = cached_wb[sheet_name]
                    worksheet_rows: Iterable[Tuple[Tuple[Any, ...], Tuple[Any, ...]]] = zip(
                        ws.iter_rows(values_only=False),
                        cached_ws.iter_rows(values_only=False),
                    )
                else:
                    worksheet_rows = ((row, row) for row in ws.iter_rows(values_only=False))
                row_iterator = iter(worksheet_rows)
                header_sample = list(itertools.islice(row_iterator, 10))
                merges_by_column: Dict[int, List[VerticalMerge]] = {}
                merges_starting_by_row: Dict[int, List[VerticalMerge]] = {}
                for merge in visibility.vertical_merges:
                    merges_by_column.setdefault(merge.column_index, []).append(merge)
                    merges_starting_by_row.setdefault(merge.first_row, []).append(merge)
                for merges in merges_by_column.values():
                    merges.sort(key=lambda merge: merge.first_row)
                merge_starts_by_column = {
                    column_index: [merge.first_row for merge in merges]
                    for column_index, merges in merges_by_column.items()
                }
                merge_anchor_cells = {}
                for sample_row_number, (sample_row, sample_cached_row) in enumerate(
                    header_sample, start=1
                ):
                    for merge in merges_starting_by_row.get(sample_row_number, []):
                        if merge.column_index < len(sample_row):
                            merge_anchor_cells[(merge.column_index, merge.first_row)] = (
                                sample_row[merge.column_index],
                                sample_cached_row[merge.column_index],
                            )
                if not header_sample:
                    source_coverage.record_unit(
                        unit_id, locator, unit_kind="workbook_sheet", is_empty=True,
                        sheet_visibility="hidden" if hidden_sheet else "visible",
                    )
                    continue
                header_row_idx = -1
                col_map: Dict[str, int] = {}
                for idx, (row, _) in enumerate(header_sample):
                    col_map = identify_columns([str(c.value) if c.value is not None else "" for c in row])
                    if "mpn" in col_map or ("description" in col_map and "quantity" in col_map):
                        header_row_idx = idx
                        break

                guessed_layout = header_row_idx == -1
                source_coverage.record_unit(
                    unit_id, locator, unit_kind="workbook_sheet",
                    sheet_visibility="hidden" if hidden_sheet else "visible",
                    header_row_number=(header_row_idx + 1 if header_row_idx >= 0 else None),
                )
                if not guessed_layout:
                    for skipped_idx, (skipped_row, _) in enumerate(
                        header_sample[: header_row_idx + 1], start=1
                    ):
                        skipped_text = self._row_text(skipped_row)
                        if skipped_text:
                            source_coverage.append(make_coverage_entry(
                                f"xlsx-{sheet_name}-row-{skipped_idx}",
                                SourceLocator(file_name=filename, sheet_name=sheet_name,
                                              row_number=skipped_idx, text_snippet=skipped_text[:120]),
                                skipped_text,
                                "filtered_metadata",
                                "XLSX_PREAMBLE_OR_HEADER",
                            ))
                if hidden_sheet:
                    warnings.append(ExtractionWarning(
                        code="HIDDEN_SHEET_INCLUDED",
                        message=f"Hidden sheet '{sheet_name}' contains possible request data and was included in inspection.",
                        severity="warning",
                    ))
                if guessed_layout:
                    col_map = self._infer_xlsx_columns([row for row, _ in header_sample])
                    if not col_map:
                        for source_row_number, (row, _) in enumerate(
                            itertools.chain(header_sample, row_iterator), start=1
                        ):
                            row_text = self._row_text(row)
                            if row_text and not self._is_known_non_item_metadata(row_text):
                                locator = SourceLocator(
                                    file_name=filename, sheet_name=sheet_name,
                                    row_number=source_row_number, text_snippet=row_text[:120],
                                )
                                region_id = f"xlsx-{sheet_name}-row-{source_row_number}"
                                candidate_segments.append(EvidenceSegment(
                                    segment_id=region_id,
                                    locator=locator,
                                    text=row_text,
                                    warnings=[ExtractionWarning(
                                        code="HEADERLESS_SHEET_LAYOUT_UNKNOWN",
                                        message=f"This row came from sheet '{sheet_name}', whose columns could not be mapped. Verify it as a possible RFQ item.",
                                        severity="warning",
                                    )],
                                ))
                                source_coverage.append(make_coverage_entry(
                                    region_id, locator, row_text, "review_candidate", "XLSX_UNKNOWN_LAYOUT_ROW"
                                ))
                            elif row_text:
                                source_coverage.append(make_coverage_entry(
                                    f"xlsx-{sheet_name}-row-{source_row_number}",
                                    SourceLocator(file_name=filename, sheet_name=sheet_name,
                                                  row_number=source_row_number, text_snippet=row_text[:120]),
                                    row_text,
                                    "filtered_metadata",
                                    "KNOWN_WORKBOOK_METADATA",
                                ))
                        warnings.append(ExtractionWarning(
                            code="HEADERLESS_SHEET_LAYOUT_UNKNOWN",
                            message=f"No header or recognizable part/quantity columns were found in sheet '{sheet_name}'. The original sheet was not silently treated as line items.",
                            severity="warning",
                        ))
                        continue
                    data_rows = itertools.chain(header_sample, row_iterator)
                    first_row_number = 1
                    warnings.append(ExtractionWarning(
                        code="HEADERLESS_SHEET_LAYOUT_GUESSED",
                        message=f"No recognized header was found in sheet '{sheet_name}'. Column roles were inferred; verify these rows.",
                        severity="warning",
                    ))
                else:
                    data_rows = itertools.chain(header_sample[header_row_idx + 1:], row_iterator)
                    first_row_number = header_row_idx + 2

                for row_idx, (row, cached_row) in enumerate(data_rows, start=first_row_number):
                    for merge in merges_starting_by_row.get(row_idx, []):
                        if merge.column_index < len(row):
                            merge_anchor_cells[(merge.column_index, merge.first_row)] = (
                                row[merge.column_index], cached_row[merge.column_index]
                            )
                    if not row or all(c.value is None or str(c.value).strip() == "" for c in row):
                        continue
                    row_text = self._row_text(row)
                    region_id = f"xlsx-{sheet_name}-row-{row_idx}"
                    mpn_idx = col_map.get("mpn")
                    qty_idx = col_map.get("quantity")
                    oem_idx = col_map.get("manufacturer")
                    desc_idx = col_map.get("description")
                    unit_idx = col_map.get("unit")
                    notes_idx = col_map.get("notes")

                    field_indexes = {
                        "requested_mpn": mpn_idx,
                        "requested_manufacturer": oem_idx,
                        "description": desc_idx,
                        "quantity": qty_idx,
                        "unit": unit_idx,
                        "notes": notes_idx,
                    }
                    effective_cells = {}
                    effective_cached_cells = {}
                    field_source_cells = {}
                    inherited_merges = {}
                    for field_name, column_index in field_indexes.items():
                        if column_index is None or column_index >= len(row):
                            continue
                        source_cell = row[column_index]
                        cached_cell = cached_row[column_index] if column_index < len(cached_row) else None
                        value = getattr(source_cell, "value", None)
                        if value is None or (isinstance(value, str) and not value.strip()):
                            merges = merges_by_column.get(column_index, [])
                            starts = merge_starts_by_column.get(column_index, [])
                            merge_index = bisect_right(starts, row_idx) - 1
                            if merge_index >= 0:
                                merge = merges[merge_index]
                                if merge.first_row < row_idx <= merge.last_row:
                                    anchor = merge_anchor_cells.get((column_index, merge.first_row))
                                    if anchor is not None and getattr(anchor[0], "value", None) not in (None, ""):
                                        source_cell, cached_cell = anchor
                                        inherited_merges[field_name] = merge
                        effective_cells[field_name] = source_cell
                        if cached_cell is not None:
                            effective_cached_cells[field_name] = cached_cell
                        field_source_cells[field_name] = (
                            inherited_merges[field_name].anchor_cell
                            if field_name in inherited_merges
                            else f"{get_column_letter(column_index + 1)}{row_idx}"
                        )

                    locator = SourceLocator(
                        file_name=filename,
                        sheet_name=sheet_name,
                        row_number=row_idx,
                        text_snippet=row_text[:120],
                        field_source_cells=field_source_cells,
                    )

                    formula_fields = {
                        name for name, field_name in (
                            ("mpn", "requested_mpn"),
                            ("manufacturer", "requested_manufacturer"),
                            ("description", "description"),
                            ("quantity", "quantity"),
                            ("unit", "unit"),
                        )
                        if getattr(effective_cells.get(field_name), "data_type", None) == "f"
                    }
                    source_coverage.add_formula_backed_fields(unit_id, len(formula_fields))
                    mpn = self._get_col_value((effective_cells.get("requested_mpn"),), 0)
                    oem = self._get_col_value((effective_cells.get("requested_manufacturer"),), 0)
                    desc = self._get_col_value((effective_cells.get("description"),), 0)
                    raw_qty = self._get_col_value((effective_cells.get("quantity"),), 0)
                    raw_unit = self._get_col_value((effective_cells.get("unit"),), 0)
                    notes = self._get_col_value((effective_cells.get("notes"),), 0)

                    qty, parsed_unit = parse_quantity_and_unit(raw_qty)
                    unit = raw_unit or parsed_unit or "EA"
                    line_warnings: List[ExtractionWarning] = []
                    if guessed_layout:
                        line_warnings.append(ExtractionWarning(
                            code="HEADERLESS_LAYOUT_REVIEW",
                            message=f"Column roles were guessed for sheet '{sheet_name}', row {row_idx}.",
                            severity="warning",
                        ))
                    if inherited_merges:
                        inherited_sources = ", ".join(
                            f"{field_name} from {merge.anchor_cell}"
                            for field_name, merge in sorted(inherited_merges.items())
                        )
                        line_warnings.append(ExtractionWarning(
                            code="MERGED_CELL_VALUE_INHERITED",
                            message=(
                                f"This row uses merged-cell values ({inherited_sources}). "
                                "Verify that the merged value applies to this line."
                            ),
                            severity="warning",
                        ))
                        if any(
                            merge.first_row in visibility.hidden_rows
                            for merge in inherited_merges.values()
                        ):
                            line_warnings.append(ExtractionWarning(
                                code="MERGED_VALUE_FROM_HIDDEN_ROW",
                                message="An inherited value originates in a hidden row; verify it against the original workbook.",
                                severity="warning",
                            ))
                    if (
                        numeric_identifier_precision_risk(
                            getattr(effective_cells.get("requested_mpn"), "value", None)
                        )
                    ):
                        line_warnings.append(ExtractionWarning(
                            code="NUMERIC_MPN_EXCEL_PRECISION_RISK",
                            message=(
                                f"The part identifier in row {row_idx} of sheet '{sheet_name}' is stored as a number with more than 15 significant digits. "
                                "Excel may already have rounded it; verify the exact identifier in the original source."
                            ),
                            severity="warning",
                        ))
                    if hidden_sheet:
                        line_warnings.append(ExtractionWarning(
                            code="HIDDEN_SHEET_REVIEW",
                            message=f"This row came from hidden sheet '{sheet_name}'. Verify it is part of the RFQ.",
                            severity="warning",
                        ))
                    if row_idx in visibility.hidden_rows:
                        line_warnings.append(ExtractionWarning(
                            code="HIDDEN_ROW_REVIEW",
                            message=f"This RFQ row is hidden in sheet '{sheet_name}'. Verify it is intended to be quoted.",
                            severity="warning",
                        ))
                    mapped_fields = {
                        idx for idx in (mpn_idx, oem_idx, desc_idx, qty_idx, unit_idx, notes_idx)
                        if idx is not None
                    }
                    if mapped_fields.intersection(visibility.hidden_columns):
                        line_warnings.append(ExtractionWarning(
                            code="HIDDEN_COLUMN_VALUE_REVIEW",
                            message=f"One or more mapped RFQ fields in row {row_idx} are in hidden columns of sheet '{sheet_name}'. Verify the original workbook layout.",
                            severity="warning",
                        ))
                    if formula_fields:
                        cached_values = {}
                        for name, field_name in (
                            ("mpn", "requested_mpn"),
                            ("manufacturer", "requested_manufacturer"),
                            ("description", "description"),
                            ("quantity", "quantity"),
                            ("unit", "unit"),
                        ):
                            cached_cell = effective_cached_cells.get(field_name)
                            if (
                                name in formula_fields
                                and cached_cell is not None
                                and cached_cell.value is not None
                            ):
                                cached_values[name] = format_excel_value(
                                    cached_cell.value, cached_cell.number_format
                                )
                        cached_detail = (
                            " Cached workbook values (not recalculated): "
                            + ", ".join(f"{name}={value}" for name, value in sorted(cached_values.items()))
                            + "."
                            if cached_values else " No cached result was stored in the workbook."
                        )
                        line_warnings.append(ExtractionWarning(
                            code="FORMULA_VALUE_NOT_EVALUATED",
                            message=(
                                f"Formula-backed fields ({', '.join(sorted(formula_fields))}) were preserved as formula text and not calculated."
                                + cached_detail
                            ),
                            severity="warning",
                        ))
                        if "quantity" in formula_fields:
                            qty = None
                    if qty is None:
                        line_warnings.append(ExtractionWarning(
                            code="MISSING_QUANTITY",
                            message=f"Missing or unparseable quantity in row {row_idx} of sheet '{sheet_name}'.",
                            severity="warning",
                        ))
                    if not mpn and not desc:
                        if not oem and qty is None and not notes:
                            if self._is_known_non_item_metadata(row_text):
                                source_coverage.append(make_coverage_entry(
                                    region_id, locator, row_text, "filtered_metadata", "KNOWN_WORKBOOK_METADATA"
                                ))
                                continue
                            candidate_segments.append(EvidenceSegment(
                                segment_id=region_id,
                                locator=locator,
                                text=row_text,
                                warnings=[ExtractionWarning(
                                    code="SOURCE_ROW_UNCLASSIFIED",
                                    message=f"Non-empty row {row_idx} in sheet '{sheet_name}' did not map to recognized RFQ fields; classify it or review it.",
                                    severity="warning",
                                )],
                            ))
                            source_coverage.append(make_coverage_entry(
                                region_id, locator, row_text, "review_candidate", "XLSX_ROW_NOT_MAPPED"
                            ))
                            continue
                        line_warnings.append(ExtractionWarning(
                            code="MISSING_PART_REFERENCE",
                            message=f"Cannot identify requested part on row {row_idx} of sheet '{sheet_name}'.",
                            severity="warning",
                        ))

                    # Headerless rows that could not be mapped remain visible
                    # as candidates; heuristics must not silently discard them.
                    if guessed_layout and not mpn and qty is None:
                        if row_text:
                            candidate_segments.append(EvidenceSegment(
                                segment_id=region_id,
                                locator=locator,
                                text=row_text,
                                warnings=[ExtractionWarning(
                                    code="HEADERLESS_SHEET_LAYOUT_UNKNOWN",
                                    message=f"This row in sheet '{sheet_name}' could not be mapped to a part and quantity column.",
                                    severity="warning",
                                )],
                            ))
                            source_coverage.append(make_coverage_entry(
                                region_id, locator, row_text, "review_candidate", "XLSX_LAYOUT_NOT_MAPPED"
                            ))
                        continue
                    if (
                        not mpn and not desc and not oem and qty is None and not notes
                        and row_text
                    ):
                        candidate_segments.append(EvidenceSegment(
                            segment_id=region_id,
                            locator=locator,
                            text=row_text,
                        ))
                        source_coverage.append(make_coverage_entry(
                            region_id, locator, row_text, "review_candidate", "XLSX_ROW_UNCLASSIFIED"
                        ))
                        continue
                    lines.append(ParsedLineDraft(
                        line_number=line_counter,
                        raw_text=row_text,
                        source_locator=locator,
                        requested_manufacturer=oem,
                        requested_mpn=mpn,
                        description=desc,
                        quantity=qty,
                        unit=unit,
                        notes=notes,
                        field_raw_values={
                            name: (
                                str(getattr(effective_cells.get(name), "value"))
                                if effective_cells.get(name) is not None
                                and getattr(effective_cells.get(name), "value", None) is not None
                                and str(getattr(effective_cells.get(name), "value")).strip()
                                else None
                            )
                            for name in (
                                "requested_manufacturer", "requested_mpn", "description", "quantity", "unit"
                            )
                        },
                        extraction_warnings=line_warnings,
                    ))
                    source_coverage.append(make_coverage_entry(
                        region_id, locator, row_text, "structured_line", "XLSX_ROW_PARSED"
                    ))
                    line_counter += 1
        finally:
            wb.close()
            if cached_wb is not None:
                cached_wb.close()

        if not lines:
            warnings.append(ExtractionWarning(
                code="NO_LINES_EXTRACTED",
                message="No valid part lines could be extracted from workbook sheets.",
                severity="error",
            ))
        enforce_candidate_region_limit(candidate_segments, source_coverage.build())
        return ParsedDocumentResult(
            lines=lines,
            warnings=warnings,
            total_lines_detected=len(lines),
            candidate_segments=candidate_segments,
            source_coverage=source_coverage.build(),
        )

    @staticmethod
    def _is_known_non_item_metadata(text: str) -> bool:
        """Recognize narrow workbook title/footer rows, not product keywords."""
        return bool(re.match(
            r"^(?:confidential\b|internal pricing\b|pricing data\b|prepared by\b|"
            r"synthetic\b|total\b|subtotal\b|grand total\b|page\s+\d+\b|"
            r"terms and conditions\b)",
            text.strip(),
            re.IGNORECASE,
        ))

    @staticmethod
    def _row_text(row) -> str:
        """Render literal cell values and formula text only, never cached formula results."""
        return " | ".join(
            rendered for rendered in (
                render_excel_cell(cell) for cell in row
            ) if rendered
        )

    @staticmethod
    def _infer_xlsx_columns(rows: List[Tuple]) -> Dict[str, int]:
        """Infer likely part, quantity, and description columns from a small sample."""
        width = max((len(row) for row in rows), default=0)
        mpn_scores: Dict[int, int] = {}
        qty_scores: Dict[int, int] = {}
        desc_scores: Dict[int, int] = {}
        for col_idx in range(width):
            for row in rows:
                if col_idx >= len(row) or row[col_idx].value is None:
                    continue
                value = str(row[col_idx].value).strip()
                if not value:
                    continue
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{2,}", value) and (
                    (any(ch.isdigit() for ch in value) and any(ch.isalpha() for ch in value))
                    or (value.isdigit() and len(value) >= 5)
                ):
                    mpn_scores[col_idx] = mpn_scores.get(col_idx, 0) + 1
                quantity, _ = parse_quantity_and_unit(value)
                if quantity is not None:
                    qty_scores[col_idx] = qty_scores.get(col_idx, 0) + 1
                if len(value) >= 20 and quantity is None and not ((any(ch.isdigit() for ch in value) and any(ch.isalpha() for ch in value))):
                    desc_scores[col_idx] = desc_scores.get(col_idx, 0) + 1
        result: Dict[str, int] = {}
        if mpn_scores:
            result["mpn"] = max(mpn_scores, key=lambda column: mpn_scores[column])
        available = {idx: score for idx, score in qty_scores.items() if idx != result.get("mpn")}
        if available:
            result["quantity"] = max(available, key=lambda column: available[column])
        available_desc = {idx: score for idx, score in desc_scores.items() if idx not in result.values()}
        if available_desc:
            result["description"] = max(available_desc, key=lambda column: available_desc[column])
        return result

    @staticmethod
    def _get_col_value(row: Sequence[Any], col_idx: Optional[int]) -> Optional[str]:
        if col_idx is None or col_idx >= len(row):
            return None
        cell = row[col_idx]
        val = getattr(cell, "value", cell)
        if val is None:
            return None
        val_str = format_excel_value(val, getattr(cell, "number_format", None))
        return val_str if val_str != "" else None
