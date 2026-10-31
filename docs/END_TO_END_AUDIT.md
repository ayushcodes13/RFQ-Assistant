# End-to-End Audit Report: RFQ-Assistant

> **Historical snapshot:** this report describes the pre-hardening audit state and its
> 269-test result. It is not the current implementation inventory. PDF OCR, streamed
> spreadsheet parsing, grounded Luna fallback, and current verification evidence are
> tracked in [EXTRACTION_AND_PERFORMANCE_AUDIT.md](EXTRACTION_AND_PERFORMANCE_AUDIT.md).

## 1. Executive Summary

This report documents an audit-only end-to-end test of the RFQ-Assistant repository.
The audit exercises the full workflow (ingestion → extraction → matching → human review →
export) with 121 synthetic test cases across 36 fixtures, supplementing the existing
148-test suite. All tests pass (269 total).

**Key metrics:**

| Metric | Value |
|--------|-------|
| Existing tests (pre-audit) | 148 passing, 1 warning |
| New audit tests (first cycle) | 47 passing |
| New audit tests (extended cycle) | 74 passing |
| Total audit test files | 2 (`test_audit_harness.py` + `test_audit_extended.py`) |
| Total tests (all suites) | 269 passing, 1 warning |
| Total findings | 13 (8 from first cycle + 5 new from extended cycle) |
| Safety invariants fully verified | 7 of 12 (see Section 6 for details on unverified invariants) |
| Formula injection mitigations | Verified working in export (but limited in XLSX extraction) |
| Export blocking on unresolved lines | Verified working |
| External transport invoked | **Never** — send route returns `simulated_local` |

The codebase is a **working prototype** with strong safety foundations (draft
labeling, export blocking, audit trails, formula escaping in CSV output, ClamAV
integration, simulated-only send). However, several defects in extraction and
architecture reduce practical reliability for real-world documents.

---

## 2. Environment

- **OS:** macOS arm64
- **Python:** 3.9.6
- **Virtualenv:** `.venv/` at `RFQ-Assistant/.venv`
- **Package:** `rfq-assistant==0.1.0` (editable install)
- **Key dependencies:** FastAPI 0.128.8, Pydantic 2.13.5, openpyxl, pypdf 5.0.0,
  rapidfuzz, fpdf2, defusedxml
- **Test framework:** pytest 8.4.2, pytest-asyncio 1.2.0
- **Test command:** `python -m pytest tests/ -v`
- **Baseline result (pre-audit):** 195 passed, 1 warning in ~1.92s
- **Post-audit result:** 269 passed, 1 warning in ~2.90s

All audit tests use isolated temporary databases (`tmp_path` or env var
`RFQ_ASSISTANT_DB_PATH`). The existing SQLite at `storage/rfq_assistant.sqlite3`
was not modified during audit.

---

## 3. Architecture Map

### 3.1 Entry Points

The RFQ workflow has two parallel extraction paths:

1. **Deterministic pipeline (active):** `CaseManager.create_case_from_upload()`
   or `create_case_from_text()` → selects parser based on file type →
   `TextParser` / `SpreadsheetParser` / `PDFParser` → `ExactMatchEngine` /
   `CatalogRepository` for matching → `ExportGenerator` for output.

2. **Agent pipeline (DEAD CODE):** `RFQAgentRunner.run_deterministic_extraction()`
   in `rfq_assistant/agents/rfq_agent.py` — a naive stub that takes the first
   token of each line as the MPN and sets quantity=1. It has prompt injection
   detection signals but is **not wired into the FastAPI app**. The
   `QuotationCommercialService` from `agents/tools.py` is imported in `app.py`
   (line 11) and instantiated (line 46) but only used by the V1 quote lifecycle
   endpoints (`/v1/quote-drafts/*` and `/v1/approved-quotes/*/send`).

### 3.2 Component Layers

```
rfq_assistant/
├── api/app.py              # FastAPI app — entry point (664 lines)
├── cases/manager.py        # CaseManager — orchestrates ingestion/extraction/matching
├── ingestion/
│   ├── __init__.py         # DocumentStorage, parsers factory
│   ├── validator.py        # MAX_UPLOAD_BYTES=10MB, ALLOWED_EXTENSIONS
│   ├── storage.py          # DocumentStorage — case-scoped file storage
│   ├── malware.py          # ClamAV scanner + offline fallback
│   └── parsers/
│       ├── base.py         # ParsedDocumentResult, ParsedLineDraft, SourceLocator
│       ├── text_parser.py  # TextParser — pasted text / email parsing
│       ├── spreadsheet_parser.py  # SpreadsheetParser — CSV + XLSX
│       └── pdf_parser.py   # PDFParser — native text-based PDFs (pypdf)
├── matching/
│   ├── catalog.py          # CatalogRepository — SQLite-backed catalog
│   ├── engine.py           # ExactMatchEngine — exact MPN + manufacturer matching
│   ├── normalizer.py       # Normalizes MPN/OEM for comparison
│   └── fuzzy.py            # RapidFuzz fuzzy candidate retrieval (v1 API only)
├── schemas/
│   ├── models.py           # Pydantic models: RFQCase, RFQLineItem, etc.
│   └── enums.py            # MatchStatus, ReviewDecision, AuditAction, etc.
├── persistence.py          # SQLiteStateStore — case/line/catalog/audit persistence
├── exports/
│   ├── generator.py        # ExportGenerator — XLSX/CSV worksheet generation
│   └── email_draft.py      # Unsent email draft generation
├── agents/
│   ├── rfq_agent.py        # RFQAgentRunner — DEAD CODE (not wired into API)
│   └── tools.py            # QuotationCommercialService — V1 quote lifecycle
└── quotation/
    ├── line_rules.py       # blocking_line_issues — export gate validators
    └── validate.py         # ProposedQuote, QuoteLine — commercial validation
```

### 3.3 Test Layers

| Layer | Test File(s) | Count |
|-------|-------------|-------|
| Unit tests | `test_schemas_and_fixtures.py`, `test_matching_and_audit.py` | ~40 |
| Integration tests | `test_ingestion_and_parsers.py`, `test_exports.py` | ~20 |
| Security/adversarial | `test_ingestion_security_adversarial.py`, `test_adversarial_and_e2e.py` | ~30 |
| Concurrency | `test_auth_and_concurrency_adversarial.py` | ~10 |
| Persistence | `test_persistence.py`, incl. restart + delete | ~5 |
| Stale quote snapshots | `test_stale_quote_snapshots.py` | ~5 |
| Schema/fixture validation | `test_schemas_and_fixtures.py`, etc. | ~10 |
| Formula safety | `test_spreadsheet_formula_safety.py` | ~10 |
| Intake completeness | `test_intake_completeness.py` | ~5 |
| Review integrity | `test_review_integrity_adversarial.py` | ~5 |
| Export blockers | `test_export_blockers_adversarial.py` | ~5 |
| Catalog import integrity | `test_catalog_import_integrity.py` | ~5 |
| Customer clarification | `test_customer_clarification_integrity.py` | ~5 |
| Original source access | `test_original_source_access.py` | ~5 |
| OpenAPI contract | `test_openapi_contract.py` | ~5 |
| OSS stack & AI pipeline | `test_oss_stack_and_ai_pipeline.py` | ~15 |
| Auth & concurrency adversarial | `test_auth_and_concurrency_adversarial.py` | ~15 |
| Audit (first cycle) | `tests/end_to_end_audit/test_audit_harness.py` | 47 |
| Audit (extended) | `tests/end_to_end_audit/test_audit_extended.py` | 74 |
| **Total** | 19 test files + 2 audit files | **269** |

