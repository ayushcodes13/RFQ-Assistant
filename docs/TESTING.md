# Test strategy: trustworthy over flashy

This document defines the test plan and records the local synthetic verification run below. No customer performance, accuracy, time-savings, or ROI claims are established.

The current 10-shape human-input matrix passed locally on 2026-11-01: `pytest -q tests/test_human_input_matrix.py` → **11 passed**. It covers six conversational inputs plus title-row XLSX, headerless CSV, wrapped native PDF, and scanned PDF with OCR disabled. The combined case-intake test checks original-file retention and requires extracted lines, surfaced warnings, or an explicit failure. It is synthetic and does not exercise a live Luna deployment or a full browser quote-to-export flow for every case.

The new second-stage quote evidence mapper passed with synthetic clients: `pytest -q tests/test_quote_proposal.py tests/test_stale_quote_snapshots.py tests/test_oss_stack_and_ai_pipeline.py` → **23 passed**. It exercises the endpoint call, exact catalog retrieval, citation mapping, deterministic price/Decimal total, and rejection of non-verbatim buyer evidence. It is not a live provider run.

Multipart ingress has a separate ASGI-level test matrix: reject an oversized declared `Content-Length` without reading the body; reject chunked input once the actual byte count exceeds the cap; permit the exact limit; and leave non-multipart bodies to their route handlers. This verifies the cap runs before Starlette's multipart form parser; deployment proxies still need their own request-size limit.

The protected workspace browser flow also asserts that state-changing proxy requests with a foreign or missing `Origin` are rejected, while a same-origin authenticated request reaches the backend role check and authorized admin write.

The browser suite checks baseline headers on the landing response: MIME sniffing is disabled, framing is denied, referrer data is restricted, DNS prefetch is off, and camera/microphone/geolocation are disabled. HSTS remains a TLS-edge responsibility.

Storage path hardening includes adversarial traversal/symlink checks and an upgrade check that migrates pre-hash local case/file paths into the opaque hashed layout while preserving existing source bytes and logical metadata. This is a local storage compatibility test; it does not test a production migration across multiple application hosts.

## Golden fixture pack

Maintain a synthetic annotated corpus covering:
- Clean 20-line XLSX and multiple-sheet workbook.
- Email with 2 lines, missing manufacturer, and natural-language quantity.
- PDF with repeated table headers, page breaks and footnotes.
- Rotated/scanned PDF with uncertain OCR.
- Same MPN used by two distinct manufacturers.
- Near-identical MPN suffixes: ABC-12, ABC-12A, ABC-12-R2.
- Duplicate item requests split across multiple lines/units.
- Contradictory email vs attached spreadsheet quantities.
- Part described as "equivalent" without engineering documentation.
- Blank quantities, zero/negative quantities and unit ambiguity.
- Headerless CSVs: first record must remain a line item, never mistaken for a header.
- Empty/header-only RFQs and document-level fatal parse errors: block case creation and clean up partially saved files.
- Whitespace-only and header-only pasted text, plus header-only CSV/XLSX files: reject before creating a case or storing source bytes, on both synchronous and queued text intake. Pasted text above 500 non-empty regions is rejected before persistence; file parsers keep their format-specific limits and failure behavior.
- Nonempty quantity with missing MPN and description: preserve as an unresolved review row instead of silently dropping it.
- Catalog duplicate IDs, unknown SKU, stale price, malformed CSV.
- Catalog imports are atomic: any malformed row, duplicate SKU inside an upload, missing OEM/MPN or invalid/nonfinite price or stock quantity rejects the entire import without changing existing catalog matching.
- Malicious spreadsheet formula or macros, prompt-injection PDF content, corrupt/password-protected files.
- Formula-like user/customer/catalog fields in generated CSV and XLSX (including leading whitespace, plus, minus and at-sign); exported text must not execute spreadsheet formulas.
- Zero-line exports must fail even in partial-draft mode.

## Key invariants

