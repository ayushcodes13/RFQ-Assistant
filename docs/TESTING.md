# Test strategy: trustworthy over flashy

This document defines the test plan and records the local synthetic verification run below. No customer performance, accuracy, time-savings, or ROI claims are established.

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
5. Unresolved required attributes, nonpositive/nonfinite quantities, unknown selected SKUs and high-severity extraction contradictions block a full validated export, **even if the line is marked approved**. Such rows may appear only in prominently labeled partial drafts.
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

The local persistence integration check reconstructs the catalog and case
manager over the same SQLite file and verifies that case fields, corrected line
values, version numbers, audit events, catalog rows, and source files remain
available after the original manager objects are discarded.

**UI:** keyboard-only editing, source navigation, warning notices, export confirmation, empty/loading/error states and prevention of accidental approval.

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

The runner creates isolated temporary SQLite, upload, and export state, then exercises 30 synthetic documents through intake, extraction, source retrieval, exact catalog validation, review, CSV/XLSX export, download, and audit verification. The corpus contains 8 pasted-text RFQs, 8 CSVs, 7 distinct generated XLSX files across seven layouts (including alternate headers, reordered columns, preambles, and a multi-sheet workbook), and 7 distinct generated native PDFs spanning four row formats, portrait/landscape pages, and page breaks. The runner fails if PDF/XLSX source hashes are not all distinct, a configured layout is missing, or the extracted line set/manufacturer/MPN/quantity/unit differs from its generated ground truth. In the latest run, all 30 full flows passed, with **180/180 critical-field checks**, in 0.86 seconds (median 13.8 ms per document; maximum 37.0 ms). It then issued 128 concurrent synthetic case-creation requests using 16 workers; all 128 succeeded with unique case IDs in 0.42 seconds. A separate five-run comparison on a generated 3,000-row workbook showed a 31.3% lower median parser time after avoiding the cached workbook open, with every extracted line matching the previous parser output. These results are local synthetic engineering evidence only, not a representative customer accuracy or production capacity benchmark; details are in `docs/EXTRACTION_AND_PERFORMANCE_AUDIT.md`. Scanned-page/OCR behavior is checked separately in parser tests and is not represented by these native-PDF timings. Separate legacy XLS tests cover conversion controls and upload-to-match flow, with an additional real LibreOffice round-trip on synthetic data. The concurrency phase stresses intake only, not simultaneous review/export or multi-user authorization.

Earlier UI baseline verification: the full Python suite passed (**319 tests**, 6 dependency deprecation warnings); `npm run lint`, `npx tsc --noEmit`, and the PR CI production build passed; isolated Playwright browser E2E passed **7/7** on synthetic local services. The synthetic API corpus passed **30/30** full flows; its timing details are recorded in `docs/EXTRACTION_AND_PERFORMANCE_AUDIT.md`. These synthetic results are not customer accuracy or production load evidence.

**Security:** dangerous uploads, oversized sheets, path traversal, prompt injection, tenant isolation, retention/deletion and leaked logs.

Advanced extraction update verification (2026-10-31): **407 Python tests passed**, with 88.82% overall line coverage; local OCR 96.88%, PDF parsing 84.72%, spreadsheet parsing 90%, quotation validation 100%, matching 99.51%, exports 96.52%, and persistence 98.85%. The isolated Playwright suite passed **9/9**, including XLSX row/cell navigation and PDF page viewing. Excel checks cover stored formula-cache visibility without accepting formulas as quantity, zero-padded numeric MPNs, Excel's 15-digit numeric precision limit, hidden row/column counts with warnings on affected rows, vertical merged-cell inheritance with explicit anchor-cell provenance, and source cell references for parsed fields. A new workbook-open count test verifies formula-free XLSX files load once and formula-bearing workbooks still load the formula and cached-value views. A bounded read-only XLSX source preview highlights the recorded row and cells; formulas remain unevaluated. A bounded PDF page render lets reviewers compare OCR text with the page and overlays its normalized source rectangle. Multi-page OCR tests verify that selected pages share one open PyMuPDF document for rendering while Tesseract stays capped at two concurrent page images; rotated synthetic scans verify source orientation and OCR line geometry, while an OCR-misread MPN remains unmatched and flagged for review. Synthetic local OCR tests cover engine absence/errors, render/page/image bounds, malformed TSV rows, confidence parsing, output caps, and normalized line boxes. Source coverage fails closed on duplicate or unknown receipt dispositions and reconciles parsed lines and review candidates to the manifest. Luna transport tests cover transient 5xx/429/timeout retry and prompt failure for permanent errors or over-budget retry delays. Provider-gate tests cover request pacing, concurrency caps, circuit opening, recovery probes, and rejection without real sleep. Deterministic worker tests verify ready-queue wait is measured and persisted per attempt. A review-sampling test verifies that source strata beyond the five sample slots remain individual-review exceptions. Ruff's selected syntax/import checks pass. Hosted checks for the previous code head passed on Python 3.10/3.11/3.12, including full-stack E2E and dependency/security scans (CI run `41211960907`, CodeQL run `124568789745`); CI must rerun for the current Excel change.

**Live model path:** `scripts/smoke_live_luna_e2e.py` sends one clearly synthetic line to the configured GPT-6 Luna endpoint, then verifies exact catalog matching, the clean-row human sample, explicit human approval, and draft-only export. It requires `RFQ_LLM_ENABLED=true`, `RFQ_LLM_MODEL=gpt-6-luna`, `RFQ_LLM_API_KEY`, and `RFQ_LLM_BASE_URL` in the process environment. Run with `uv run --extra test python -m scripts.smoke_live_luna_e2e`. It prints only counts/status, retains no source or result outside a temporary directory, and is intentionally excluded from CI because it uses a live provider and may incur cost. If Luna's second-pass validator flags uncertainty or the sample policy assigns an exception, the script exits nonzero and does not approve or export.

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
