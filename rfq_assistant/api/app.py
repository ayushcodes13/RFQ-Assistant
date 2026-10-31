"""FastAPI application for RFQ Assistant backend API."""

import hashlib
import json
import os
from pathlib import Path
from typing import List, Optional
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from decimal import Decimal
from rfq_assistant.agents.tools import ApprovalGateError, QuotationCommercialService
from rfq_assistant.auth import PilotUser, get_current_user, require_role
from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.exports import ExportGenerator, ExportValidationError
from rfq_assistant.ingestion.excel import ExcelBOMInspector
from rfq_assistant.ingestion.malware import ClamAVScanner
from rfq_assistant.ingestion.parsers.base import DocumentParserError
from rfq_assistant.ingestion.validator import UploadValidationError
from rfq_assistant.matching.catalog import CatalogImportError, CatalogRepository
from rfq_assistant.matching.fuzzy import RapidFuzzCandidateEngine
from rfq_assistant.persistence import SQLiteStateStore
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
_database_path = Path(os.environ.get("RFQ_ASSISTANT_DB_PATH", "storage/rfq_assistant.sqlite3"))
state_store = SQLiteStateStore(_database_path)
catalog_repo = CatalogRepository(state_store=state_store)
case_manager = CaseManager(catalog=catalog_repo, state_store=state_store)
export_generator = ExportGenerator(catalog=catalog_repo)
clamav_scanner = ClamAVScanner()
rapidfuzz_engine = RapidFuzzCandidateEngine()
commercial_service = QuotationCommercialService()

# Pre-load default synthetic catalog if available
if DEFAULT_CATALOG_PATH.exists() and catalog_repo.count() == 0:
    try:
        catalog_repo.import_csv(DEFAULT_CATALOG_PATH.read_bytes(), version="v1-synth")
        rapidfuzz_engine.index_catalog(catalog_repo.list_all())
    except Exception as e:
        print(f"Warning: Failed to pre-load default catalog: {e}")