1. Every exported row has a corresponding source locator or explicit user-entered origin.
2. System never fabricates a catalog SKU/price/stock/lead time.
3. Cross-manufacturer IDs never auto-approve because of a matching part number alone.
4. Changes made by a human persist through reprocessing.
5. Unresolved required attributes, nonpositive/nonfinite quantities, unknown selected SKUs, recorded stock shortfalls and high-severity extraction contradictions block a full validated export, **even if the line is marked approved**. Stock-shortfall lines cannot be approved until the catalog quantity is corrected. Such rows may appear only in prominently labeled partial drafts.
6. Broken files or model errors cannot produce a silent "all clear".
7. No outbound email or order submission exists in v0.
   Unsent customer clarification drafts must never describe an unresolved collision or critical source contradiction as verified, or ask customers to resolve a line that only awaits internal review.
8. No sensitive data appears in test fixtures, telemetry or CI logs.

## Metrics (to measure, not promises)

- **Line recall:** detected true RFQ line items / human-annotated true lines.
- **Critical field exactness:** exact agreement on MPN, manufacturer, quantity and unit for annotated comparable fields.
- **Unflagged critical error count:** wrong quantity/MPN/brand exported as approved without reviewer warning.
- **Source coverage:** proportion of generated rows with valid original page/sheet/row link.
- **Match precision:** correct exact catalog row among candidates / proposals with a selected catalog row.
- **Manual correction burden:** number and duration of corrections per RFQ.
- **Workflow time:** elapsed human work from opening original RFQ to export-ready reviewed draft (manual vs assisted on comparable documents).
- **Abstention quality:** whether ambiguous/unknown rows were actually flagged.

Reported results require fixture count, sample distribution, annotation method, pass criteria and known limitations. Separate synthetic fixture scores from real-client metrics.

## Test layers

**Unit:** parsers, quantity and units, MPN normalization, catalog collisions, export validators, schema constraints.

**Integration:** upload -> parse -> catalog lookup -> human review -> export; ingest failures/retries, permission checks, idempotency and version changes.

Catalog replacement coverage verifies that the CSV is validated before commit, the active item master changes atomically, older line candidates remain available as evidence, stale rows block validated export (including after manager restart), and explicit rematching updates the snapshot version while returning the row to pending human review. The browser suite exercises catalog upload, the visible stale-match warning, rematch, and approval revocation with synthetic data.

The local persistence integration check reconstructs the catalog and case
manager over the same SQLite file and verifies that case fields, corrected line
values, version numbers, audit events, catalog rows, and source files remain
available after the original manager objects are discarded.

**UI:** keyboard-only editing, source navigation, warning notices, export confirmation, empty/loading/error states and prevention of accidental approval.
The export dialog must announce itself as modal, contain keyboard focus while open, close on Escape, and return focus to its opener. Line-edit API requests must include the version shown to the reviewer; missing versions are rejected and stale versions return 409.

**Contract:** `frontend/openapi.json` is checked in and verified against the live FastAPI app by `tests/test_openapi_contract.py`. Frontend wire types are generated from that schema with `npm run gen:types`; `npm run check:types` fails CI if the generated file is stale.

**Browser E2E:** the Playwright suite uses isolated FastAPI and Next.js processes with temporary storage. It covers synthetic intake, review/sample approval, draft export and safety boundaries; these paths prove UI/backend behavior only and are not accuracy benchmarks.

**Coverage and generated cases:** CI publishes pytest-cov XML/JSON artifacts and enforces an 80% project line-coverage floor plus 95% floors for quotation validation, matching, exports, and SQLite persistence. Hypothesis checks normalization idempotence, quantity/unit preservation, decimal conversion, and spreadsheet-formula escaping. Lease and retry timing tests use frozen time. The backend lint gate currently checks Ruff syntax/import-error classes and formats files touched by the coverage work; repository-wide Ruff modernization remains a separate cleanup because the existing baseline contains legacy lint and formatting violations.

**Supply-chain checks:** CI reports pip-audit findings (informational until the existing vulnerable dependency baseline is upgraded), runs Bandit, blocks on npm audit findings at high severity and above, and runs CodeQL for Python and TypeScript/JavaScript plus Gitleaks. Lower-severity npm advisories remain visible in audit output and should be triaged separately.

