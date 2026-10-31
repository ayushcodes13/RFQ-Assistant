# problem.md — QA Defect Log for RFQ Assistant

All issues found during end-to-end QA of the current working tree. Each entry lists the
**severity**, **current status**, and the **fix** applied (if any). Removed from this
list once fixed and verified.

---

## Status Legend

- **[OPEN]** — Defect confirmed, not yet fixed.
- **[FIXED]** — Fixed in the working tree and verified by tests.

---

## 1. [FIXED] Password-protected PDF now produces a clear "Password-protected PDF" error

**Severity:** Medium
**Files:** `rfq_assistant/ingestion/parsers/pdf_parser.py` (lines 44–62)

**Description (fixed):** The `PDFParser.parse()` method wrapped only the
`pypdf.PdfReader(io.BytesIO(content))` constructor in a `try/except`, but `pypdf`
does NOT raise on construction for password-protected PDFs — it succeeds silently.
The `FileNotDecryptedError` was raised when `len(reader.pages)` was accessed, which
was OUTSIDE the try/except block. This caused the error to fall through to the
generic `except Exception` handler in `CaseManager.create_case_from_upload()`,
producing a generic `PROCESSING_UNEXPECTED_ERROR` warning instead of a specific,
actionable "Password-protected PDF" message.

**Fix applied:** Added an explicit `try/except` around `len(reader.pages)` that
catches `pypdf.errors.FileNotDecryptedError` and raises a descriptive
`DocumentParserError`, plus a catch-all `except Exception` for any other pypdf
error during page enumeration.

**Verified by:** `test_audit_harness.py::test_password_protected_pdf_rejected` now
asserts that the warning message contains "Password-protected".

---

## 2. [FIXED] Download endpoint now uses `export_generator.base_export_dir` instead of hardcoded path

**Severity:** High
**Files:** `rfq_assistant/api/app.py` (line 436)

**Description (fixed):** The `download_export` endpoint hardcoded
`Path("storage/exports") / export_id`, ignoring the `export_generator.base_export_dir`
configuration. When the generator used a custom base directory (e.g., `tmp_path / "exports"`
in tests), the download endpoint returned 404 because it looked in the wrong location.

**Fix applied:** Changed `Path("storage/exports")` to `Path(export_generator.base_export_dir)`.

**Verified by:** `test_audit_extended.py::test_export_download_from_custom_storage` now
asserts `download_resp.status_code == 200` with a download body > 100 bytes.

---

## 3. [FIXED] TextParser now extracts numeric-only MPNs (e.g., `2900364`)

**Severity:** High
**Files:** `rfq_assistant/ingestion/parsers/text_parser.py` (lines 197–214)

**Description (fixed):** The `_extract_mpn()` static method required at least one
letter AND one digit in the token. Numeric-only MPNs like Phoenix Contact's `2900364`
were silently dropped to `NO_MATCH`.

**Fix applied:** Added a new branch in `_extract_mpn()` that accepts numeric-only
tokens with length >= 5 as valid MPN candidates. Also added voltage/amperage
specification exclusion (`24VDC`, `100-240VAC`, etc.) consistent with the PDF parser.

**Verified by:**
- `test_audit_extended.py::TestTextExtractionExtended::test_text_parser_extracts_numeric_only_mpn`
- `test_audit_harness.py::TestExtractionTextEdgeCases::test_numeric_only_mpn`

---

## 4. [FIXED] PDF parser now extracts quantity appearing before manufacturer/OEM

**Severity:** Medium
**Files:** `rfq_assistant/ingestion/parsers/pdf_parser.py` (lines 256–270)

**Description (fixed):** The quantity regex `r"\b(\d+(?:\.\d+)?)\s*(EA|PCS|UNITS|M|FT|SET)?\b\s*$"`
anchored to the end of the line (`$`). Lines like `10 EA Schneider Electric LC1D09BD`
lost the quantity because the numeric token didn't appear at the end (it appeared
before the manufacturer in tab-delimited table rows).

**Fix applied:** Added a fallback quantity search that looks for `N UNIT` patterns
anywhere in the line (with unit variants `EA|PCS|UNITS?|M|FT|SET|X`) when the
end-of-line pattern doesn't match.

**Verified by:** `test_audit_extended.py::TestPdfLayoutDiversity::test_wrapped_description_pdf_extracts_items`
now asserts `len(lines_without_qty) == 0`.

---

## 5. [FIXED] PDF parser no longer extracts document reference numbers (e.g., `RFQ-2026-001`) as MPNs

