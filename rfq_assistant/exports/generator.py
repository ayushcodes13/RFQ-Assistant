"""Deterministic XLSX and CSV quotation worksheet generator with strict validation."""

import csv
import io
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional, Tuple
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from rfq_assistant.exports.email_draft import generate_unsent_email_draft
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.quotation.line_rules import blocking_line_issues
from rfq_assistant.schemas.enums import MatchStatus, ReviewDecision
from rfq_assistant.schemas.models import (
    ExportDocumentSummary,
    ExportManifest,
    ExportRequest,
    RFQCase,
    RFQLineItem,
)


class ExportValidationError(Exception):
    """Raised when an export is blocked due to unresolved critical fields."""
    pass


def _looks_like_spreadsheet_formula(value: str) -> bool:
    """Detect formula-like values even when prefixed by whitespace/control characters."""
    return value.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@"))


def _safe_csv_cell(value):
    """CSV consumers may interpret untrusted strings as formulas; prefix them as text."""
    if isinstance(value, str) and _looks_like_spreadsheet_formula(value):
        return "'" + value
    return value


def _safe_csv_row(writer, values) -> None:
    writer.writerow([_safe_csv_cell(value) for value in values])


class ExportGenerator:
    """Produces deterministic quotation preparation sheets in XLSX or CSV format."""

    def __init__(self, catalog: CatalogRepository, base_export_dir: Optional[Path] = None):
        self.catalog = catalog
        self.base_export_dir = base_export_dir or Path("storage/exports")
        self.base_export_dir.mkdir(parents=True, exist_ok=True)

    def list_exports(self, case_id: str) -> List[ExportDocumentSummary]:
        """List case-scoped export artifacts without exposing filesystem paths."""
        records: List[ExportDocumentSummary] = []
        if not self.base_export_dir.exists():
            return records

        for export_dir in self.base_export_dir.iterdir():
            export_id = export_dir.name
            if (
                export_dir.is_symlink()
                or not export_dir.is_dir()
                or not re.fullmatch(r"EXP-[A-F0-9]{8}", export_id)
            ):
                continue
            manifest_path = export_dir / "manifest.json"
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if manifest_data.get("case_id") != case_id:
                continue

            file_name = manifest_data.get("file_name")
            if not isinstance(file_name, str) or Path(file_name).name != file_name:
                file_name = ""
            artifact_path = export_dir / file_name if file_name else None
            suffix = Path(file_name).suffix.lower().removeprefix(".") if file_name else ""
            file_format: Literal["xlsx", "csv"] = "csv" if suffix == "csv" else "xlsx"
            try:
                generated_at = datetime.fromisoformat(manifest_data["generated_at"])
            except (KeyError, TypeError, ValueError):
                generated_at = datetime.fromtimestamp(
                    manifest_path.stat().st_mtime, tz=timezone.utc
                )

            file_available = bool(
                artifact_path
                and artifact_path.is_file()
                and not artifact_path.is_symlink()
                and artifact_path.resolve().parent == export_dir.resolve()
            )
            records.append(
                ExportDocumentSummary(
                    export_id=export_id,
                    file_name=file_name or f"Export {export_id}",
                    format=file_format,
                    is_draft=bool(manifest_data.get("is_draft", True)),
                    total_lines=int(manifest_data.get("total_lines", 0)),
                    approved_lines=int(manifest_data.get("approved_lines", 0)),
                    unresolved_lines_omitted=int(
                        manifest_data.get("unresolved_lines_omitted", 0)
                    ),
                    generated_at=generated_at,
                    file_available=file_available,
                    problem=None if file_available else "Generated document file is missing.",
                    download_url=f"/api/rfqs/{case_id}/exports/{export_id}",
                )
            )
        return sorted(records, key=lambda item: item.generated_at, reverse=True)

    def delete_case_exports(self, case_id: str) -> int:
        """Delete generated export directories whose manifest belongs to this case."""
        if not re.fullmatch(r"RFQ-[A-F0-9]{8}", case_id):
            raise OSError("RFQ case ID is not a supported export owner identifier.")
        if self.base_export_dir.is_symlink():
            raise OSError("Export root is a symbolic link; refusing case deletion.")
        if not self.base_export_dir.exists():
            return 0
        if not self.base_export_dir.is_dir():
            raise OSError("Export root is not a directory; refusing case deletion.")

        root = self.base_export_dir.resolve()
        deleted = 0
        for export_dir in self.base_export_dir.iterdir():
            if not re.fullmatch(r"EXP-[A-F0-9]{8}", export_dir.name):
                continue
            if export_dir.is_symlink():
                raise OSError(
                    "An export directory is a symbolic link; refusing case deletion."
                )
            if not export_dir.is_dir():
                continue
            try:
                resolved = export_dir.resolve(strict=True)
                if resolved.parent != root:
                    raise OSError("An export directory escaped the configured export root.")
                manifest_path = export_dir / "manifest.json"
                if manifest_path.is_symlink() or not manifest_path.is_file():
                    raise OSError("An export ownership manifest is missing or unsafe.")
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise OSError("An export ownership manifest is unreadable.") from exc
            if not isinstance(manifest, dict) or not isinstance(
                manifest.get("case_id"), str
            ):
                raise OSError("An export ownership manifest is malformed.")
            if manifest.get("case_id") != case_id:
                continue
            shutil.rmtree(export_dir)
            deleted += 1
        return deleted

    def generate_export(
        self, case: RFQCase, lines: List[RFQLineItem], request: ExportRequest
    ) -> ExportManifest:
        """
        Validates case lines and outputs a deterministic quotation worksheet.
        Blocks final export if unresolved items exist unless allow_partial is True.
        """
        if not lines:
            raise ExportValidationError("Export blocked: RFQ contains no extracted line items.")

        line_problems = [(line, blocking_line_issues(line, self.catalog)) for line in lines]
        unresolved_lines = [line for line, problems in line_problems if problems]

        if unresolved_lines and not request.allow_partial:
            reasons = [
                f"Line {line.line_number} ({', '.join(problems)})"
                for line, problems in line_problems if problems
            ]

            raise ExportValidationError(
                f"Export blocked: {len(unresolved_lines)} line(s) require review before final export: "
                f"{'; '.join(reasons[:5])}. To export anyway, select 'Allow partial/draft export'."
            )

        export_id = f"EXP-{uuid.uuid4().hex[:8].upper()}"
        export_dir = self.base_export_dir / export_id
        export_dir.mkdir(parents=True, exist_ok=True)

        fmt = request.format.lower()
        if fmt not in ("xlsx", "csv"):
            fmt = "xlsx"

        file_name = f"Quotation_Preparation_{case.case_id}_{export_id}.{fmt}"
        file_path = export_dir / file_name

        if fmt == "xlsx":
            self._write_xlsx(case, lines, file_path, request.allow_partial, request.actor)
        else:
            self._write_csv(case, lines, file_path, request.allow_partial, request.actor)

        approved_count = sum(1 for line in lines if line.review_decision == ReviewDecision.APPROVED)
        manifest_path = export_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump({
                "export_id": export_id,
                "case_id": case.case_id,
                "file_name": file_name,
                "format": fmt,
                "is_draft": True,
                "total_lines": len(lines),
                "approved_lines": approved_count,
                "unresolved_lines_omitted": len(unresolved_lines),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }, mf)

        unsent_email = generate_unsent_email_draft(case, lines)

        omitted_or_draft = len(unresolved_lines)

        return ExportManifest(
            export_id=export_id,
            case_id=case.case_id,
            file_name=file_name,
            format=fmt,
            is_draft=True,
            total_lines=len(lines),
            approved_lines=approved_count,
            unresolved_lines_omitted=omitted_or_draft,
            generated_at=datetime.utcnow(),
            reviewer_name=request.actor,
            unsent_email_draft=unsent_email,
            download_url=f"/api/rfqs/{case.case_id}/exports/{export_id}",
        )

    def _write_xlsx(
        self,
        case: RFQCase,
        lines: List[RFQLineItem],
        output_path: Path,
        is_partial: bool,
        actor: str,
    ):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Quote Preparation"

        # Styling definitions
        font_banner = Font(name="Arial", size=11, bold=True, color="991B1B")
        fill_banner = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        font_header = Font(name="Arial", size=10, bold=True, color="0F172A")
        fill_header = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        font_cell = Font(name="Arial", size=9, color="1E293B")
        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        # Row 1: High-visibility DRAFT notice
        ws.merge_cells("A1:M1")
        cell_banner = ws["A1"]
        cell_banner.value = "*** DRAFT QUOTATION WORKSHEET — INTERNAL USE ONLY — NOT A BINDING OFFER ***"
        cell_banner.font = font_banner
        cell_banner.fill = fill_banner
        cell_banner.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 25

        # Row 2-4: Metadata
        ws["A2"] = "Case ID:"
        ws["B2"] = case.case_id
        ws["D2"] = "Customer:"
        ws["E2"] = case.customer_label or "Unspecified"
        ws["G2"] = "Date:"
        ws["H2"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        ws["A3"] = "Reviewer:"
        ws["B3"] = actor
        ws["D3"] = "Source File:"
        ws["E3"] = case.source_file.file_name if case.source_file else "Pasted Text"
        ws["G3"] = "Export Mode:"
        ws["H3"] = "Partial Draft (Unresolved lines included)" if is_partial else "Standard Validated"

        # Row 5: Column headers
        headers = [
            "Line #",
            "Review Status",
            "Requested OEM",
            "Requested MPN",
            "Matched SKU",
            "Catalog OEM",
            "Catalog MPN",
            "Description",
            "Qty",
            "UOM",
            "List Price",
            "Ext Price",
            "Notes / Source Locator",
        ]
        ws.append([])  # blank row 4
        ws.merge_cells("K4:M4")
        pricing_note = ws["K4"]
        pricing_note.value = (
            "Pricing intentionally blank. Sales must supply and authorize current pricing."
        )
        pricing_note.font = Font(name="Arial", size=9, italic=True, color="64748B")
        pricing_note.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        ws.row_dimensions[4].height = 30
        ws.append(headers)
        ws.row_dimensions[5].height = 22

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=5, column=col_idx)
            cell.font = font_header
            cell.fill = fill_header
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center" if col_idx in (1, 9, 10) else "left", vertical="center")

        # Line item rows
        for row_num, item in enumerate(lines, start=6):
            catalog_item = self.catalog.get_by_sku(item.selected_catalog_sku) if item.selected_catalog_sku else None

            locator_str = f"File: {item.source_locator.file_name}"
            if item.source_locator.sheet_name:
                locator_str += f" | Sheet: {item.source_locator.sheet_name}"
            if item.source_locator.page_number:
                locator_str += f" | Page: {item.source_locator.page_number}"
            if item.source_locator.row_number:
                locator_str += f" | Row: {item.source_locator.row_number}"

            row_data = [
                item.line_number,
                item.review_decision.value,
                item.requested_manufacturer or "--",
                item.requested_mpn or "--",
                item.selected_catalog_sku or "--",
                catalog_item.manufacturer if catalog_item else "--",
                catalog_item.manufacturer_part_number if catalog_item else "--",
                catalog_item.description if catalog_item else item.description or "--",
                item.quantity if item.quantity is not None else "MISSING",
                item.unit or "EA",
                "",
                "",
                f"{item.notes or ''} [{locator_str}]".strip(),
            ]

            ws.append(row_data)
            ws.row_dimensions[row_num].height = 18

            for col_idx in range(1, len(row_data) + 1):
                cell = ws.cell(row=row_num, column=col_idx)
                cell.font = font_cell
                cell.border = thin_border
                cell.alignment = Alignment(
                    horizontal="center" if col_idx in (1, 9, 10) else "right" if col_idx in (11, 12) else "left",
                    vertical="center",
                )

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 10)
        # The merged pricing note crosses these columns; keep price columns
        # compact so it does not turn the numeric fields into wide text areas.
        ws.column_dimensions["K"].width = 14
        ws.column_dimensions["L"].width = 14

        # openpyxl infers executable formulas from strings beginning with "=".
        # Save untrusted spreadsheet-like strings as literal text cells instead.
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and _looks_like_spreadsheet_formula(cell.value):
                    cell.data_type = "s"

        wb.save(output_path)

    def _write_csv(
        self,
        case: RFQCase,
        lines: List[RFQLineItem],
        output_path: Path,
        is_partial: bool,
        actor: str,
    ):
        with open(output_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            _safe_csv_row(writer, ["# DRAFT QUOTATION WORKSHEET - INTERNAL USE ONLY - NOT A FINAL COMMITMENT"])
            _safe_csv_row(writer, [f"# Case ID: {case.case_id}", f"Customer: {case.customer_label or 'Unspecified'}", f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"])
            _safe_csv_row(writer, [f"# Reviewer: {actor}", f"Mode: {'Partial Draft' if is_partial else 'Standard Validated'}"])
            _safe_csv_row(writer, ["# Pricing intentionally blank; sales must supply and authorize current pricing."])
            _safe_csv_row(writer, [])
            headers = [
                "line_number",
                "review_status",
                "requested_oem",
                "requested_mpn",
                "matched_sku",
                "catalog_oem",
                "catalog_mpn",
                "description",
                "quantity",
                "uom",
                "unit_price",
                "ext_price",
                "notes_and_locator",
            ]
            _safe_csv_row(writer, headers)

            for item in lines:
                catalog_item = self.catalog.get_by_sku(item.selected_catalog_sku) if item.selected_catalog_sku else None
                locator_str = f"File: {item.source_locator.file_name} Row: {item.source_locator.row_number}"
                _safe_csv_row(writer, [
                    item.line_number,
                    item.review_decision.value,
                    item.requested_manufacturer or "",
                    item.requested_mpn or "",
                    item.selected_catalog_sku or "",
                    catalog_item.manufacturer if catalog_item else "",
                    catalog_item.manufacturer_part_number if catalog_item else "",
                    catalog_item.description if catalog_item else item.description or "",
                    item.quantity if item.quantity is not None else "MISSING",
                    item.unit or "EA",
                    "",
                    "",
                    f"{item.notes or ''} [{locator_str}]".strip(),
                ])
