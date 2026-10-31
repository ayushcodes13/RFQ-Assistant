"""Read Excel layout metadata without loading worksheet cell values."""

from __future__ import annotations

import io
import posixpath
import zipfile
from dataclasses import dataclass
from defusedxml import ElementTree
from openpyxl.utils.cell import range_boundaries, get_column_letter

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@dataclass(frozen=True)
class SheetVisibility:
    hidden_rows: set[int]
    hidden_columns: set[int]
    vertical_merges: tuple["VerticalMerge", ...] = ()
    has_formulas: bool = False


@dataclass(frozen=True)
class VerticalMerge:
    column_index: int
    first_row: int
    last_row: int
    anchor_cell: str


def _worksheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relation.attrib["Id"]: relation.attrib["Target"]
        for relation in relationships.findall(f"{{{_PACKAGE_REL_NS}}}Relationship")
        if "Id" in relation.attrib and "Target" in relation.attrib
    }
    paths = {}
    sheets = workbook.find(f"{{{_MAIN_NS}}}sheets")
    if sheets is None:
        raise ValueError("Workbook sheet relationships are missing")
    for sheet in sheets.findall(f"{{{_MAIN_NS}}}sheet"):
        name = sheet.attrib.get("name")
        relationship_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
        target = targets.get(relationship_id or "")
        if not name or not target:
            raise ValueError("Workbook sheet metadata is incomplete")
        if target.startswith("/"):
            path = posixpath.normpath(target.lstrip("/"))
        else:
            path = posixpath.normpath(posixpath.join("xl", target))
        if path.startswith("../") or path not in archive.namelist():
            raise ValueError("Workbook sheet path is invalid")
        paths[name] = path
    return paths


def read_hidden_dimensions(content: bytes) -> dict[str, SheetVisibility]:
    """Collect hidden row and column indexes via bounded streaming XML reads.

    openpyxl's read-only worksheets do not expose row/column dimension
    visibility. This reads only the workbook relationships and each sheet's
    XML metadata; it never materializes cell values or evaluates formulas.
    The caller enforces the workbook byte, row, column, and sheet limits.
    """
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        paths = _worksheet_paths(archive)
        result: dict[str, SheetVisibility] = {}
        for sheet_name, path in paths.items():
            hidden_rows: set[int] = set()
            hidden_columns: set[int] = set()
            vertical_merges: list[VerticalMerge] = []
            has_formulas = False
            with archive.open(path) as xml_stream:
                for event, element in ElementTree.iterparse(
                    xml_stream, events=("start", "end")
                ):
                    if event == "start" and element.tag == f"{{{_MAIN_NS}}}row":
                        if element.attrib.get("hidden", "").casefold() in {"1", "true"}:
                            try:
                                row_number = int(element.attrib.get("r", ""))
                            except ValueError:
                                row_number = 0
                            if row_number > 0:
                                hidden_rows.add(row_number)
                    elif event == "start" and element.tag == f"{{{_MAIN_NS}}}col":
                        if element.attrib.get("hidden", "").casefold() in {"1", "true"}:
                            try:
                                first = int(element.attrib.get("min", ""))
                                last = int(element.attrib.get("max", ""))
                            except ValueError:
                                first, last = 0, -1
                            if 1 <= first <= last <= 100:
                                hidden_columns.update(range(first - 1, last))
                    elif event == "start" and element.tag == f"{{{_MAIN_NS}}}mergeCell":
                        reference = element.attrib.get("ref", "")
                        try:
                            min_column, min_row, max_column, max_row = range_boundaries(
                                reference
                            )
                        except (TypeError, ValueError):
                            raise ValueError(
                                "Workbook contains an invalid merged cell range"
                            )
                        if None in (min_column, min_row, max_column, max_row):
                            raise ValueError(
                                "Workbook contains an incomplete merged cell range"
                            )
                        if max_column > 100 or max_row > 5000:
                            raise ValueError(
                                "Merged cell range exceeds workbook parser limits"
                            )
                        if min_column == max_column and max_row > min_row:
                            vertical_merges.append(
                                VerticalMerge(
                                    column_index=min_column - 1,
                                    first_row=min_row,
                                    last_row=max_row,
                                    anchor_cell=f"{get_column_letter(min_column)}{min_row}",
                                )
                            )
                    elif event == "start" and element.tag == f"{{{_MAIN_NS}}}f":
                        has_formulas = True
                    elif event == "end":
                        element.clear()
            result[sheet_name] = SheetVisibility(
                hidden_rows=hidden_rows,
                hidden_columns=hidden_columns,
                vertical_merges=tuple(vertical_merges),
                has_formulas=has_formulas,
            )
        return result