**Severity:** Low
**Files:** `rfq_assistant/ingestion/parsers/pdf_parser.py` (line 299)

**Description (fixed):** The MPN token regex matched document reference numbers like
`RFQ-2026-001` which appear in RFQ headers. These were extracted as `requested_mpn`
with no manufacturer context.

**Fix applied:** Added a filter in the MPN token loop that excludes tokens matching
common document reference patterns: `^(?:RFQ|PO|QUO|SO|QUOTE)[\-_]\d`.

**Verified by:** `test_audit_extended.py::test_wrapped_description_pdf_extracts_items`
now asserts `len(rfq_lines) == 0`.

---

## 10. [FIXED] TextParser and PDFParser extract specification tokens (e.g., `3-pole`) as MPNs

**Severity:** Medium
**Files:** `rfq_assistant/ingestion/parsers/text_parser.py` (lines 207–216),
`rfq_assistant/ingestion/parsers/pdf_parser.py` (lines 294–308)

**Description (fixed):** The MPN extraction logic in both `_extract_mpn` (text parser)
and `_parse_pdf_line` (PDF parser) accepted any token containing both a digit and a
letter with length >= 4. Specification tokens like `3-pole` (a 3-pole contactor),
`9A` (9 amp), `5VA` (5 volt-amps), and `24V` (24 volts) were wrongly extracted as
part numbers when no real MPN was present in the text.

**Fix applied:** Added exclusion filters in both parsers for:
- Pole/contact specification tokens: `3-pole`, `SPST`, `SPDT`, `DPST`, `DPDT`, etc.
- Decimal quantity+unit specification tokens: `9A`, `100mA`, `5VA`, `24V`, etc.

**Verified by:** `test_audit_extended.py::test_text_parser_false_positive_mpn_extraction`
now asserts that `3-pole` is NOT extracted as an MPN (MPN is `None` or a valid catalog
part number, never a spec token).

---

## 11. [FIXED] Path traversal defense-in-depth in DocumentStorage.save_file and download_export

**Severity:** Medium
**Files:** `rfq_assistant/ingestion/storage.py` (line 17),
`rfq_assistant/api/app.py` (line 456)

**Description (fixed):** Two potential path traversal vectors:
1. `DocumentStorage.save_file` used the caller-supplied filename directly in the
   path without verifying the resolved path stays within the case directory. While
   `validate_file_upload` sanitizes filenames upstream, defense-in-depth was missing.
2. `download_export` endpoint used the `export_id` from the URL path directly in
   `Path(export_generator.base_export_dir) / export_id` without validating the format,
   allowing potential `..` traversal.

**Fix applied:**
1. Added path resolution check in `DocumentStorage.save_file` that raises `ValueError`
   if the resolved path escapes the case directory.
2. Added `export_id` format validation (`EXP-[A-F0-9]{8}`) in the `download_export`
   endpoint before constructing any filesystem path.

**Verified by:** Full test suite (318 passed).

---

## 12. [FIXED] Legacy XLS conversion test fails when LibreOffice is not installed

**Severity:** Low
**Files:** `tests/test_legacy_xls.py` (line 76)

**Description:** The test `test_parser_converts_and_retains_original_filename_with_review_warning`
monkeypatched `subprocess.run` to mock the LibreOffice converter, but did NOT mock
`shutil.which("libreoffice")`. When LibreOffice is absent from the test environment,
`convert_legacy_xls` raises `LegacyXLSConversionError("Legacy .xls conversion is
unavailable because LibreOffice is not installed.")` before reaching the mocked
`subprocess.run` call.

**Fix applied:** Added `monkeypatch.setattr("rfq_assistant.ingestion.xls_conversion.shutil.which",
lambda _: "/usr/bin/libreoffice")` to the test so it proceeds to the mocked subprocess.

**Verified by:** `tests/test_legacy_xls.py::test_parser_converts_and_retains_original_filename_with_review_warning`
now passes.

---

## 6. [FIXED] Local-demo audit attribution ignores client-supplied actor names

**Severity:** Medium
**Files:** `rfq_assistant/auth.py` (lines 99–103), `rfq_assistant/api/app.py` (line 165)

**Fix applied:** Upload, line edits, exports, and quote approval/rejection/send always
use the server-side `PilotUser.name`, including the explicit local demo principal.
Caller-supplied actor fields can no longer spoof audit records.