Mutation testing and dedicated frontend component/accessibility tests are not yet CI gates. Add them after establishing a stable mutation target list and extracting the review/export decisions into testable UI units; the current Playwright suite remains the browser-level check.

## Local synthetic verification — 2026-10-31

Run the reproducible API corpus from the repository root with:

```bash
.venv/bin/python -m scripts.run_synthetic_e2e_corpus
```

The runner creates isolated temporary SQLite, upload, and export state, then exercises 30 synthetic documents through intake, extraction, source retrieval, exact catalog validation, review, CSV/XLSX export, download, and audit verification. The corpus contains 8 pasted-text RFQs, 8 CSVs, 7 distinct generated XLSX files across seven layouts (including alternate headers, reordered columns, preambles, and a multi-sheet workbook), and 7 distinct generated native PDFs spanning four row formats, portrait/landscape pages, and page breaks. The runner fails if PDF/XLSX source hashes are not all distinct, a configured layout is missing, or the extracted line set/manufacturer/MPN/quantity/unit differs from its generated ground truth. In the latest local run on the merged branch, all 30 full flows passed with **180/180 critical-field checks** in 1.11 seconds (median 15.2 ms per document; maximum 93.0 ms). It then issued 128 concurrent synthetic case-creation requests using 16 workers; all 128 succeeded with unique case IDs in 0.58 seconds. A separate five-run comparison on a generated 3,000-row workbook showed a 31.3% lower median parser time after avoiding the cached workbook open, with every extracted line matching the previous parser output. These results are local synthetic engineering evidence only, not a representative customer accuracy or production capacity benchmark; details are in `docs/EXTRACTION_AND_PERFORMANCE_AUDIT.md`. Scanned-page/OCR behavior is checked separately in parser tests and is not represented by these native-PDF timings. Separate legacy XLS tests cover conversion controls and upload-to-match flow, with an additional real LibreOffice round-trip on synthetic data. The concurrency phase stresses intake only, not simultaneous review/export or multi-user authorization.

The combined advanced-ingestion, current-main, and demo-preflight branch was reverified locally on 2026-10-31: the full Python suite passed (**418 tests**, 7 deprecation warnings); frontend ESLint, TypeScript checking, and production build passed; isolated Playwright browser E2E passed (**9/9**), including export-dialog keyboard behavior, workbook cell navigation, and PDF page preview. The latest synthetic corpus run passed **30/30 flows and 180/180 critical-field checks**; 128/128 concurrent creates had unique case IDs. These are synthetic local results, not customer accuracy or production capacity guarantees.

The asynchronous processing-progress change adds persisted API stages (`QUEUED`, `VALIDATING`, `EXTRACTING`, `CHECKING_FIELDS`, `MATCHING`, `READY_FOR_REVIEW`, and `FAILED`) and a browser assertion that queued uploads advance to completed review. Its manual Aside Browser walkthrough used synthetic pasted text and confirmed the queued stage was followed by the actual review state and source-coverage exception; the screenshot is [async processing and review](screenshots/async-processing-review.png). Browser evidence is a local synthetic workflow check, not a customer document test. The focused regression suite additionally checks stage persistence, a stage transition during blocked parsing, repeated enqueue idempotency, and provider pacing after a concurrency wait.

Coverage receipts label CSV/XLSX as `structured_rows` and PDF/email/text as `heuristic_regions`. The workbench states that structured row accounting is deterministic but does not prove each row is a request, and that unstructured region counts are heuristic rather than a completeness guarantee. Schema, parser accumulator, and browser checks cover these distinctions.

Verification for the coverage-basis change on 2026-10-31: **437 Python tests passed**; coverage was **88.75% overall**, with quotation validation 100%, matching 99.58%, exports 96.57%, and persistence 98.86% (all floors passed). Frontend lint, TypeScript, and production build passed; isolated Playwright E2E passed **11/11**, including the displayed heuristic-coverage warning. `git diff --check` passed. This is local synthetic evidence only.

