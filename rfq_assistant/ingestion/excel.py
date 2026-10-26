"""High-fidelity Excel workbook and BOM inspector using openpyxl and defusedxml.

Provides cell-level, sheet-level, formula, hidden-row/sheet, and workbook access.
Protects against XML expansion attacks via defusedxml.
"""

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import openpyxl
from openpyxl.worksheet.worksheet import Worksheet
import defusedxml

# Defusedxml enables safe parsing for openpyxl XML structures
defusedxml.defuse_stdlib()


class ExcelBOMInspector:
    """Detailed deterministic inspector for Excel RFQ spreadsheets."""

    def __init__(self, max_sheets: int = 10, max_rows_per_sheet: int = 2000):
        self.max_sheets = max_sheets
        self.max_rows_per_sheet = max_rows_per_sheet

    def inspect(self, content_or_path: Union[bytes, Path, str]) -> Dict[str, Any]:
        """Inspects workbook structure, metadata, formulas, and rows."""
        if isinstance(content_or_path, (str, Path)):
            wb_source = content_or_path
            wb_formula = openpyxl.load_workbook(wb_source, read_only=False, data_only=False)
            wb_data = openpyxl.load_workbook(wb_source, read_only=False, data_only=True)
        else:
            wb_source = BytesIO(content_or_path)
            wb_formula = openpyxl.load_workbook(wb_source, read_only=False, data_only=False)
            wb_data = openpyxl.load_workbook(BytesIO(content_or_path), read_only=False, data_only=True)

        sheets_meta: List[Dict[str, Any]] = []

        try:
            for title in wb_formula.sheetnames[: self.max_sheets]:
                ws_f: Worksheet = wb_formula[title]
                ws_d: Worksheet = wb_data[title]

                is_hidden = ws_f.sheet_state != "visible"
                rows_data: List[Dict[str, Any]] = []

                # Track hidden row indices
                hidden_rows: List[int] = []
                for row_idx, row_dim in ws_f.row_dimensions.items():
                    if row_dim.hidden:
                        hidden_rows.append(row_idx)

                # Iterate rows
                row_count = 0
                for r_idx, (row_f, row_d) in enumerate(
                    zip(ws_f.iter_rows(), ws_d.iter_rows()), start=1
                ):
                    row_count += 1
                    if row_count > self.max_rows_per_sheet:
                        break

                    cells: List[Dict[str, Any]] = []
                    has_data = False

                    for c_f, c_d in zip(row_f, row_d):
                        val_formula = c_f.value
                        val_data = c_d.value
                        coordinate = c_f.coordinate

                        is_formula = isinstance(val_formula, str) and val_formula.startswith("=")
                        
                        # Preserve MPNs formatted as numbers or strings with leading zeroes
                        display_str = self._format_cell_value(val_data if val_data is not None else val_formula)

                        if display_str:
                            has_data = True

                        cells.append({
                            "coordinate": coordinate,
                            "formula": val_formula if is_formula else None,
                            "value": val_data,
                            "display_text": display_str,
                            "is_formula": is_formula,
                        })

                    if has_data:
                        rows_data.append({
                            "row_number": r_idx,
                            "is_hidden": r_idx in hidden_rows,
                            "cells": cells,
                        })

                sheets_meta.append({
                    "title": title,
                    "state": ws_f.sheet_state,
                    "is_hidden": is_hidden,
                    "total_data_rows": len(rows_data),
                    "hidden_rows": hidden_rows,
                    "rows": rows_data,
                })

            return {
                "total_sheets": len(wb_formula.sheetnames),
                "sheets": sheets_meta,
                "has_hidden_sheets": any(s["is_hidden"] for s in sheets_meta),
            }
        finally:
            wb_formula.close()
            wb_data.close()

    @staticmethod
    def _format_cell_value(val: Any) -> str:
        """Formats cell value accurately preserving numeric codes and strings."""
        if val is None:
            return ""
        if isinstance(val, float):
            if val.is_integer():
                return str(int(val))
            return f"{val:.4f}".rstrip("0").rstrip(".")
        if isinstance(val, int):
            return str(val)
        return str(val).strip()