**Verified by:** `test_audit_extended.py::TestAuthAndSecurityExtended::test_local_demo_actor_is_server_supplied`.

---

## 7. [DOCUMENTED] Quote send route uses simulated local transport (never external)

**Severity:** Info
**Files:** `rfq_assistant/agents/tools.py` (lines 140–159)

**Description:** The `send_approved_quote` method always returns
`{"transport": "simulated_local", "is_simulated": true, "outbound_transport_invoked": false}`.
The `REQUIRE_REAL_TRANSPORT` env var blocks sends when set to `true`, but is not set
by default. This is an intentional safety design (no automatic outbound), but it means
the send route never actually transmits.

**Verified by:** `test_audit_extended.py::test_send_quota_route_never_invokes_external_transport`
asserts `result["transport"] == "simulated_local"` and `result["outbound_transport_invoked"] is False`.
`test_send_with_require_real_transport_blocks` confirms sends are blocked when
`REQUIRE_REAL_TRANSPORT=true`.

**Resolution:** No fix needed — this is an intentional safety invariant per AGENTS.md
("No automatic outbound customer quotation, follow-up or purchase order submission").
Documented clearly in the API schema and the `transport_notes` field.

---

## 8. [FIXED] Test flakiness: `test_password_protected_pdf_rejected` no longer fails intermittently

**Severity:** Low
**Files:** `tests/end_to_end_audit/test_audit_harness.py`

**Description (fixed):** When running the full test suite,
`test_password_protected_pdf_rejected` occasionally failed with a
`FileNotDecryptedError` traceback from pypdf. This was caused by the same root
cause as issue #1 — the password-protected PDF error was not caught by the PDF
parser and fell through to the generic handler.

**Fix applied:** Resolved by the fix for issue #1 (explicit `FileNotDecryptedError`
handling). The test assertion was also strengthened to verify the warning message
contains "Password-protected".

---

## 9. [FIXED] CORS misconfiguration: `allow_origins=["*"]` with `allow_credentials=True`

**Severity:** Medium
**Files:** `rfq_assistant/api/app.py` (lines 129–135)

**Description:** The CORS middleware was configured with `allow_origins=["*"]` while
also setting `allow_credentials=True`. Per the CORS specification, wildcard origins
are not allowed when credentials are involved — browsers reject the preflight response.
In production, this would either allow any origin (security risk) or cause all
credentialed requests to fail (browser bug).

**Fix applied:** Replaced `allow_origins=["*"]` with an explicit list of local
development origins (`http://localhost:3000`, etc.). In production deployments,
`RFQ_ASSISTANT_CORS_ORIGINS` should be set via environment variable (future enhancement).

**Verified by:** Full test suite (318 passed). The latest PR CI production build passed and prerendered 5/5 pages.

---

The following issues have been fixed and verified in the current working tree:

### F-1. [FIXED] Scanned/image-only PDF now retained as a failed case instead of crashing
- **Was:** `DocumentParserError` was raised, causing a 500 error or test failure.
- **Now:** The case is created with status `FAILED`, the original upload is retained,
  and a clear `DOCUMENT_EXTRACTION_FAILED` warning is recorded.
- **Verified by:** `test_audit_extended.py::test_scanned_pdf_retained_as_failed_case_without_crash`

### F-2. [FIXED] Oversized CSV (>5000 rows) now retained as a failed case instead of crashing
- **Was:** `DocumentParserError` was raised before the case was created, losing the upload.
- **Now:** The row limit is checked during streaming row iteration (not upfront), so the
  upload is retained and a failed case with `DOCUMENT_EXTRACTION_FAILED` is created.
- **Verified by:** `test_audit_extended.py::test_oversized_csv_retained_as_failed_case`
  and `test_ingestion_security_adversarial.py::test_spreadsheet_row_limit_enforced`

### F-3. [FIXED] Corrupt PDF now retained as a failed case instead of raising
- **Was:** `DocumentParserError` was raised, propagating as a 500 error.
- **Now:** The case is created with status `FAILED` and a clear error message.
- **Verified by:** `test_adversarial_and_e2e.py::test_scenario_6_unsafe_files_rejected_safely`

### F-4. [FIXED] Headerless XLSX now preserves rows with guessed column layout and review warnings
- **Was:** Headerless XLSX sheets were silently skipped, producing a
  `DocumentParserError("No RFQ line items could be extracted")`.
- **Now:** Column roles are inferred from content, rows are preserved, and
  `HEADERLESS_LAYOUT_REVIEW` warnings are emitted per line.
