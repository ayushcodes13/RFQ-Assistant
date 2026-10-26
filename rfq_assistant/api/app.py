"""FastAPI application for RFQ Assistant backend API."""

from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.validator import UploadValidationError
from rfq_assistant.matching.catalog import CatalogImportError, CatalogRepository
from rfq_assistant.schemas.models import (
    AuditEvent,
    BatchReviewRequest,
    CatalogItem,
    RFQCase,
    RFQLineItem,
    RFQLineItemUpdate,
)

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CATALOG_PATH = ROOT / "fixtures" / "catalogs" / "industrial_components_sample_catalog.csv"

# Global repositories and services
catalog_repo = CatalogRepository()
case_manager = CaseManager(catalog=catalog_repo)

# Pre-load default synthetic catalog if available
if DEFAULT_CATALOG_PATH.exists():
    try:
        catalog_repo.import_csv(DEFAULT_CATALOG_PATH.read_bytes(), version="v1-synth")
    except Exception as e:
        print(f"Warning: Failed to pre-load default catalog: {e}")

app = FastAPI(
    title="RFQ Assistant API",
    version="0.1.0",
    description="Human-reviewed RFQ intake and quotation preparation assistant",
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
    """Creates draft case from an uploaded file or pasted email text."""
    if not file and not pasted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either an uploaded file or pasted text.",
        )

    try:
        if file:
            content = await file.read()
            case = case_manager.create_case_from_upload(
                filename=file.filename or "upload.xlsx",
                content=content,
                title=title,
                customer_label=customer_label,
                actor=actor,
            )
            return case
        else:
            case = case_manager.create_case_from_text(
                raw_text=pasted_text or "",
                title=title,
                customer_label=customer_label,
                actor=actor,
            )
            return case
    except UploadValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
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
