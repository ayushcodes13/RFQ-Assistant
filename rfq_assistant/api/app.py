"""FastAPI application for RFQ Assistant backend API."""

from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal
from rfq_assistant.agents.tools import ApprovalGateError, QuotationCommercialService
from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.exports import ExportGenerator, ExportValidationError
from rfq_assistant.ingestion.excel import ExcelBOMInspector
from rfq_assistant.ingestion.malware import ClamAVScanner
from rfq_assistant.ingestion.parsers.base import DocumentParserError
from rfq_assistant.ingestion.validator import UploadValidationError
from rfq_assistant.matching.catalog import CatalogImportError, CatalogRepository
from rfq_assistant.matching.fuzzy import RapidFuzzCandidateEngine
from rfq_assistant.quotation.validate import ProposedQuote, QuoteLine, SourceRef, validate_proposed_quote
from rfq_assistant.schemas.enums import AuditAction
from rfq_assistant.schemas.models import (
    AuditEvent,
    BatchReviewRequest,
    CatalogItem,
    ExportManifest,
    ExportRequest,
    RFQCase,
    RFQLineItem,
    RFQLineItemUpdate,
)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CATALOG_PATH = ROOT / "fixtures" / "catalogs" / "industrial_components_sample_catalog.csv"

# Global repositories and services
catalog_repo = CatalogRepository()
case_manager = CaseManager(catalog=catalog_repo)
export_generator = ExportGenerator(catalog=catalog_repo)
clamav_scanner = ClamAVScanner()
rapidfuzz_engine = RapidFuzzCandidateEngine()
commercial_service = QuotationCommercialService()

# Pre-load default synthetic catalog if available
if DEFAULT_CATALOG_PATH.exists():
    try:
        catalog_repo.import_csv(DEFAULT_CATALOG_PATH.read_bytes(), version="v1-synth")
        rapidfuzz_engine.index_catalog(catalog_repo.list_all())
    except Exception as e:
        print(f"Warning: Failed to pre-load default catalog: {e}")

app = FastAPI(
    title="RFQ Assistant API",
    version="0.2.0",
    description="Human-reviewed RFQ intake and quotation preparation assistant with OSS stack",
)


# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "catalog_size": catalog_repo.count(),
        "total_cases": len(case_manager.list_cases()),
    }


# ---------------------------------------------------------------------------
# Catalog Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/catalogs/import")
async def import_catalog(file: UploadFile = File(...)):
    """Imports tenant-authorized catalog CSV."""
    content = await file.read()
    try:
        summary = catalog_repo.import_csv(content)
        return {"status": "success", "summary": summary}
    except CatalogImportError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/catalogs", response_model=List[CatalogItem])
def list_catalog():
    """Lists all catalog items in item master."""
    return catalog_repo.list_all()