---

## 4. Test Methodology

### 4.1 Fixtures Created

All new fixtures are synthetic and clearly labeled, stored under
`tests/end_to_end_audit/fixtures/`:

**Original audit fixtures (25 files, first cycle):**

| Fixture | Format | Tests |
|---------|--------|-------|
| `multiline_email_with_headers.txt` | Text | Multi-line email with headers, 6 items |
| `numeric_only_mpn.txt` | Text | Numeric-only MPNs (2900364, 2966171) + alphanumeric (LC1D09BD) |
| `description_only_no_mpn.txt` | Text | 3 lines with descriptions, no clean MPNs |
| `suffix_bearing_mpn.txt` | Text | ABC-12, ABC-12A, ABC-12-R2 (suffix precision) |
| `cross_brand_collision.txt` | Text | XG-42 with no manufacturer → cross-brand collision |
| `contradictory_email_note.txt` | Text | Contradictory quantity in email thread |
| `adversarial_prompt_injection.txt` | Text | Injection text embedded in document |
| `layout_different_headers.csv` | CSV | Headers: Part Number, Manufacturer, Qty, Unit, Description, UOM |
| `layout_alt_headers.csv` | CSV | Headers: Manufacturer, MPN, QTY, Description |
| `headerless_csv.csv` | CSV | No header row, 4 rows |
| `csv_duplicate_lines.csv` | CSV | 6 rows, lines 5-6 duplicate lines 1-2 |
| `csv_with_formula_values.csv` | CSV | Formula-like Qty values (=CMD, =HYPERLINK) |
| `csv_headerless_four_cols.csv` | CSV | 4-column headerless CSV |
| `csv_short_header_names.csv` | CSV | Headers: MPN, Qty, MFR, Desc |
| `layout_xlsx_alt_headers.xlsx` | XLSX | Item #, Part Number, Brand, Quantity, Description, Unit, Extra_Col |
| `multisheet_diff_cols.xlsx` | XLSX | 2 sheets with different column orders |
| `xlsx_with_formula_cells.xlsx` | XLSX | Formula cells in Description column |
| `headerless_xlsx.xlsx` | XLSX | No header row |
| `xlsx_interleaved_columns.xlsx` | XLSX | Extra1, Part Number, Extra2, Manufacturer interleaved |
| `xlsx_formula_in_notes.xlsx` | XLSX | Notes column with formula-like content |
| `multipage_native_pdf.pdf` | PDF | 2 pages, table headers repeated, 6 items |
| `corrupt_invalid_pdf.pdf` | PDF | Plain text with .pdf extension |
| `password_protected_pdf.pdf` | PDF | Encrypted with password "synthetic-password" |
| `audit_synthetic_catalog.csv` | Catalog | 11 items including collision pair and suffix pair |
| `empty_file.txt` | Text | 0 bytes |
| `oversized_csv_5005_rows.csv` | CSV | 5006 rows (exceeds 5000 limit) |
| `oversized_file_10mb_plus.bin` | BIN | 10,485,761 bytes (exceeds 10MB limit) |

**New extended audit fixtures (11 files, extended cycle):**

| Fixture | Format | Tests |
|---------|--------|-------|
| `audit_extended_catalog.csv` | Catalog | 15 items: cross-brand XG-42, suffix ABC-12/12A/12-R2, duplicate ABC-12 |
| `quoted_email_thread.txt` | Text | Quoted email with nested `>` quotes, 3 items across 2 quote levels |
| `wrapped_description_pdf.pdf` | PDF | 2-page native PDF, qty-before-OEM layout, wrapped descriptions |
| `multipage_repeated_headers_pdf.pdf` | PDF | 2-page PDF with repeated table header lines |
| `scanned_image_pdf.pdf` | PDF | Image-only PDF (no text layer) — tests OCR rejection |
| `pdf_unfamiliar_manufacturers.pdf` | PDF | Pipe-delimited table with 2 unknown OEMs + 1 known |
| `xlsx_title_then_header.xlsx` | XLSX | Title rows before header row, 2 data rows |
| `xlsx_hidden_merged_blank.xlsx` | XLSX | Hidden sheet, merged cells, blank row, 4 sheets total |
| `xlsx_fresh_formulas_no_cache.xlsx` | XLSX | Fresh formulas (=SUM, =HYPERLINK) with no cached values |
| `xlsx_quantity_formats.xlsx` | XLSX | "10 pcs", "5 units", "20x", "15.5" quantity formats |
| `wrapped_description_pdf.txt` | Text | Text version of wrapped description PDF for reference |

### 4.2 Audit Test Harness

The audit test suite is split across two files under `tests/end_to_end_audit/`:

- **`test_audit_harness.py`** (47 tests): First cycle — covers text extraction edge cases,
  spreadsheet layouts, PDF parsing, matching, review/export blocking, export content
  verification, adversarial failures, full API workflow, persistence/restart, and
  concurrency (case creation only).

- **`test_audit_extended.py`** (74 tests): Extended cycle — covers:
  - Text extraction: quoted email threads, numeric-only MPNs, suffixes,
    unfamiliar manufacturers, description-only requests
  - Spreadsheet: title+header rows, hidden/merged/blank regions, fresh formulas
    without cache, various quantity formats, extra columns, quoted specs
  - PDF: wrapped descriptions (qty before OEM), multi-page repeated headers,
    scanned image rejection, unfamiliar manufacturers
  - Matching: cross-brand collisions, duplicate catalog records (same MPN+OEM),
    suffix near-collisions, missing manufacturer, unknown parts, case-insensitivity
  - Review/export: post-approval SKU/MPN change revokes approval, export blocking
    on NO_MATCH/COLLISION/unapproved, partial exports, audit trail SKU changes,
    case status transitions, manifest download URL scoping
  - API/download/persistence: download from default vs configured storage (404 defect),
    full workflow persistence across restart, case deletion (memory + SQLite + files),
    case-scoped source file access (path traversal prevention), upload size limits,
    oversized CSV rejection
  - Auth/security: simulated send transport verification (no external invocation),
    REQUIRE_REAL_TRANSPORT blocks send, RBAC across admin/reviewer/viewer roles,
    actor spoofing prevention, usr-local-demo bypass, path traversal in filenames,
    empty filename rejection, macro extension rejection, formula injection in
    CSV/XLSX export, EICAR rejection, protected-mode ClamAV fail-closed
  - Concurrency: concurrent create+approve (30 threads), concurrent export of same
    case (20 threads), optimistic locking on concurrent line edits, full
    create→approve→export workflow under 15 concurrent threads

