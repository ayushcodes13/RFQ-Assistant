# Lean technical architecture

This is a **proposed** implementation, not a claim that the app exists.

## Guiding choices

- Keep a small monolith for v0. No orchestration framework or agent swarm.
- Use deterministic spreadsheet parsing and part-number matching first.
- Add PDF text/vision extraction only as needed for real fixtures.
- Every transformation must preserve source provenance and uncertainty.
- Write outputs only after schema and reviewer-state checks.

## Suggested stack

- Frontend: Next.js / TypeScript and a compact accessible data grid.
- Backend: Python / FastAPI with Pydantic schemas and background task queue only when required.
- Storage: SQLite for local prototype; PostgreSQL for customer deployments. The local API persists cases, lines, audit events, and catalog rows in `storage/rfq_assistant.sqlite3`; original files and exports remain in local storage directories. Private file storage with per-workspace keys/paths is still required for customer deployments.
- Data extraction: openpyxl/CSV parser for spreadsheets, text extraction for native PDFs, OCR/vision behind a single optional provider interface for scans.
- Match service: canonicalized *exact* part number + manufacturer matching over an imported catalog; possible collisions remain unresolved.
- Export: deterministic XLSX/CSV, quote-preparation template, plain text **unsent** email draft.
- Auth: local demo clearly labeled; production pilots require authenticated tenant isolation and access controls before any real data.

## Components

    Web Intake ----> Upload validation ----> File storage
          |                                    |
          v                                    v
    Case state <---- Extraction adapter <---- File parser
          |
          v
    Normalized line-item schema
          |
          v
    Catalog exact-match engine
          |
          v
    Human review / corrections / audit
          |
          v
    Export validator ----> CSV/XLSX + unsent email

The initial product must function with a fixture catalog and without an LLM for well-structured CSV/XLSX. If an LLM is used for PDF parsing, its output is treated as untrusted proposals.

## Minimal proposed record shapes

**RFQ case**
- case_id, workspace_id, source_files (name, MIME, digest, locator), created_at, status, case_title.
- processing_attempt_id, parser_version, parsed_at, warnings.

**RFQ line**
- line_id, case_id, source_locator (file, page/sheet, row or text span), source_snippet.
- raw_text, requested_manufacturer (optional), requested_mpn (optional), description, quantity (nullable), unit (nullable), required_by (nullable).
- extraction_status, extraction_warnings, extraction_version.

**Catalog row**
- catalog_row_id, catalog_version, internal_sku, manufacturer, manufacturer_part_number, description.
- Optional price or stock only with timestamp/source and explicit tenant policy.

**Match proposal**
- line_id, candidate_catalog_row_id, match_type (exact_mpn_manufacturer | collision | no_match | manual), explanation, evidence_locator.
- state (unreviewed | approved | needs_clarification | rejected), reviewed_by, reviewed_at.

**Audit event**
- case_id, line_id (optional), actor, action, old_value, new_value, recorded_at, source_context.

## Validation and matching rules

1. Preserve original raw input and full original manufacturer part number.
2. Normalize only safe variations in case/outer whitespace and punctuation **after tests per manufacturer**; never strip meaningful suffixes or revisions.
3. Manufacturer and MPN must both identify one catalog record for an automatic **candidate**. If manufacturer absent or duplicates exist, require manual choice.
4. Unknown part number, missing quantity, unit mismatch and conflicting email-vs-attachment values trigger a review blocker.
5. Similar description is for **search assistance only**, not certified interchangeability.
6. Do not silently deduplicate identical part numbers requested on different lines; retain quantities, packaging and notes per source.
7. Exports must validate quantity > 0, supported unit, mandatory columns, cleared conflicts and explicit reviewer authorization.
8. Review actions are versioned; a fresh parse must not silently replace human corrections.

## Prototype API proposal

- POST /api/rfqs — create draft case with uploaded file or pasted text.
- GET /api/rfqs/{id} — case, status and warnings.
- GET /api/rfqs/{id}/lines — extracted lines, evidence and review status.
- PATCH /api/rfqs/{id}/lines/{line_id} — human correction, optimistic concurrency control.
- POST /api/rfqs/{id}/review — confirm a set of line decisions with actor ID.
- POST /api/catalogs/import — validate/import tenant-authorized CSV.
- POST /api/rfqs/{id}/exports — request draft export after validation.
- GET /api/rfqs/{id}/exports/{export_id} — download authorized artifact.
- DELETE /api/rfqs/{id} — delete case and uploaded artifacts subject to agreed retention policy.

These endpoints are implemented in the prototype backend. The FastAPI OpenAPI
schema is checked in as `frontend/openapi.json`; `frontend/src/types/api.generated.ts`
is generated from it with `openapi-typescript`, and
`tests/test_openapi_contract.py` fails if the checked-in schema drifts from the
live app. Regenerate with:

```bash
python -m rfq_assistant.scripts.export_openapi
cd frontend && npm run gen:types
```

## Security and reliability boundaries

- Validate actual file content, not extension alone; reject macros/executables and external references.
- Configure max upload size/pages/sheets/rows and parsing time limits.
- Content in PDF/email is untrusted user data; no instruction following or tool invocation from it.
- Do not send customer uploads to third-party AI APIs without explicit consent, documented provider, retention terms and region suitability.
- Avoid passing entire files to LLMs if only small fields need processing.
- Tenant segregation, minimal rights, deletion, private objects, TLS and audit are required before production.
- Use fixture-based regression tests and fail closed when provenance is missing.
- Export rows should be reproducible from input digest, parser version, catalog version and reviewer decisions.

## Scaling policy

Do **not** build queue infrastructure, pgvector, semantic search, ERP connectors, background crawlers or enterprise multi-tenant billing without evidence they solve the first pilot's bottleneck. Favor the smallest reliable working slice.