Per-field provenance is serialized with line snapshots and covered across a manager restart. The persistence test verifies source locators and catalog item version, then checks that a human quantity correction retains the original raw value, changes the origin to `HUMAN`, increments the field revision, and survives reload. Grounded Luna adapter tests verify Luna-origin fields remain explicitly tagged as proposals. A manual Side Browser check uploaded a synthetic CSV, opened the extracted line detail, and visually confirmed deterministic field origins, source values, source sheet/row, evidence, validation state, and pending review status in [the workbench screenshot](screenshots/field-provenance-review.jpg). This visual check is limited to one synthetic CSV row; it is not a general extraction-quality result.

Catalog snapshot/rematch coverage verifies atomic full-catalog replacement, a bounded 10 MiB catalog upload, preserved old match evidence, restart recovery, export blocking, and approval revocation after an explicit rematch. The isolated Playwright suite passed **10/10** on synthetic data, including the catalog replacement workflow; the manual Side Browser check visually confirmed the stale-match warning and pending status after rematching in [the catalog rematch screenshot](screenshots/catalog-rematch-warning.jpg). This is local synthetic workflow evidence and does not establish customer extraction accuracy or production concurrency.

Latest catalog snapshot/rematch verification on 2026-10-31: **433 Python tests passed** (7 dependency deprecation warnings); selected Ruff checks passed; frontend ESLint, generated OpenAPI type check, and production build passed; isolated Playwright browser E2E passed **10/10**. The synthetic API corpus passed **30/30 flows and 180/180 critical-field checks**, and 128/128 concurrent intake requests returned unique case IDs. These results are local synthetic evidence only, not customer accuracy, production capacity, or pilot-readiness claims.

Additional source-reconciliation regression coverage: mixed native/scanned PDF verifies native text on page 1 is retained and only page 2 is sent to OCR. Repeated exact part numbers with conflicting quantities across source regions are retained as separate lines, receive blocking warnings, and produce a specific unsent clarification prompt. A reviewer quantity correction is audited and clears the conflict warning once the source values agree. This synthetic text-region test does not exercise separate email and spreadsheet uploads in one case; the current intake contract accepts one document or pasted text per case.

Final local verification on the source-conflict regression branch: **435 Python tests passed**; pytest-cov reported **88.74% overall**, with quotation validation 100%, matching 99.58%, exports 96.57%, and persistence 98.86%; all configured floors passed. CI-selected Ruff checks and required format checks passed. Frontend lint, TypeScript check, and production build passed. Isolated Playwright browser E2E passed **11/11**, including visible quantity-conflict warning and blocked validated export. The synthetic API corpus passed **30/30 flows and 180/180 critical-field checks**, with **128/128** unique concurrent case IDs. Aside Browser manually confirmed the conflict warning in line detail and `NEEDS_REVIEW` export status. All findings use synthetic fixtures; separate multi-file email-plus-attachment intake remains unsupported, and no real distributor accuracy or production-capacity claim is established.

Latest verification of `codex/local-processing-progress` on 2026-10-31: **427 Python tests passed** (7 dependency deprecation warnings); frontend ESLint and `npx tsc --noEmit` passed; `npm run build` passed; isolated Playwright E2E passed **9/9**. The synthetic corpus passed **30/30 full flows**, **180/180 critical-field checks**, and **128/128 concurrent case creations with unique IDs** (16 workers). `git diff --check` passed. This run validates local synthetic behavior only; it does not establish general extraction accuracy, production capacity, or pilot readiness.

**Security:** dangerous uploads, oversized sheets, path traversal, prompt injection, tenant isolation, retention/deletion and leaked logs.