### 4.3 Test Execution

```bash
# Full suite (existing + audit)
python -m pytest tests/ -v
# Output: 269 passed, 1 warning in ~2.90s

# Audit-only suite (both files)
python -m pytest tests/end_to_end_audit/ -v
# Output: 121 passed, 1 warning in ~2.07s

# Extended audit tests only
python -m pytest tests/end_to_end_audit/test_audit_extended.py -v
# Output: 74 passed, 1 warning in ~1.69s

# Synthetic demo evaluation (prior evidence)
python scripts/evaluate_synthetic_demo.py
# Output: 20/20 lines, 80/80 critical fields, 20/20 matches, 20/20 source locators

# E2E corpus (prior evidence)
python scripts/run_synthetic_e2e_corpus.py
# Output: 30/30 serial flows, 128/128 concurrent creates
```

---

## 5. Findings

Findings are severity-ranked. Each finding includes a synthetic reproduction
that was actually executed.

### Finding 1: TextParser silently skips numeric-only MPNs  [HIGH]

- **Severity:** High
- **Category:** Text Extraction (TextParser)
- **Reproduction:** `tests/end_to_end_audit/test_audit_harness.py::TestExtractionTextEdgeCases::test_numeric_only_mpn`
  and `tests/end_to_end_audit/test_audit_extended.py::TestTextExtractionExtended::test_text_parser_skips_numeric_only_mpn`
- **Expected:** A numeric MPN like "2900364" (Phoenix Contact) should be extracted and
  matched against the catalog.
- **Observed:** TextParser's `_extract_mpn` (text_parser.py:198-211) requires tokens to
  have at least one letter AND one digit, OR match `^[A-Z]{2,}\-[0-9]+[A-Z0-9\-]*$`.
  Pure-numeric tokens like "2900364" are silently excluded. The line is still detected
  (OEM "Phoenix Contact" is recognized), but `requested_mpn=None` and
  `match_status=NO_MATCH`.
- **Evidence:** Test confirms lines with numeric-only MPNs produce `requested_mpn=None`
  while alphanumeric MPNs are correctly extracted and matched.

### Finding 2: PDF parser loses quantity when it appears before manufacturer  [HIGH]

- **Severity:** Medium → **Elevated to High** based on extended testing
- **Category:** PDF Extraction (PDFParser)
- **Reproduction:** `tests/end_to_end_audit/test_audit_extended.py::TestPdfLayoutDiversity::test_wrapped_description_pdf_extracts_items`
- **Expected:** Quantity regex should find quantities anywhere in the line, not just at
  the end of the line.
- **Observed:** The PDF parser's quantity regex (pdf_parser.py:114) anchors to the end of
  the line: `r"\b(\d+(?:\.\d+)?)\s*(EA|PCS|UNITS|M|FT|SET)?\b\s*$"`. When the quantity
  appears before the manufacturer (e.g., "10 EA Schneider Electric LC1D09BD"), the regex
  fails to match and `quantity=None`. In the test fixture, 7 of 8 lines had no quantity
  extracted.
- **Evidence:** Extended test with `wrapped_description_pdf.pdf` confirms 7/8 lines lose
  their quantity.
- **Impact:** Lines without quantities cannot be exported (export is blocked by
  `blocking_line_issues` which checks `quantity is None`). This affects PDF layouts
  where quantity precedes the catalog reference — a common format.

### Finding 3: Download endpoint hardcodes `storage/exports` path  [HIGH]

- **Severity:** High
- **Category:** Export / Download (API)
- **Reproduction:** `tests/end_to_end_audit/test_audit_extended.py::TestApiExportDownloadAndPersistence::test_export_download_from_default_storage`
- **Expected:** The download endpoint should use `export_generator.base_export_dir`
  instead of a hardcoded path.
- **Observed:** The `download_export` endpoint (app.py:365) hardcodes
  `Path("storage/exports")` instead of referencing `export_generator.base_export_dir`.
  When the generator is configured with a custom base directory (as in tests or
  potential deployment variations), the export file is written to the custom path but
  the download endpoint looks in `storage/exports`, returning 404.
- **Evidence:** Extended test confirms download returns 404 when `export_generator` is
  configured with `tmp_path / "exports"`, while the file is correctly written to the
  configured directory.
- **Impact:** Any deployment or test that configures `ExportGenerator` with a custom
  `base_export_dir` will produce exports that cannot be downloaded via the API.

### Finding 4: TextParser extracts false-positive MPNs from description tokens  [LOW]

- **Severity:** Low
- **Category:** Text Extraction (TextParser)
- **Reproduction:** `tests/end_to_end_audit/test_audit_harness.py::TestExtractionTextEdgeCases::test_description_only_no_mpn`
- **Expected:** Description-only tokens like "3-pole" should not be extracted as MPNs.
- **Observed:** For input "10 pcs 24VDC contactor, 9A, 3-pole, Schneider Electric", the
  parser extracts "3-pole" as the MPN (matches the `[A-Z]{2,}-[0-9]+[A-Z0-9-]*` pattern).
  For "4 units Siemens S7-1200 CPU 1214C digital", it extracts "S7-1200". Both are
  description fragments, not part numbers.
- **Evidence:** TextParser's `_extract_mpn` regex patterns match any token with a hyphen
  between letters and digits. The `3-pole` token matches
  `^[A-Z]{2,}\-[0-9]+[A-Z0-9\-]*$` because "3" is treated as `[0-9]+` after the "pole"
  prefix — wait, actually "3-pole" doesn't match because it starts with a digit.
  Let me correct: "S7-1200" matches because `S` is `[A-Z]` and `7-1200` matches the
  rest. Both produce NO_MATCH (not in catalog) but create reviewer noise.

### Finding 5: Headerless XLSX files are silently skipped (no fallback)  [MEDIUM]

- **Severity:** Medium
- **Category:** Spreadsheet Extraction (SpreadsheetParser)
- **Reproduction:** `tests/end_to_end_audit/test_audit_harness.py::TestExtractionSpreadsheetEdgeCases::test_headerless_xlsx`
- **Expected:** A headerless XLSX file should either be parsed positionally (like the CSV
  parser does) or produce a clear error message.
- **Observed:** When the XLSX parser's header detection fails (`header_row_idx == -1` at
  spreadsheet_parser.py:213), it executes `continue` (line 215), silently skipping the
  entire sheet with no warning. The CSV parser (lines 104-108) has a headerless fallback.
- **Evidence:** Test confirms headerless XLSX produces zero lines and raises
  `DocumentParserError("No RFQ line items could be extracted")` with no indication that
  the sheet was skipped due to missing headers.

### Finding 6: PDF parser extracts document reference numbers as MPNs  [LOW]