# ---------------------------------------------------------------------------
# RFQ Case Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/rfqs", response_model=RFQCase)
async def create_rfq(
    file: Optional[UploadFile] = File(None),
    pasted_text: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    customer_label: Optional[str] = Form(None),
    actor: str = Form("Inside Sales"),
):
    """Creates draft case from an uploaded file or pasted email text with malware defense."""
    if not file and not pasted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either an uploaded file or pasted text.",
        )

    try:
        if file:
            content = await file.read()
            filename = file.filename or "upload.xlsx"
            # 1. Attachment security scan
            scan = clamav_scanner.scan_bytes(content, filename=filename)
            if not scan.is_clean:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Security alert: Malicious attachment quarantined ({scan.threat_name}). Processing blocked.",
                )

            case = case_manager.create_case_from_upload(
                filename=filename,
                content=content,
                title=title,
                customer_label=customer_label,
                actor=actor,
            )
            return case
        else:
            raw_text = pasted_text or ""
            scan = clamav_scanner.scan_bytes(raw_text.encode("utf-8"), filename="pasted_text.txt")
            if not scan.is_clean:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Security alert: Malicious content quarantined ({scan.threat_name}).",
                )

            case = case_manager.create_case_from_text(
                raw_text=raw_text,
                title=title,
                customer_label=customer_label,
                actor=actor,
            )
            return case
    except (UploadValidationError, DocumentParserError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@app.get("/api/rfqs", response_model=List[RFQCase])
def list_rfqs():
    """Returns all RFQ cases sorted by date."""
    return case_manager.list_cases()


@app.get("/api/rfqs/{case_id}", response_model=RFQCase)
def get_rfq(case_id: str):
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    return case


@app.get("/api/rfqs/{case_id}/lines", response_model=List[RFQLineItem])
def get_rfq_lines(case_id: str):
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    return case_manager.get_lines(case_id)


@app.patch("/api/rfqs/{case_id}/lines/{line_id}", response_model=RFQLineItem)
def update_rfq_line(case_id: str, line_id: str, update: RFQLineItemUpdate):
    updated = case_manager.update_line(case_id, line_id, update)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found.")
    return updated


@app.post("/api/rfqs/{case_id}/review")
def batch_review_lines(case_id: str, request: BatchReviewRequest):
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    count = case_manager.batch_review(case_id, request)
    return {"status": "success", "updated_count": count}


@app.get("/api/rfqs/{case_id}/audit", response_model=List[AuditEvent])
def get_rfq_audit_trail(case_id: str):
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    return case_manager.get_audit_trail(case_id)


@app.delete("/api/rfqs/{case_id}")
def delete_rfq(case_id: str):
    success = case_manager.delete_case(case_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    return {"status": "success", "deleted_case_id": case_id}


# ---------------------------------------------------------------------------
# Export Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/rfqs/{case_id}/exports", response_model=ExportManifest)
def export_rfq_worksheet(case_id: str, request: ExportRequest):
    """Generates deterministic XLSX/CSV quote worksheet and email draft."""
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")

    lines = case_manager.get_lines(case_id)
    try:
        manifest = export_generator.generate_export(case, lines, request)
        # Record audit event
        case_manager._record_audit(
            case_id=case_id,
            actor=request.actor,
            action=AuditAction.EXPORTED,
            notes=f"Exported {manifest.format.upper()} worksheet ({manifest.file_name}) - {manifest.approved_lines} approved lines.",
        )
        return manifest
    except ExportValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/rfqs/{case_id}/exports/{export_id}")
def download_export(case_id: str, export_id: str):
    """Downloads the generated export artifact."""
    export_dir = Path("storage/exports") / export_id
    if not export_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found.")

    files = list(export_dir.iterdir())
    if not files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export artifact missing.")

    artifact = files[0]
    from fastapi.responses import FileResponse
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if artifact.suffix == ".xlsx"
        else "text/csv"
    )
    return FileResponse(path=str(artifact), filename=artifact.name, media_type=media_type)


@app.get("/api/rfqs/{case_id}/email-draft")
def get_unsent_email_draft(case_id: str):
    """Returns the unsent customer clarification email draft."""
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    lines = case_manager.get_lines(case_id)
    from rfq_assistant.exports.email_draft import generate_unsent_email_draft
    draft = generate_unsent_email_draft(case, lines)
    return {"case_id": case_id, "draft": draft}


# ---------------------------------------------------------------------------
# V1 Public Contract Endpoints (OSS Stack & Pydantic AI Pipeline)
# ---------------------------------------------------------------------------

@app.post("/v1/rfqs/extract")
async def v1_extract_rfq(
    file: Optional[UploadFile] = File(None),
    pasted_text: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    customer_name: Optional[str] = Form(None),
):
    """V1 Extract: Scans attachment with ClamAV, isolates untrusted data, extracts RFQ lines."""
    if not file and not pasted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide an attachment file or pasted text.",
        )

    if file:
        content = await file.read()
        filename = file.filename or "upload.dat"
        # 1. Attachment security scan
        scan = clamav_scanner.scan_bytes(content, filename=filename)
        if not scan.is_clean:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security alert: Malicious attachment quarantined ({scan.threat_name}). Processing blocked.",
            )

        case = case_manager.create_case_from_upload(
            filename=filename,
            content=content,
            title=title,
            customer_label=customer_name,
        )
    else:
        content = (pasted_text or "").encode("utf-8")
        scan = clamav_scanner.scan_bytes(content, filename="pasted_text.txt")
        if not scan.is_clean:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security alert: Malicious content quarantined ({scan.threat_name}).",
            )
        case = case_manager.create_case_from_text(
            raw_text=pasted_text or "",
            title=title,
            customer_label=customer_name,
        )

    lines = case_manager.get_lines(case.case_id)
    return {
        "case": case,
        "lines": lines,
        "security_scan": {
            "engine": scan.engine,
            "is_clean": scan.is_clean,
            "file_digest": scan.file_digest,
        },
    }


