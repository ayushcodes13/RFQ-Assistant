# Demo rehearsal verification — RFQ Assistant

**Date:** 2026-10-31
**Branch:** `audit/e2e-test-defects`
**Scope:** Isolated local rehearsal using synthetic data. No production service or customer files.

## Results

| Check | Result | Evidence / limit |
|---|---|---|
| Python regression suite | 269 passed, 1 deprecation warning | `pytest -q`, isolated SQLite database |
| Audit tests | 121 passed, 1 deprecation warning | `pytest -q tests/end_to_end_audit/` |
| Synthetic XLSX evaluation | 20/20 lines, 80/80 critical fields, 20/20 exact matches, 20 source locators, 0 unflagged critical mismatches | `scripts.evaluate_synthetic_demo`; synthetic ground truth only |
| Synthetic document corpus | 30/30 full API workflows; 128/128 concurrent create requests | 8 CSV, 7 PDF, 8 text, 7 XLSX; does not establish general input accuracy |
| Playwright rehearsal | 6/6 passed on each of 3 clean isolated DB runs; final expanded run 7/7 passed | Added regression for stale export dialog state across two cases |
| Frontend lint and types | Passed | `npm run lint && npm run check:types` |
| Production build | Passed | Built from an isolated frontend copy to avoid the user's existing local server artifacts |
| Manual browser walkthrough | Passed for synthetic pasted text and XLSX upload | Started with empty DB; created/reviewed a 2-line case, opened line provenance, generated/downloaded its draft, then uploaded the 20-line XLSX fixture and checked its unresolved case |
| Export dialog case isolation | Fixed and verified | A prior export link used to persist when opening a different case. Export modal now gets a fresh state per open/case; unresolved XLSX case showed `NEEDS_REVIEW` with no stale download link |
| Downloaded workbook structure | Passed | OOXML ZIP integrity verified with Python stdlib; one `Quote Preparation` sheet; draft-only banner; 2 approved rows, quantities, exact SKU/MPN/OEM values, and source locators present |

## What the browser rehearsal proves

- Synthetic text input creates a case and extracted lines.
- Human review and quantity correction happen through the UI; export is blocked until required review data is complete.
- The export endpoint returns an XLSX MIME type and a ZIP-signature payload, and the export manifest marks the output as a draft.
- Browser refresh retains the case and review state.
- The quote send route reports `simulated_local` and `outbound_transport_invoked: false`.
- An unsupported upload reports an error, creates no case, and allows recovery through valid pasted text.

The browser rehearsal used the actual download link and the downloaded OOXML package was inspected. The workbook was **not** opened in Excel/LibreOffice. The browser flow did not restart the backend process. Python persistence tests and API corpus runs provide separate evidence, not a substitute for those manual checks.

## Local server used for manual inspection

To avoid colliding with existing services on ports 8000 and 3000, rehearsal used:

- Backend: `http://127.0.0.1:8001`, isolated SQLite database under `/tmp/rfq-assistant-rehearsal-20261031/`
- Frontend: `http://localhost:3001/workspace`, isolated source copy under `/tmp/rfq-assistant-rehearsal-20261031/frontend`
- Catalog: 24 synthetic/sample catalog entries loaded at backend startup

The server is for local manual inspection only. Before presenting, start a fresh isolated DB and frontend/backend pair using the commands in `docs/DEMO_3_MINUTES.md`, verify the cases list is empty, and create only the demonstration cases you intend to show.

## Remaining demo checks

1. Run the live walkthrough once in the actual browser and meeting display setup, including a genuine browser download and opening the draft workbook.
2. Verify audio/screen share, browser zoom, notifications, and no unrelated customer or credential material is visible.
3. Rehearse a controlled failure path and the spoken explanation; do not improvise values or approve unresolved lines.
4. Confirm the chosen synthetic fixture's current UI output before describing extraction or warnings.
5. Keep the product framed as human-reviewed quotation preparation. This rehearsal does not demonstrate hosting, customer readiness, accuracy on arbitrary RFQs, ERP integration, real pricing, or measured time savings.