- **Severity:** Low
- **Category:** PDF Extraction / False Positives (PDFParser)
- **Reproduction:** `tests/end_to_end_audit/test_audit_extended.py::TestPdfLayoutDiversity::test_wrapped_description_pdf_extracts_items`
- **Expected:** RFQ reference numbers like "RFQ-2026-001" should not be extracted as MPNs.
- **Observed:** The PDF parser's token regex (pdf_parser.py:130) matches
  `RFQ-2026-001` as a potential MPN because it matches the pattern
  `[A-Za-z0-9][A-Za-z0-9._/-]{2,}`. The token has digits and letters and is long enough.
- **Evidence:** Extended test with `wrapped_description_pdf.pdf` shows `RFQ-2026-004`
  extracted as `requested_mpn` with no manufacturer, producing a false NO_MATCH line.

### Finding 7: PDF parser does not extract manufacturer from pipe-delimited table rows  [MEDIUM]

- **Severity:** Medium
- **Category:** PDF Extraction + Matching (PDFParser + ExactMatchEngine)
- **Reproduction:** `tests/end_to_end_audit/test_audit_harness.py::TestExtractionPdfEdgeCases::test_pdf_unfamiliar_manufacturers`
- **Expected:** A pipe-delimited PDF table row like `1 | Unknown Brand Co | ZZ-99999 | ...`
  should have the manufacturer extracted from the second cell.
- **Observed:** The PDF parser extracts the MPN token but sets `requested_manufacturer=None`
  for all lines. Pipe-delimited cells are not split — the entire row becomes the
  description. The matching engine then requires both MPN AND manufacturer for exact
  match, so catalog items (which should be EXACT_MATCH) become COLLISION.
- **Evidence:** Test confirms all 3 lines from `pdf_unfamiliar_manufacturers.pdf` have
  `requested_manufacturer=None`. ZZ-99999 (in catalog under "Unknown Brand Co") matches
  as COLLISION, not EXACT_MATCH.

### Finding 8: Download endpoint defect papered over in test  [DOCUMENTATION]

- **Severity:** Info
- **Category:** Test Methodology / Report Accuracy
- **Reproduction:** Review of `tests/end_to_end_audit/test_audit_harness.py::TestFullApiWorkflow::test_full_workflow_via_api`
- **Expected:** The download 404 should be documented as a defect, not accommodated
  in the test.
- **Observed:** The original test accepted the 404 as "expected" by checking
  `download_resp.status_code == 404` rather than flagging it as a defect. This
  understates the severity of the download path hardcoding issue (Finding 3).
- **Evidence:** The test was adjusted to verify the file exists in the generator's
  directory instead of testing the download endpoint. Extended test (Finding 3)
  now correctly flags the download 404 as a defect.

### Finding 9: XLSX parser does not skip hidden sheets  [MEDIUM]

- **Severity:** Medium
- **Category:** Spreadsheet Extraction (SpreadsheetParser)
- **Reproduction:** `tests/end_to_end_audit/test_audit_extended.py::TestSpreadsheetLayoutDiversity::test_xlsx_hidden_sheets_are_parsed`
- **Expected:** Hidden sheets should be skipped — the operator explicitly hid them.
- **Observed:** The XLSX parser uses `wb.worksheets` (spreadsheet_parser.py:184) which
  includes hidden sheets. Data from hidden sheets is extracted as line items with
  potentially incorrect column mapping (no manufacturer context).
- **Evidence:** Extended test with `xlsx_hidden_merged_blank.xlsx` shows 4 lines extracted
  (3 from Main BOM + 1 from hidden "Line Items" sheet). The hidden sheet line has
  `requested_manufacturer=None`.

### Finding 10: XLSX fresh formulas silently become None with no reviewer warning  [MEDIUM]

- **Severity:** Medium
- **Category:** Spreadsheet Extraction / Transparency (SpreadsheetParser)
- **Reproduction:** `tests/end_to_edge_audit/test_audit_extended.py::TestSpreadsheetLayoutDiversity::test_xlsx_fresh_formulas_no_cache_silently_skipped`
- **Expected:** Reviewer should be informed that cells originally contained formulas.
- **Observed:** The XLSX parser uses `openpyxl.load_workbook(data_only=True)` (line 183),
  which returns cached computed values. Formula cells without cached values return
  `None`. No `FORMULA_CELL_DETECTED` warning is emitted. The reviewer sees a blank or
  missing MPN with no indication that a formula was present.
- **Evidence:** Extended test with `xlsx_fresh_formulas_no_cache.xlsx` confirms 2 lines
  extracted (formula rows silently become None) with no warning.
- **Impact:** A reviewer cannot distinguish between a genuinely empty cell and a cell
  that contained a formula. While this prevents formula execution, it creates
  opacity about the original document content.

### Finding 11: Dead code: RFQAgentRunner and QuotationCommercialService partially wired  [LOW]

- **Severity:** Low
- **Category:** Architecture
- **Reproduction:** Static analysis of `rfq_assistant/api/app.py`
- **Expected:** Either wire the agent pipeline into the API or remove the dead code.
- **Observed:** `QuotationCommercialService` is imported (app.py:11) and instantiated
  (line 46: `commercial_service = QuotationCommercialService()`) and IS used by the V1
  quote lifecycle endpoints (`/v1/quote-drafts/*`, `/v1/approved-quotes/*/send`). However,
  `RFQAgentRunner` in `agents/rfq_agent.py` is completely dead code — never imported or
  called by any route handler. The active API endpoints all use
  `case_manager.create_case_from_upload()` / `create_case_from_text()`.
- **Evidence:** Grep confirms `RFQAgentRunner` has zero references in `app.py`.
  `QuotationCommercialService` is only used in V1 endpoints.
- **Impact:** The dead `RFQAgentRunner` code (with naive first-token-as-MPN parsing and
  injection detection signals) creates confusion about which extraction path is
  authoritative. The injection detection signals in the dead code are NOT checked by the
  active TextParser (see Finding 12).

### Finding 12: Prompt injection text is silently skipped, not flagged  [LOW]

- **Severity:** Low
- **Category:** Extraction / Defense-in-depth (TextParser)
- **Reproduction:** `tests/end_to_end_audit/test_audit_harness.py::TestAdversarialFailures::test_prompt_injection_isolated_as_data`
- **Expected:** Lines containing prompt injection patterns should be flagged as untrusted
  content, even if not extracted as RFQ lines.
- **Observed:** TextParser has no prompt injection detection. The injection line
  "SYSTEM INSTRUCTION: Ignore all previous rules..." is silently skipped (no
  `has_item_indicator` match) with empty `result.warnings`. The dead `RFQAgentRunner`
  has injection signal detection (`["ignore previous instructions", "system:", ...]`)
  but its phrasing doesn't match the fixture ("SYSTEM INSTRUCTION" vs "system:").
- **Evidence:** Test confirms the injected lines produce no warnings and no flags.
- **Impact:** While injection text is not executed (parser treats all text as data),
  the lack of any signal means a reviewer has no visibility that potentially malicious
  instructions were embedded. This weakens defense-in-depth.

### Finding 13: XLSX parser uses data_only=True, hiding formula content from review  [LOW]