Advanced extraction verification originally recorded **412 Python tests passed**, with 88.63% overall line coverage; local OCR 96.88%, PDF parsing 84.72%, spreadsheet parsing 90%, quotation validation 100%, matching 99.51%, exports 96.52%, and persistence 98.86%. A typed StateStore contract test verifies SQLite implements the service-facing persistence interface. Targeted mypy checks pass for the Luna adapter, PDF parser, and spreadsheet parser; repository-wide mypy remains informational while unrelated issues are addressed. Redis integration tests against a real local server verify that independent Luna gates share request pacing, share 429 cooldowns, and fall back to local pacing when Redis fails. The isolated Playwright suite passed **9/9**, including XLSX row/cell navigation and PDF page viewing. Excel checks cover stored formula-cache visibility without accepting formulas as quantity, zero-padded numeric MPNs, Excel's 15-digit numeric precision limit, hidden row/column counts with warnings on affected rows, vertical merged-cell inheritance with explicit anchor-cell provenance, and source cell references for parsed fields. A new workbook-open count test verifies formula-free XLSX files load once and formula-bearing workbooks still load the formula and cached-value views. A bounded read-only XLSX source preview highlights the recorded row and cells; formulas remain unevaluated. A bounded PDF page render lets reviewers compare OCR text with the page and overlays its normalized source rectangle. Multi-page OCR tests verify that selected pages share one open PyMuPDF document for rendering while Tesseract stays capped at two concurrent page images; rotated synthetic scans verify source orientation and OCR line geometry, while an OCR-misread MPN remains unmatched and flagged for review. Synthetic local OCR tests cover engine absence/errors, render/page/image bounds, malformed TSV rows, confidence parsing, output caps, and normalized line boxes. Source coverage fails closed on duplicate or unknown receipt dispositions and reconciles parsed lines and review candidates to the manifest. Luna transport tests cover transient 5xx/429/timeout retry and prompt failure for permanent errors or over-budget retry delays. Provider-gate tests cover request pacing, concurrency caps, circuit opening, recovery probes, and rejection without real sleep. Deterministic worker tests verify ready-queue wait is measured and persisted per attempt. A review-sampling test verifies that source strata beyond the five sample slots remain individual-review exceptions. Ruff's selected syntax/import checks pass. Hosted CI passed on PR #39's head before this main integration, including Python 3.10/3.11/3.12, frontend lint/build/typecheck, full-stack E2E, dependency/security scans, CodeQL, and Gitleaks. CI will rerun on the integration commit.

**Live model path:** `scripts/smoke_live_luna_e2e.py` sends one clearly synthetic line to the configured GPT-6 Luna endpoint, then verifies exact catalog matching, the clean-row human sample, explicit human approval, and draft-only export. It requires `RFQ_LLM_ENABLED=true`, `RFQ_LLM_MODEL=gpt-6-luna`, `RFQ_LLM_API_KEY`, and `RFQ_LLM_BASE_URL` in the process environment. Run with `uv run --extra test python -m scripts.smoke_live_luna_e2e`. It prints only counts/status, retains no source or result outside a temporary directory, and is intentionally excluded from CI because it uses a live provider and may incur cost. If Luna's second-pass validator flags uncertainty or the sample policy assigns an exception, the script exits nonzero and does not approve or export.

Live Luna smoke executed on 2026-10-31 using the explicitly configured GPT-6 Luna deployment and one synthetic ambiguous-manufacturer line: **passed**, with 2 extraction-stage calls, 1 selective validation call, exact catalog match, explicit sample review approval, and draft-only export. Token counts were returned. The credential was loaded from the user's local project environment only for this process; it was not printed, committed, or copied into repository files. The smoke fixture is regression-tested to require Luna fallback, and the live command now fails if extraction or selective validation is skipped. The post-change backend suite passed **436 tests** (7 dependency deprecation warnings); the focused smoke-contract test, edited-file Ruff checks, and `git diff --check` also passed.

**Pilot:** operator-led blind review of historical RFQs with manual baseline and measured corrections. Maintain a holdout set not used for tuning.

## Release blocker examples

- Missing or modified quantity with no warning.
- Unapproved alternative presented as an exact matching part.
- Displayed source snippet does not correspond to underlying file.
- A corrupted file causes a successful zero-line quote without error.
- Export bypasses review state.
- Private RFQ appears in another workspace or public file.

