"""Deterministic XLSX and CSV quotation worksheet generator with strict validation."""

import csv
import io
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from rfq_assistant.exports.email_draft import generate_unsent_email_draft
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.quotation.line_rules import blocking_line_issues
from rfq_assistant.schemas.enums import MatchStatus, ReviewDecision
from rfq_assistant.schemas.models import (
    ExportManifest,
    ExportRequest,
    RFQCase,
    RFQLineItem,
)


class ExportValidationError(Exception):
    """Raised when an export is blocked due to unresolved critical fields."""
    pass


class ExportGenerator:
    """Produces deterministic quotation preparation sheets in XLSX or CSV format."""

    def __init__(self, catalog: CatalogRepository, base_export_dir: Optional[Path] = None):
        self.catalog = catalog
        self.base_export_dir = base_export_dir or Path("storage/exports")
        self.base_export_dir.mkdir(parents=True, exist_ok=True)

    def generate_export(
        self, case: RFQCase, lines: List[RFQLineItem], request: ExportRequest
    ) -> ExportManifest:
        """
        Validates case lines and outputs a deterministic quotation worksheet.
        Blocks final export if unresolved items exist unless allow_partial is True.
        """
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

        import json
        manifest_path = export_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump({
                "export_id": export_id,
                "case_id": case.case_id,
                "file_name": file_name,
            }, mf)

        unsent_email = generate_unsent_email_draft(case, lines)

        approved_count = sum(1 for l in lines if l.review_decision == ReviewDecision.APPROVED)
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

            price_val = catalog_item.list_price if (catalog_item and catalog_item.list_price is not None) else None
            ext_price = (price_val * item.quantity) if (price_val is not None and item.quantity is not None) else None

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
                price_val if price_val is not None else "",
                ext_price if ext_price is not None else "",
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
                if col_idx in (11, 12) and isinstance(cell.value, (int, float)):
                    cell.number_format = "$#,##0.00"

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 10)

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
            writer.writerow(["# DRAFT QUOTATION WORKSHEET - INTERNAL USE ONLY - NOT A FINAL COMMITMENT"])
            writer.writerow([f"# Case ID: {case.case_id}", f"Customer: {case.customer_label or 'Unspecified'}", f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"])
            writer.writerow([f"# Reviewer: {actor}", f"Mode: {'Partial Draft' if is_partial else 'Standard Validated'}"])
            writer.writerow([])
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
            writer.writerow(headers)

            for item in lines:
                catalog_item = self.catalog.get_by_sku(item.selected_catalog_sku) if item.selected_catalog_sku else None
                price_val = catalog_item.list_price if (catalog_item and catalog_item.list_price is not None) else ""
                ext_price = (
                    f"{catalog_item.list_price * item.quantity:.2f}"
                    if (catalog_item and catalog_item.list_price is not None and item.quantity is not None)
                    else ""
                )
                locator_str = f"File: {item.source_locator.file_name} Row: {item.source_locator.row_number}"
                writer.writerow([
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
                    price_val,
                    ext_price,
                    f"{item.notes or ''} [{locator_str}]".strip(),
                ])