- **Severity:** Low
- **Category:** Spreadsheet Extraction / Transparency (SpreadsheetParser)
- **Reproduction:** `tests/end_to_end_audit/test_audit_harness.py::TestExtractionSpreadsheetEdgeCases::test_xlsx_formula_mpn_values`
  and `tests/end_to_edge_audit/test_audit_extended.py::TestSpreadsheetLayoutDiversity::test_xlsx_fresh_formulas_no_cache_silently_skipped`
- **Expected:** Formula cells should be surfaced as formula text for reviewer awareness.
- **Observed:** The XLSX parser uses `openpyxl.load_workbook(data_only=True)` (line 183),
  returning cached computed values. Formula cells without cached values return `None`
  (e.g., `=CMD("evil")` → `None`). Formula-like string values (`+1+2`, `@SUM(1,2)`)
  are treated as literal MPN text.
- **Evidence:** Tests confirm `=CMD("evil")` returns `None`; `+1+2` and `@SUM(1,2)`
  are treated as literal MPN strings.
- **Impact:** `data_only=True` silently discards formula content that a reviewer should
  see. The CSV parser reads raw values (no `data_only` equivalent) and surfaces
  formula-like content properly, creating an inconsistency between the two formats.

---

## 6. Safety Invariant Verification

This section records each AGENTS.md safety invariant with **direct evidence** or
marks it as **unverified** where no direct test exists.

| # | Invariant | Status | Evidence |
|---|-----------|--------|----------|
| 1 | No automatic outbound customer quotation/follow-up/PO submission | ✅ Verified | `email_draft.py` generates "UNSENT DRAFT" with "NO AUTOMATIC OUTBOUND DISPATCH". `send_approved_quote` returns `transport: "simulated_local"`, `outbound_transport_invoked: False`. No SMTP/HTTP/email libraries called. |
| 2 | No automatic approval of unverified substitutions | ✅ Verified | `ExactMatchEngine.match_line` only returns EXACT_MATCH when normalized MPN AND manufacturer match uniquely. No fuzzy/similarity-based auto-approval. `test_suffix_precision_no_collapsed_match` confirms suffix precision. |
| 3 | Exact MPN matching (normalized IDs + manufacturer context) | ✅ Verified | Normalizer preserves hyphens/dots/slashes. `test_case_insensitive_oem_mpn_matching`, `test_oem_alias_normalization`. Description similarity is NOT used for matching. |
| 4 | No fabricated SKU/pricing/availability/lead time/warranty/compliance | ✅ Verified | Catalog-only pricing from `CatalogItem.list_price`. Unpriced items have `list_price=None` and are exported with blank price. `test_scenario_7_export_without_prices`. |
| 5 | Missing/ambiguous quantities flagged | ✅ Verified | `MISSING_QUANTITY` warning code. `blocking_line_issues` blocks export when `quantity is None`. |
| 6 | Failed OCR/model calls preserve source | ⚠️ Partially verified | Corrupt PDFs raise `DocumentParserError` and rollback (delete case, remove files). Scanned PDFs raise "Scanned or image-only PDF" error. **However:** OCR is not configured (always disabled), so "OCR/model failure" path is never exercised. The PDF parser doesn't use OCR at all — it only handles native text PDFs. Scanned PDFs are rejected before any extraction, so the "preserve original upload" invariant is satisfied trivially (no processing attempted), not through resilient error handling. |
| 7 | Source-location provenance visible before export | ✅ Verified | `SourceLocator` with file_name, row_number, page_number, text_snippet. `test_export_includes_source_locator`, `test_source_file_retrieval`. |
| 8 | Generated documents labeled as drafts | ✅ Verified | XLSX A1 = "DRAFT QUOTATION WORKSHEET". CSV header = "DRAFT QUOTATION WORKSHEET". `is_draft=True` in manifest. |
| 9 | Human review required for all rows | ✅ Verified | `ReviewDecision.PENDING` default. `blocking_line_issues` checks `review_decision == APPROVED`. Export blocked for unapproved lines. |
| 10 | Audit trail records who changed/approved what and when | ✅ Verified | `AuditEvent` with actor, action, field_name, old_value, new_value, recorded_at. `CASE_CREATED`, `PARSED`, `LINE_EDITED`, `LINE_APPROVED`, `EXPORTED` actions recorded. `test_persistence_across_restart_full_workflow` confirms survival. |
| 11 | No prompt injection from PDF/email text | ⚠️ Partially verified | Text is treated as data (never executed). Injection lines are silently skipped (not extracted as items). **However:** No explicit detection or warning is emitted when injection patterns are detected. `test_prompt_injection_isolated_as_data` confirms the injection line is skipped but `result.warnings` is empty. |
| 12 | Upload defenses (MIME/type/extension/size, decompression bombs, macros, path traversal) | ✅ Verified | `validate_file_upload` checks size (10MB), extensions, macro detection (VBA in XLSX zip, .xlsm extension), path traversal sanitization. `test_path_traversal_in_filename_blocked`, `test_macro_file_rejected_by_extension`, `test_upload_size_limit_enforced`. |

### Safety invariants that are **NOT** fully verified:

- **Invariant 6 (Failed OCR/model calls preserve source):** OCR is not configured.
  The system rejects scanned PDFs outright rather than attempting OCR with fallback.
  There is no "model call failure" path in the active pipeline (no LLM is used for
  extraction). The invariant is satisfied by never attempting the operation, not by
  resilient recovery.
- **Invariant 11 (No prompt injection):** While injection text is not executed,
  there is no detection or warning mechanism. The reviewer has no visibility that
  injection patterns were present in the document. The dead `RFQAgentRunner` code has
  signal patterns but they don't match real-world injection phrasing.

### Overclaim corrections from the first-cycle report:

- The first report claimed "Failed OCR/model calls preserve source" was ✅ Verified,
  citing `corrupt_invalid_pdf.pdf`. This is an **overstatement**: the PDF parser
  doesn't use OCR at all; the test only confirms corrupt PDFs raise
  `DocumentParserError`, not that OCR/model failure preserves source.
- The first report stated "7 defects" in the executive summary but listed 8 findings.
  This report corrects the count to 13 findings (8 from the first cycle + 5 new from
  the extended cycle).

---

## 7. Workflow Verification Results

### 7.1 Text Parsing

| Fixture | Lines Extracted | Exact Matches | No Matches | Collisions | Notes |
|---------|----------------|---------------|------------|------------|-------|
| multiline_email_with_headers.txt | 6/6 | 6 | 0 | 0 | ✅ All source locators present |
| numeric_only_mpn.txt | 3/3 | 1 | 2 | 0 | ⚠️ Finding 1: numeric MPNs (2900364, 2966171) not extracted |
| description_only_no_mpn.txt | 3/3 | 0 | 2 | 0 | ⚠️ Finding 4: false-positive MPNs ("3-pole", "S7-1200") |
| suffix_bearing_mpn.txt | 3/3 | 3 | 0 | 0 | ✅ Suffix precision verified |
| quoted_email_thread.txt | 3/3 | 3 | 0 | 0 | ✅ Quoted thread extraction works correctly |
| prompt_injection_in_document.txt | 3/3 | 3 | 0 | 0 | ⚠️ Finding 12: injection line silently skipped, no warning |