- **Verified by:** `test_audit_harness.py::test_headerless_xlsx`

### F-5. [FIXED] Headerless CSV now retains the first data row instead of discarding it as a header
- **Was:** The first data row could be skipped if it didn't match header patterns.
- **Now:** Streaming header detection with `HEADERLESS_CSV_LAYOUT_GUESSED` warning.
- **Verified by:** `test_intake_completeness.py::test_headerless_csv_retains_first_row_and_original_row_numbers`

### F-6. [FIXED] XLSX fresh formulas (no cached values) are preserved as formula text with warnings
- **Was:** `data_only=True` caused formula cells to return `None` silently.
- **Now:** `data_only=False` preserves formula text, and `FORMULA_VALUE_NOT_EVALUATED`
  warnings are emitted. Formula-backed quantity cells are set to `None` with
  `MISSING_QUANTITY` warning.
- **Verified by:** `test_ingestion_and_parsers.py::test_xlsx_formula_quantity_is_preserved_but_not_calculated`
  and `test_audit_extended.py::test_xlsx_fresh_formulas_no_cache_are_visible_for_review`

### F-7. [FIXED] XLSX hidden sheets are surfaced for review (not silently dropped or extracted without warning)
- **Was:** Hidden sheet data was extracted without any warning to the reviewer.
- **Now:** Hidden sheets are included in inspection with `HIDDEN_SHEET_INCLUDED`
  document-level warning and `HIDDEN_SHEET_REVIEW` per-line warning.
- **Verified by:** `test_audit_extended.py::test_xlsx_hidden_sheets_are_parsed`

### F-8. [FIXED] PDF "24VDC" voltage spec tokens are not extracted as MPNs
- **Was:** Voltage specifications like `24VDC` could be extracted as MPN candidates.
- **Now:** The regex `re.fullmatch(r"\d+(?:V(?:AC|DC)?|A|HZ|W|KW)", candidate, re.IGNORECASE)`
  excludes voltage/amperage specification tokens.
- **Verified by:** `tests/test_ingestion_and_parsers.py:159-160`
  (asserts `phoenix_line.requested_mpn == "2900364"`, not `"24VDC"`)

### F-9. [FIXED] Grounded LLM extraction adapter and offline tests pass
- **Was:** Committed `main` does not have `llm_extractor` parameter on `CaseManager.__init__`.
  `test_grounded_llm_extraction.py` fails with `TypeError`.
- **Now:** `CaseManager.__init__` accepts `llm_extractor` parameter. The
  `GroundedLLMExtractor` adapter validates JSON schema, evidence grounding, and
  quantity evidence. LLM fallback is disabled by default (`RFQ_LLM_ENABLED=false`).
  All 8 LLM extraction tests pass.
- **Verified by:** `tests/test_grounded_llm_extraction.py` (8 tests)

### F-10. [FIXED] `document_warnings` field added to RFQCase schema and surfaced in API/frontend
- **Was:** Parse warnings were only in the `ParsedDocumentResult`, not persisted on the case.
- **Now:** `document_warnings: List[ExtractionWarning]` field added to `RFQCase`.
  API responses include warnings; frontend displays them in the workbench.
- **Verified by:** OpenAPI contract check, E2E corpus, frontend build.

### F-11. [FIXED] Legacy XLS conversion test fails when LibreOffice is not installed
- **Was:** `test_legacy_xls_upload_runs_through_case_matching_and_keeps_original` monkeypatched
  `subprocess.run` but not `shutil.which("libreoffice")`. In environments without LibreOffice,
  `convert_legacy_xls` raises before reaching the mocked subprocess.
- **Now:** Both tests that rely on a mocked converter also monkeypatch
  `shutil.which` to return a fake path, allowing the conversion to proceed with the
  mocked subprocess.
- **Verified by:** `tests/test_legacy_xls.py` (7 tests pass)

---

## Test Suite Status

| Metric | Working Tree |
|---|---|
| Total tests | 318 passed |
| Warnings | 6 (all deprecation, non-blocking) |
| E2E corpus | 30/30 full flows (8 CSV, 7 PDF, 8 text, 7 XLSX) |
| Concurrent burst | 128/128 unique case IDs (latest measured run: 0.50 s) |
| Synthetic demo scorecard | 20/20 lines, 80/80 field checks, 20/20 match checks |
| OpenAPI contract | Up to date |
| Browser E2E | 7/7 passed on isolated synthetic services |
| Frontend production build | 5/5 pages prerendered |