def _rfq_source_snapshot_hash(case_id: str) -> str:
    """Fingerprint the *current* RFQ and item master, not a saved quotation copy.

    Including the full prototype catalog is deliberately conservative: any
    import/update requires re-drafting and re-approval. Customer deployments
    should replace this with versioned, workspace-scoped catalog snapshots.
    """
    case = case_manager.get_case(case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source RFQ no longer exists. Quote must not be approved or sent.",
        )
    payload = {
        "case_id": case_id,
        "customer_label": case.customer_label,
        "file_digest": case.source_file.sha256_digest if case.source_file else None,
        "lines": [line.model_dump(mode="json") for line in case_manager.get_lines(case_id)],
        "catalog": [
            item.model_dump(mode="json")
            for item in sorted(catalog_repo.list_all(), key=lambda row: row.internal_sku)
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_fresh_quote_source(quote_id: str) -> None:
    """Reject a saved draft if its underlying RFQ or catalog changed."""
    draft = commercial_service.get_draft(quote_id)
    if draft is None:
        return  # The commercial service reports the missing quote.
    if not draft.source_state_hash or draft.source_state_hash != _rfq_source_snapshot_hash(draft.case_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RFQ lines, reviewer decisions or catalog changed since this draft was created. Regenerate and review the quote.",
        )


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
async def import_catalog(
    file: UploadFile = File(...),
    current_user: PilotUser = Depends(require_role(["admin"])),
):
    """Imports tenant-authorized catalog CSV (admin only)."""
    content = await file.read()
    try:
        summary = catalog_repo.import_csv(content)
        return {"status": "success", "summary": summary}
    except CatalogImportError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/api/catalogs", response_model=List[CatalogItem])
def list_catalog(current_user: PilotUser = Depends(get_current_user)):
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
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
):
    """Creates draft case from an uploaded file or pasted email text with malware defense."""
    if not file and not pasted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either an uploaded file or pasted text.",
        )

    effective_actor = current_user.name if current_user.user_id != "usr-local-demo" else actor

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
                actor=effective_actor,
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
                actor=effective_actor,
            )
            return case
    except (UploadValidationError, DocumentParserError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@app.get("/api/rfqs", response_model=List[RFQCase])
def list_rfqs(current_user: PilotUser = Depends(get_current_user)):
    """Returns all RFQ cases sorted by date."""
    return case_manager.list_cases()


@app.get("/api/rfqs/{case_id}", response_model=RFQCase)
def get_rfq(case_id: str, current_user: PilotUser = Depends(get_current_user)):
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    return case


@app.get("/api/rfqs/{case_id}/lines", response_model=List[RFQLineItem])
def get_rfq_lines(case_id: str, current_user: PilotUser = Depends(get_current_user)):
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    return case_manager.get_lines(case_id)


@app.get("/api/rfqs/{case_id}/source")
def get_original_source(
    case_id: str,
    current_user: PilotUser = Depends(get_current_user),
):
    """Open the original uploaded RFQ for human source verification.

    Always resolve the stored file from an existing authorized case, never from
    an arbitrary path supplied in the URL. Native PDF/text can open inline;
    XLSX is downloaded for inspection in the operator's spreadsheet tool.
    """
    from fastapi.responses import FileResponse

    case = case_manager.get_case(case_id)
    if not case or not case.source_file:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ source not found.")

    source = case_manager.storage.uploads_dir / case.case_id / case.source_file.file_name
    if not source.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Original source file is missing.")

    ext = source.suffix.lower()
    mime = {
        ".pdf": "application/pdf",
        ".csv": "text/csv",
        ".txt": "text/plain",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(ext, "application/octet-stream")

    return FileResponse(
        path=source,
        filename=case.source_file.file_name,
        media_type=mime,
        content_disposition_type="inline" if ext in {".pdf", ".txt", ".csv"} else "attachment",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.patch("/api/rfqs/{case_id}/lines/{line_id}", response_model=RFQLineItem)
def update_rfq_line(
    case_id: str,
    line_id: str,
    update: RFQLineItemUpdate,
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
):
    if current_user.user_id != "usr-local-demo":
        update.actor = current_user.name
    try:
        updated = case_manager.update_line(case_id, line_id, update)
    except ValueError as e:
        if "conflict" in str(e).lower() or "stale" in str(e).lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found.")
    return updated


@app.post("/api/rfqs/{case_id}/review")
def batch_review_lines(
    case_id: str,
    request: BatchReviewRequest,
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
):
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    if current_user.user_id != "usr-local-demo":
        request.actor = current_user.name
    count = case_manager.batch_review(case_id, request)
    return {"status": "success", "updated_count": count}


@app.get("/api/rfqs/{case_id}/audit", response_model=List[AuditEvent])
def get_rfq_audit_trail(case_id: str, current_user: PilotUser = Depends(get_current_user)):
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    return case_manager.get_audit_trail(case_id)


@app.delete("/api/rfqs/{case_id}")
def delete_rfq(
    case_id: str,
    current_user: PilotUser = Depends(require_role(["admin"])),
):
    """Deletes RFQ case (restricted to administrators)."""
    success = case_manager.delete_case(case_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")
    return {"status": "success", "deleted_case_id": case_id}


# ---------------------------------------------------------------------------
# Export Endpoints
# ---------------------------------------------------------------------------

@app.post("/api/rfqs/{case_id}/exports", response_model=ExportManifest)
def export_rfq_worksheet(
    case_id: str,
    request: ExportRequest,
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
):
    """Generates deterministic XLSX/CSV quote worksheet and email draft."""
    case = case_manager.get_case(case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ case not found.")

    lines = case_manager.get_lines(case_id)
    if current_user.user_id != "usr-local-demo":
        request.actor = current_user.name
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
def download_export(
    case_id: str,
    export_id: str,
    current_user: PilotUser = Depends(get_current_user),
):
    """Downloads the generated export artifact with strict case-scoping verification."""
    export_dir = Path("storage/exports") / export_id
    if not export_dir.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found.")

    manifest_path = export_dir / "manifest.json"
    if manifest_path.exists():
        import json
        with open(manifest_path, "r", encoding="utf-8") as mf:
            manifest_data = json.load(mf)
            if manifest_data.get("case_id") != case_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Export '{export_id}' does not belong to case '{case_id}'.",
                )

    files = [f for f in export_dir.iterdir() if f.name != "manifest.json"]
    if not files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export artifact missing.")

    artifact = files[0]
    if case_id not in artifact.name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export '{export_id}' does not belong to case '{case_id}'.",
        )

    from fastapi.responses import FileResponse
    media_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if artifact.suffix == ".xlsx"
        else "text/csv"
    )
    return FileResponse(path=str(artifact), filename=artifact.name, media_type=media_type)


@app.get("/api/rfqs/{case_id}/email-draft")
def get_unsent_email_draft(case_id: str, current_user: PilotUser = Depends(get_current_user)):
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
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
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
            actor=current_user.name,
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
            actor=current_user.name,
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
def v1_match_rfq(
    case_id: str,
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
):
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
def v1_draft_quote(
    case_id: str,
    currency: str = "USD",
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
):
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
        source_state_hash=_rfq_source_snapshot_hash(case_id),
        lines=quote_lines,
    )

    registered = commercial_service.register_draft(draft)
    return registered


@app.get("/v1/quote-drafts/{quote_id}")
def v1_get_quote_draft(quote_id: str, current_user: PilotUser = Depends(get_current_user)):
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
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
):
    """Version-bound human approval of a quotation draft."""
    _require_fresh_quote_source(quote_id)
    effective_approver = current_user.name if current_user.user_id != "usr-local-demo" else approver_name
    try:
        record = commercial_service.approve_draft(
            quote_id=quote_id,
            expected_hash=expected_hash,
            approver_name=effective_approver,
        )
        return {"status": "success", "approval_record": record}
    except ApprovalGateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/v1/quote-drafts/{quote_id}/reject")
def v1_reject_quote_draft(
    quote_id: str,
    reason: str = Form(...),
    approver_name: str = Form("Inside Sales"),
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
):
    """Rejects quotation draft with explicit reason."""
    effective_approver = current_user.name if current_user.user_id != "usr-local-demo" else approver_name
    try:
        record = commercial_service.reject_draft(
            quote_id=quote_id,
            approver_name=effective_approver,
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
    current_user: PilotUser = Depends(require_role(["admin", "reviewer"])),
):
    """Transmits quote strictly after human approval verification and hash validation."""
    _require_fresh_quote_source(quote_id)
    effective_sender = current_user.name if current_user.user_id != "usr-local-demo" else sender_name
    try:
        result = commercial_service.send_approved_quote(
            quote_id=quote_id,
            expected_hash=expected_hash,
            sender_name=effective_sender,
        )
        return {"status": "success", "transmission": result}
    except ApprovalGateError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