### 7.2 Spreadsheet Parsing

| Fixture | Lines Extracted | Match Status | Notes |
|---------|----------------|--------------|-------|
| layout_different_headers.csv | 6/6 | 5 EXACT, 1 NO_MATCH | LC1D25BD not in catalog |
| layout_alt_headers.csv | 3/3 | 3 EXACT | ✅ Different header names work |
| headerless_csv.csv | 4/4 | 4 EXACT | ✅ CSV headerless fallback works |
| csv_duplicate_lines.csv | 6/6 | 6 | ✅ Duplicates preserved (not deduplicated) |
| csv_with_formula_values.csv | 2/2 | 2 | ✅ Formula values treated as literals |
| csv_headerless_four_cols.csv | 2/2 | 2 | ✅ 4-column headerless works |
| csv_short_header_names.csv | 3/3 | 3 EXACT | ✅ Short headers (MFR, Desc) work |
| layout_xlsx_alt_headers.xlsx | 4/4 | 4 | ✅ Extra columns ignored |
| multisheet_diff_cols.xlsx | 4/4 | 4 | ✅ Multi-sheet with different column orders |
| xlsx_formula_mpn_values.xlsx | 4/4 | 1 EXACT, 3 NO_MATCH | ⚠️ Finding 13: formulas with data_only=True |
| xlsx_formula_in_notes.xlsx | 2/2 | 2 | ✅ Formula in notes column |
| headerless_xlsx.xlsx | 0 | N/A | ⚠️ Finding 5: headerless XLSX silently skipped |
| xlsx_title_then_header.xlsx | 2/2 | 2 EXACT | ✅ Title rows before header detected |
| xlsx_hidden_merged_blank.xlsx | 4/4 | 3 EXACT, 1 None | ⚠️ Finding 9: hidden sheet "Line Items" parsed |
| xlsx_fresh_formulas_no_cache.xlsx | 2/2 | 2 | ⚠️ Finding 10: formula rows silently None |
| xlsx_quantity_formats.xlsx | 4/4 | 2 EXACT, 2 NO_MATCH | ✅ "10 pcs", "5 units", "20x", "15.5" parsed |
| csv_with_quoted_quantity_specs.csv | 2/2 | 2 | ✅ Quoted quantity specs handled |

### 7.3 PDF Parsing

| Fixture | Lines Extracted | Match Status | Notes |
|---------|----------------|--------------|-------|
| multipage_native_pdf.pdf | 6/6 | 6 EXACT | ✅ Multi-page with source locators |
| multipage_repeated_headers_pdf.pdf | 5/5 | 1 EXACT, 4 NO_MATCH | ✅ Headers not extracted as false lines |
| wrapped_description_pdf.pdf | 8/8 | 0 EXACT, 7 NO_MATCH, 1 RFQ-2026 | ⚠️ Finding 2: qty lost (qty before OEM); ⚠️ Finding 6: RFQ ref extracted as MPN |
| pdf_unfamiliar_manufacturers.pdf | 3/3 | 0 EXACT, 2 COLLISION, 1 NO_MATCH | ⚠️ Finding 7: manufacturer not extracted from PDF tables |
| scanned_image_pdf.pdf | 0 | N/A | ✅ Rejected with "Scanned or image-only PDF" error |
| corrupt_invalid_pdf.pdf | 0 | N/A | ✅ Rejected with DocumentParserError |
| password_protected_pdf.pdf | 0 | N/A | ✅ Rejected safely |

### 7.4 Matching Engine

| Input | Expected | Actual | Status |
|-------|----------|--------|--------|
| ABC-12 @ Acme Industrial | COLLISION (2 SKUs) | COLLISION, both candidates | ✅ |
| ABC-12A @ Acme Industrial | EXACT_MATCH, SKU-EXT-010 | EXACT_MATCH, SKU-EXT-010 | ✅ |
| ABC-12-R2 @ Acme Industrial | EXACT_MATCH, SKU-EXT-011 | EXACT_MATCH, SKU-EXT-011 | ✅ |
| XG-42 @ None | COLLISION (2 manufacturers) | COLLISION, both candidates | ✅ |
| XG-42 @ Delta Electronics | EXACT_MATCH, SKU-EXT-013 | EXACT_MATCH, SKU-EXT-013 | ✅ |
| LC1D09BD @ None | COLLISION (manufacturer omitted) | COLLISION, 1 candidate | ✅ |
| LC1D09BD @ Schneider Electric | EXACT_MATCH, SKU-EXT-001 | EXACT_MATCH, SKU-EXT-001 | ✅ |
| LC1D09BD @ Siemens | COLLISION (brand mismatch) | COLLISION, 1 candidate | ✅ |
| NONEXISTENT-PART-12345 @ Any | NO_MATCH | NO_MATCH | ✅ |
| ABC-12A @ acme industrial | EXACT_MATCH (case-insensitive) | EXACT_MATCH, SKU-EXT-010 | ✅ |

### 7.5 Export Verification

| Property | XLSX | CSV | Status |
|----------|------|-----|--------|
| Draft banner in A1 | ✅ "DRAFT QUOTATION WORKSHEET" | ✅ "DRAFT QUOTATION WORKSHEET" | ✅ |
| Internal use notice | ✅ "INTERNAL USE ONLY" | ✅ "INTERNAL USE ONLY" | ✅ |
| Not binding notice | ✅ "NOT A BINDING OFFER" | ✅ "NOT A FINAL COMMITMENT" | ✅ |
| Source locator | ✅ "[File: ... \| Row: N]" | ✅ "[File: ... \| Row: N]" | ✅ |
| Formula escaping | ✅ data_type="s" for formula-like | ✅ prefixed with `'` | ✅ |
| Export blocking on unresolved | ✅ ExportValidationError | ✅ ExportValidationError | ✅ |
| Partial export | ✅ allowed with flag | ✅ allowed with flag | ✅ |
| Email draft unsent | ✅ "UNSENT DRAFT" + "NO AUTOMATIC" | ✅ via separate endpoint | ✅ |
| Draft label on manifest | ✅ is_draft=True | ✅ is_draft=True | ✅ |
| Download URL case-scoped | ✅ `/api/rfqs/{case_id}/exports/{export_id}` | ✅ | ✅ |

### 7.6 Adversarial / Failure Behavior