## Evidence required in each PR

Record commands actually executed, test count/results, failed cases, screenshots for UX and remaining risks. "Not run" is acceptable when honest; invented passes are not.

## Catalog and workbench additions (2026-11-01)

Focused verification for catalog edit proposals, export document listing, and stock-shortfall blocking: `.venv/bin/pytest -q tests/test_export_blockers_adversarial.py tests/test_exports.py tests/test_catalog_update_proposals.py` → **21 passed** (7 dependency deprecation warnings). `cd frontend && npm run lint` and `RFQ_E2E_NEXT_DIST_DIR=.next-qa-ui npm run build` passed. Aside Browser visually confirmed catalog Edit/Ask AI controls, the restored Keyboard shortcuts dialog, case IDs in the inbox, original and generated documents in the workbench, and a synthetic request for 200 units against catalog stock of 150 showing the blocker and increasing the review count. The synthetic case was deleted after the check. Screenshots: [mobile catalog actions](screenshots/catalog-mobile-edit.png), [workbench documents](screenshots/workbench-documents.png). This is local UI evidence; no live Luna call was made.

## Per-user single-workspace authentication (2026-11-01)

The protected web workspace now validates each operator's own backend API key, stores it in an encrypted eight-hour HTTP-only cookie, and forwards that user's key through the server proxy. The backend returns the authenticated user's ID, display name, and role without returning the credential. The isolated Playwright auth flow checks invalid credentials, user identity, cookie flags and tamper rejection, viewer write denial, logout, and admin write access. Local verification on the feature branch: focused auth/OpenAPI checks **29 passed**; full Python suite **511 passed** at **89.18% coverage**; frontend generated-type check, ESLint, TypeScript, and production build passed; protected Playwright auth flow **1/1 passed**; `git diff --check` passed. These tests use synthetic keys and RFQ text. This remains a single-workspace deployment: organization ownership and tenant-scoped database, catalog, files, exports, and jobs are not implemented, so multiple customer organizations must not share one deployment.

**Multi-source intake:** `pytest -q tests/test_multi_source_ingestion.py tests/test_original_source_access.py tests/test_storage_path_safety.py` covers mixed pasted email and attachments, duplicate sources, same-part quantity/manufacturer/revision conflicts, possible differing-MPN conflicts, partial extraction failure, attachment retry without losing successful rows, durable asynchronous processing, limits, source-specific downloads, and storage traversal/symlink escapes on read/write/delete. Playwright's `combine pasted customer email with two source attachments` flow checks the operator form, consolidated case, per-source document list, and stratified sample representation. All fixtures are synthetic; antivirus, real scanned attachment processing, and live Luna are not claimed by these checks.

Local verification on the multi-source implementation branch (2026-11-01): Python 3.12 full suite **529 passed** at **88.74%** coverage; the 80% overall floor and 95% floors for quotation validation, matching, exports and persistence passed. Playwright **16 passed**; frontend ESLint, TypeScript, and production build passed; `git diff --check` passed. Pytest reported existing dependency/Pydantic deprecation warnings; no failures. No live Luna call or antivirus engine scan was part of this run.

Workspace identity binding extends the protected credential format to `key:role:user_id:workspace_id:display_name`, returns the authenticated workspace ID to the Next.js session handler, and rejects a configured key set that names more than one workspace. Older formats map to `ws-default`. This guard prevents an operator from accidentally enabling shared mode before persistence and every resource path are scoped; it does not itself provide tenant isolation. Because the encrypted session payload now requires workspace identity, deployment invalidates older session cookies and users must sign in again. Local verification on the implementation branch: full Python suite **514 passed**, **89.19% overall coverage**, all configured coverage floors passed; frontend ESLint, generated API type check, TypeScript and production build passed; protected workspace-auth Playwright test **1/1 passed** with synthetic keys bound to `ws-browser-test`; selected Ruff syntax/import checks and `git diff --check` passed. The auth persistence, route-level ownership, and cross-workspace object tests remain future gates.