@app.post("/v1/rfqs/{case_id}/match")
def v1_match_rfq(case_id: str):
    """V1 Match: Runs exact catalog matching and RapidFuzz candidate retrieval."""
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")

    lines = case_manager.get_lines(case_id)
    rapidfuzz_engine.index_catalog(catalog_repo.list_all())

    matched_results = []
    for line in lines:
        candidates = rapidfuzz_engine.find_candidates(
            requested_mpn=line.requested_mpn or "",
            requested_oem=line.requested_manufacturer,
        )
        matched_results.append({
            "line_id": line.line_id,
            "line_number": line.line_number,
            "requested_mpn": line.requested_mpn,
            "current_status": line.match_status,
            "candidate_count": len(candidates),
            "candidates": [
                {
                    "internal_sku": c[0].internal_sku,
                    "mpn": c[0].manufacturer_part_number,
                    "manufacturer": c[0].manufacturer,
                    "score": c[1],
                    "reason": c[2],
                }
                for c in candidates
            ],
        })

    return {"case_id": case_id, "results": matched_results}


@app.post("/v1/rfqs/{case_id}/draft-quote")
def v1_draft_quote(case_id: str, currency: str = "USD"):
    """V1 Draft Quote: Compiles ProposedQuote with provenance, authoritative pricing, and draft hash."""
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")

    lines = case_manager.get_lines(case_id)
    quote_lines: List[QuoteLine] = []

    for idx, line in enumerate(lines, start=1):
        # Look up price and provenance from authoritative catalog if matched
        catalog_item = (
            catalog_repo.get_by_sku(line.selected_catalog_sku)
            if line.selected_catalog_sku
            else None
        )

        unit_price = (
            Decimal(str(catalog_item.list_price))
            if catalog_item and catalog_item.list_price is not None
            else None
        )
        source_price_id = (
            f"CAT-{catalog_item.catalog_version}-{catalog_item.internal_sku}"
            if catalog_item and unit_price is not None
            else None
        )

        sources = []
        if line.source_locator:
            sources.append(
                SourceRef(
                    file_id=case.source_file.file_id if case.source_file else "unknown",
                    page=line.source_locator.page_number,
                    sheet=line.source_locator.sheet_name,
                    text_excerpt=line.source_locator.text_snippet,
                )
            )

        match_status_str = "exact" if line.match_status.value == "EXACT_MATCH" else "unmatched"

        quote_lines.append(
            QuoteLine(
                line_no=idx,
                requested_mpn=line.requested_mpn or "UNKNOWN",
                requested_manufacturer=line.requested_manufacturer,
                catalogue_part_id=catalog_item.internal_sku if catalog_item else None,
                description=line.description or (catalog_item.description if catalog_item else None),
                quantity=Decimal(str(line.quantity)) if line.quantity is not None else Decimal("0"),
                unit=line.unit or "EA",
                unit_price=unit_price,
                currency=currency,
                source_price_id=source_price_id,
                match_status=match_status_str,
                requires_human_review=line.review_decision.value != "APPROVED",
                sources=sources,
            )
        )

    quote_id = f"QUOTE-{case_id.replace('RFQ-', '')}"
    draft = ProposedQuote(
        quote_id=quote_id,
        case_id=case_id,
        customer_name=case.customer_label or "Valued Customer",
        currency=currency,
        lines=quote_lines,
    )

    registered = commercial_service.register_draft(draft)
    return registered


@app.get("/v1/quote-drafts/{quote_id}")
def v1_get_quote_draft(quote_id: str):
    """Retrieves a quotation draft with current hash and validation errors."""
    draft = commercial_service.get_draft(quote_id)
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote draft not found.")
    return draft


@app.post("/v1/quote-drafts/{quote_id}/approve")
def v1_approve_quote_draft(
    quote_id: str,
    expected_hash: str = Form(...),
    approver_name: str = Form("Inside Sales"),
):
    """Version-bound human approval of a quotation draft."""
    try:
        record = commercial_service.approve_draft(
            quote_id=quote_id,
            expected_hash=expected_hash,
            approver_name=approver_name,
        )
        return {"status": "success", "approval_record": record}
    except ApprovalGateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/v1/quote-drafts/{quote_id}/reject")
def v1_reject_quote_draft(
    quote_id: str,
    reason: str = Form(...),
    approver_name: str = Form("Inside Sales"),
):
    """Rejects quotation draft with explicit reason."""
    try:
        record = commercial_service.reject_draft(
            quote_id=quote_id,
            approver_name=approver_name,
            reason=reason,
        )
        return {"status": "success", "rejection_record": record}
    except ApprovalGateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/v1/approved-quotes/{quote_id}/send")
def v1_send_approved_quote(
    quote_id: str,
    expected_hash: str = Form(...),
    sender_name: str = Form("Inside Sales"),
):
    """Transmits quote strictly after human approval verification and hash validation."""
    try:
        result = commercial_service.send_approved_quote(
            quote_id=quote_id,
            expected_hash=expected_hash,
            sender_name=sender_name,
        )
        return {"status": "success", "transmission": result}
    except ApprovalGateError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