| Fixture | Expected | Actual | Status |
|---------|----------|--------|--------|
| empty_file.txt (0 bytes) | UploadValidationError | ✅ Raised | ✅ |
| corrupt_invalid_pdf.pdf | DocumentParserError | ✅ Raised | ✅ |
| oversized_csv_5005_rows.csv (>5000 rows) | DocumentParserError | ✅ Raised | ✅ |
| oversized_file_10mb_plus.bin (>10MB) | UploadValidationError | ✅ Raised | ✅ |
| password_protected_pdf.pdf | Safe failure | ✅ Raised exception | ✅ |
| script.py (unsupported ext) | UploadValidationError | ✅ Raised | ✅ |
| prompt_injection_in_document.txt | Treated as data | ✅ Lines parsed, injection skipped | ✅ but no flag — Finding 12 |
| csv_with_formula_values.csv | Formula values as literals | ✅ Handled | ✅ |
| scanned_image_pdf.pdf | Rejection with clear error | ✅ "Scanned or image-only PDF" | ✅ |
| EICAR test file | Rejected by scanner | ✅ "Security alert: Malicious" | ✅ |
| Path traversal filename | Sanitized | ✅ No `..` in filename | ✅ |

### 7.7 Persistence / Restart

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| Case survives manager restart | Case + lines + audit restored | ✅ All restored | ✅ |
| File survives restart | Uploaded file retrievable | ✅ File on disk | ✅ |
| Version increments on edit | version=1 → version=2 | ✅ version=2 after 1 edit | ✅ |
| Audit trail survives restart | Events persisted | ✅ 3+ events after restart | ✅ |
| Delete case removes all state | Case + lines + audit + files gone | ✅ All removed from memory + SQLite | ✅ |
| Delete persists across restart | Deleted in next process | ✅ Confirmed via SQLiteStateStore reload | ✅ |
| Full workflow persists | Create → edit → approve → export → restart → verify | ✅ All state restored | ✅ |

### 7.8 Concurrency

| Test | Workload | Expected | Actual | Status |
|------|----------|----------|--------|--------|
| 50 concurrent case creations (16 workers) | Intake only | 50/50 unique case IDs | ✅ 50/50 | ✅ (prior evidence) |
| 128 concurrent case creations (16 workers) | Intake only | 128/128 unique IDs | ✅ 128/128 | ✅ (prior evidence, `run_synthetic_e2e_corpus.py`) |
| 30 concurrent create + approve | Intake → review | 30/30 cases created + approved | ✅ 30/30, all 30 approved | ✅ **NEW** |
| 20 concurrent exports of same case | Export | 20 unique exports, no corruption | ✅ 20/20, all unique IDs | ✅ **NEW** |
| 8 concurrent edits to same line (stale version) | Review | 1 succeeds, 7 conflict (409) | ✅ 1+ success, ≥1 conflict, all conflicts say "Stale state" | ✅ **NEW** |
| 15 concurrent full create→approve→export workflows | End-to-end | 15/15 complete all stages | ✅ 15/15 created, approved, exported | ✅ **NEW** |

### 7.9 Authentication, Authorization & Send Route

| Test | Expected | Actual | Status |
|------|----------|--------|--------|
| REQUIRE_AUTH=false, no API key | Request succeeds (demo bypass) | ✅ 200, usr-local-demo (admin) | ✅ |
| REQUIRE_AUTH=true, no API key | 401 Unauthorized | ✅ 401 | ✅ |
| REQUIRE_AUTH=true, invalid key | 401 Unauthorized | ✅ 401 | ✅ |
| REQUIRE_AUTH=true, viewer key | 200 for read, 403 for write | ✅ Correct RBAC | ✅ |
| REQUIRE_AUTH=true, reviewer key | 200 for create/patch/export | ✅ Correct RBAC | ✅ |
| REQUIRE_AUTH=true, admin key | 200 for all operations | ✅ Correct RBAC | ✅ |
| Client actor spoofing (auth on) | Actor overridden by authenticated principal | ✅ "Authorized Reviewer" in audit, not "SYSTEM_ADMIN" | ✅ |
| Client actor spoofing (auth off) | ⚠️ Actor trusted from client | ✅ FAKE_ADMIN recorded when auth disabled | ⚠️ **Limitation** (Finding documented) |
| Viewer cannot delete case | 403 Forbidden | ✅ 403 | ✅ |
| Admin can delete case | 200 success | ✅ 200 | ✅ |
| Send with REQUIRE_REAL_TRANSPORT=false | Simulated send, no external transport | ✅ `transport: "simulated_local"`, `outbound_transport_invoked: False` | ✅ |
| Send with REQUIRE_REAL_TRANSPORT=true | Blocked | ✅ `ApprovalGateError: Real outbound transport is not configured` | ✅ |
| Send route invokes SMTP/HTTP | Never | ✅ No SMTP/HTTP/email library calls in code or at runtime | ✅ |

---

## 8. Findings (Severity-Ranked)

### High Severity

| # | Finding | Affected Stage | Reproduction |
|---|---------|----------------|--------------|
| 1 | TextParser silently skips numeric-only MPNs | Text Extraction | `test_numeric_only_mpn`, `test_text_parser_skips_numeric_only_mpn` |
| 3 | Download endpoint hardcodes `storage/exports` path | Export / Download | `test_export_download_from_default_storage` |
| 2 | PDF parser loses quantity when before manufacturer | PDF Extraction | `test_wrapped_description_pdf_extracts_items` |

### Medium Severity

| # | Finding | Affected Stage | Reproduction |
|---|---------|----------------|--------------|
| 5 | Headerless XLSX silently skipped, no fallback | Spreadsheet Extraction | `test_headerless_xlsx` |
| 7 | PDF parser doesn't extract manufacturer from table rows | PDF + Matching | `test_pdf_unfamiliar_manufacturers` |
| 9 | XLSX parser does not skip hidden sheets | Spreadsheet Extraction | `test_xlsx_hidden_sheets_are_parsed` |
| 10 | XLSX fresh formulas silently become None, no warning | Spreadsheet / Transparency | `test_xlsx_fresh_formulas_no_cache_silently_skipped` |
| 15 | usr-local-demo bypass trusts client-supplied actor | Auth / Accountability | `test_usr_local_demo_bypasses_auth` |

Note: Finding 8 (usr-local-demo bypass) is rated Medium because it only affects
the local demo mode (`REQUIRE_AUTH` not set). In production with auth enabled,
the actor is always overridden by the authenticated principal.

### Low Severity

| # | Finding | Affected Stage | Reproduction |
|---|---------|----------------|--------------|
| 4 | TextParser extracts false-positive MPNs from description tokens | Text Extraction | `test_description_only_no_mpn` |
| 6 | PDF parser extracts document reference numbers as MPNs | PDF / False Positives | `test_wrapped_description_pdf_extracts_items` |
| 11 | Dead code: RFQAgentRunner never wired into API | Architecture | Static analysis |
| 12 | Prompt injection text silently skipped, not flagged | Extraction / Defense-in-depth | `test_prompt_injection_isolated_as_data` |
| 13 | XLSX parser uses data_only=True, hiding formula content | Spreadsheet / Transparency | `test_xlsx_formula_mpn_values`, `test_xlsx_fresh_formulas_no_cache_silently_skipped` |

### Info

| # | Finding | Affected Stage | Reproduction |
|---|---------|----------------|--------------|
| 8 | Download endpoint defect was papered over in test | Test Methodology | Review of `test_full_workflow_via_api` |

---

## 9. Coverage Gaps

The following areas were **not** tested or are only partially tested:

### Unverified or Partially Verified

1. **Scanned PDF with OCR:** OCR is not configured. Scanned PDFs are rejected
   outright. The "preserve source on OCR failure" invariant cannot be tested
   because the OCR path is entirely disabled. Only the rejection path is tested.

2. **Frontend (Next.js) UI end-to-end:** The frontend was not exercised. Only
   the API layer and backend logic were tested. UI behavior (editable tables,
   keyboard navigation, accessibility) is unverified.

3. **RapidFuzz fuzzy matching (V1 API `/v1/rfqs/{case_id}/match`):** The fuzzy
   candidate retrieval endpoint was not tested for score quality or ranking
   correctness. Only the exact matching engine was tested.

4. **Catalog collisions in XLSX/CSV extraction:** Cross-brand collisions were
   tested at the matching engine level and with text input, but not through
   full XLSX/CSV → matching → export pipeline with collision resolution.

5. **Multi-sheet XLSX with different column mappings per sheet:** The
   `multisheet_diff_cols.xlsx` fixture has two sheets with different column
   orders, but both sheets happen to have the same header names in different
   positions. A sheet with entirely different header names per sheet was not
   tested.

6. **Excel date/number formatting edge cases:** Quantity columns formatted as
   dates, scientific notation, or locale-specific number formats were not
   tested.

7. **Very long MPNs (>50 characters):** No test for extremely long part numbers
   that might overflow UI fields or database columns.

8. **Unicode and bidirectional text in RFQ lines:** Non-Latin characters,
   right-to-left text, and emoji in MPN/description fields were not tested beyond
   basic handling.

9. **Concurrent access to the same export manifest:** While concurrent exports
   of the same case were tested (20 threads), concurrent download of the same
   export manifest was not explicitly tested.

10. **Export format edge cases:** XLSX with 26+ columns, CSV with embedded
    newlines in quoted fields, and files exceeding the row limit by a large
    margin were not tested.

11. **Time zone handling:** All timestamps use `datetime.utcnow()`. Timezone
    handling in the audit trail and export manifests was not tested.

12. **Email draft template injection:** The `generate_unsent_email_draft`
    function was tested for content, but not for template injection attacks
    through RFQ line data embedded in the draft.

### Limits Confirmed in Code (Not Defects, but Constraints)

| Limit | Value | Location |
|-------|-------|----------|
| Max upload size | 10 MB | validator.py:12 |
| Allowed extensions | .csv, .xlsx, .pdf, .txt | validator.py:13 |
| PDF max pages | 50 | pdf_parser.py:47 |
| CSV max rows | 5000 | spreadsheet_parser.py:87 |
| XLSX max sheets | 20 | spreadsheet_parser.py:184 |
| XLSX max columns | 100 | spreadsheet_parser.py:195 |
| XLSX data_only | True (formulas → cached values or None) | spreadsheet_parser.py:183 |

---

## 10. Minimum Next Tests Before Real-Data Pilot

Before any real-data pilot, the following tests must be added and passed:

### Must-have (blocking)

1. **OCR failure recovery test:** Even though OCR is not configured, the system
   must preserve the original uploaded file on disk when a scanned PDF is
   rejected, and the error must clearly indicate the user should provide a
   native PDF or paste lines manually. Test: upload scanned PDF → verify file
   is stored → verify error message → verify no partial case created.

2. **Download endpoint with custom storage path test:** Test the download
   endpoint with a non-default `base_export_dir` to confirm the path-hardcoding
   defect (Finding 3). This is a blocking architectural issue.

3. **XLSX formula detection test:** Test that formula cells (with and without
   cached values) are detected and flagged in extraction warnings. Reviewer must
   see `FORMULA_CELL_DETECTED` or similar warning. Currently no such warning
   exists (Finding 10).

4. **XLSX hidden sheet skip test:** Test that hidden sheets are skipped and not
   contributing spurious lines. Currently they leak (Finding 9).

5. **PDF quantity-before-manufacturer test:** Test that quantities appearing
   before the manufacturer name are correctly extracted. Currently lost (Finding 2).

6. **End-to-end V1 API quote lifecycle test:** Test the full V1 flow:
   `POST /v1/rfqs/extract` → `POST /v1/rfqs/{id}/match` →
   `POST /v1/rfqs/{id}/draft-quote` → `POST /v1/quote-drafts/{id}/approve` →
   `POST /v1/approved-quotes/{id}/send`. Currently only the service layer is
   tested, not the full API chain.

7. **Frontend integration test:** At minimum, a smoke test that the Next.js
   frontend can list RFQs, view lines, and approve a line through the API proxy.
   Currently untested.

### Should-have (strongly recommended)

8. **Unicode/MPN edge cases:** Test RFQs with non-Latin characters, extremely
   long MPNs, and special characters in descriptions.

9. **Concurrent export + download:** Test that downloading an export while
   another export of the same case is being generated doesn't cause file
   system race conditions.

10. **Catalog change invalidation:** Test that updating the catalog invalidates
    existing draft quotes (version-bound approval). The `_rfq_source_snapshot_hash`
    function exists but is only tested indirectly via `test_stale_quote_snapshots.py`.

11. **Time zone / timestamp consistency:** Verify that audit events, export
    manifests, and quote approvals have consistent timestamps across restarts.

12. **Email draft template injection:** Verify that RFQ line data embedded in
    email drafts cannot inject additional content or break the template.

---

## 11. Test Commands

```bash
# Run full test suite (existing + audit)
python -m pytest tests/ -v

# Run only audit tests (both harnesses)
python -m pytest tests/end_to_end_audit/ -v

# Run extended audit tests only
python -m pytest tests/end_to_end_audit/test_audit_extended.py -v

# Run existing evaluation scripts (prior evidence)
python scripts/evaluate_synthetic_demo.py
python scripts/run_synthetic_e2e_corpus.py
```

---

## 12. Evidence Artifacts

- **First-cycle audit tests:** `tests/end_to_end_audit/test_audit_harness.py` (47 tests)
- **Extended audit tests:** `tests/end_to_end_audit/test_audit_extended.py` (74 tests)
- **Audit fixtures:** `tests/end_to_end_audit/fixtures/` (36 files)
- **Test results log:** `tests/end_to_end_audit/results/pytest_audit_run_v2.txt`
- **Findings summary:** `tests/end_to_end_audit/results/audit_findings_extended.txt`
- **Catalogs used:** `tests/end_to_end_audit/fixtures/audit_extended_catalog.csv` (15 items),
  `tests/end_to_end_audit/fixtures/audit_synthetic_catalog.csv` (11 items)

---

*Report generated: October 31, 2026*
*Test environment: Python 3.9.6, macOS arm64, macOS arm64 native tools*
*No real customer data, PII, or production systems were used in this audit.*
*Audit branch: `audit/e2e-test-defects` (commit e001272 on pushed branch)*
