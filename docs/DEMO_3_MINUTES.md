# RFQ Assistant: two-workflow distributor demo

**Status:** synthetic, locally reproducible demo guide. This is not a production deployment, measured customer accuracy, or a customer acceptance test. The application prepares **drafts only** and never automatically emails buyers, reserves stock, or deducts inventory.

This replaces the older runbook that referred to the removed Overview navigation and incorrectly described the current quote/audit/clarification panels. The live application now has **RFQ inbox**, **Catalog**, and **Update data**. Do not show a screen or feature that you have not verified in this exact demo run.

## The one-sentence pitch

"Keep manufacturer item records current with human-approved, source-backed updates, then turn a buyer's BOM into an auditable, matched quotation **draft** instead of manually copying every part number."

## Preconditions: rehearsal on the demo computer

1. Use only synthetic materials in `demo-data/` and the built-in industrial sample catalog. Never connect employer, real customer, CRM or Gmail data without explicit authorization.
2. From the repository root, install the documented Python and `frontend/` dependencies, then run:

   ```bash
   ./scripts/demo.sh
   ```

   Open `http://localhost:3010/workspace`. The launcher starts an isolated SQLite store, the backend on `127.0.0.1:8010`, and the Next.js frontend on `127.0.0.1:3010`. It does **not** touch the normal `storage/` directory, but **starting it again clears its own `.demo-runtime/storage/` data**. Keep it running throughout the presentation. Use `./scripts/demo.sh stop` after the meeting. Set `RFQ_DEMO_BACKEND_PORT` and `RFQ_DEMO_FRONTEND_PORT` for occupied ports; never kill unrelated processes.
3. Confirm the sidebar includes **RFQ inbox**, **Catalog**, and **Update data**. Confirm the seeded catalog contains `SKU-SCH-001` with recorded stock 150. If it does not, stop and diagnose startup; do not invent seed values.
4. **Luna is optional, not automatically enabled by the launcher.** To demonstrate model extraction, configure the authorized provider through server-only `RFQ_LLM_ENABLED=true`, `RFQ_LLM_MODEL=gpt-6-luna`, `RFQ_LLM_BASE_URL`, and `RFQ_LLM_API_KEY` outside Git before starting the launcher. Verify a synthetic intake records a model call and that quote preparation reports its actual evidence-mapping status. If credentials or provider access are unavailable, describe the deterministic parser instead of claiming a live Luna result.
5. Before screen sharing, run both flows completely once. Inspect the actual saved/catalog/export values; check source links, the quote draft, and the downloaded XLSX. Close email/CRM tabs and suppress notifications. Keep a screenshot or screen recording of a **genuine successful rehearsal**, not an edited simulation.

## Full buyer demonstration: approximately 5–7 minutes

### Part A: Distributor adds and corrects manufacturer data (2–3 minutes)

Synthetic file: `demo-data/distributor-update-demo.csv`

1. Open **Update data**, attach the file and click **Review file changes**.
2. The source proposes three records: one Schneider item already in the seeded catalog with a stock change **150 → 149**, and two new items, Omron `G2R-1-S` and WAGO `2002-1201`. Check those exact facts against the visible CSV rows; if the screen differs, stop and debug instead of reciting them.
3. Show the current-versus-proposed table and row/filename citations. Mark **Accept** for the Omron and WAGO additions, **Reject** for the Schneider stock change.
4. Before the final action, open Catalog or inspect its API if convenient: neither new SKU should exist yet. Return and click **Review done**.
5. Confirm the two accepted SKUs are now searchable in **Catalog**, but `SKU-SCH-001` remains at stock **150**. Show the accepted/rejected **Decision history**.
6. Open the rejected Schneider proposal. The UI asks what should change. If live Luna is configured and the correction path was rehearsed, enter a grounded short correction, inspect both old and new evidence, then make a **new** review decision. Do not claim that a free-form correction already changed stock or that every generated correction is valid.

**Meaning to the distributor:** "An AI suggestion is never an automatic item-master write. You see the source, approve each proposed change, and apply only after Review done."

### Part B: Buyer BOM to reviewed draft worksheet (2–3 minutes)

Synthetic file: `demo-data/buyer-two-line-bom-demo.csv`

1. Go to **RFQ inbox → New RFQ**, upload the BOM and explicitly enter customer label **Northstar Demo Buyer**. The app may offer a buyer name from an explicit email header, but it must be confirmed by the operator; a sender name alone is not validated customer identity.
2. Submit. Verify that **Omron G2R-1-S (4 units)** and **WAGO 2002-1201 (6 units)** are shown as distinct extracted lines, both matched by exact manufacturer plus full part number against the newly approved catalog. If a field is missing, use the visible manual correction/recovery path; never fill it with a guess.
3. Open each line and its original source evidence. Check row and cell/filename provenance. Approve the rows **only after source comparison**, including the required sample or any exceptions. This is not an automatic match approval.
4. Click **Prepare quote draft**. Show catalog stock (Omron 35, WAGO 42), catalog-backed USD list prices (8.25 and 1.80), human-review warnings, evidence, and any calculated totals that actually appear. Price is a catalog list price, **not** a distributor-approved selling price. Lack of source or currency remains a blocker, not a reason to invent commercial facts.
5. Open the evidence drawer. Confirm that a document-specific source link points to the correct attachment, not just the first email in a mixed-source RFQ. Text evidence is readable without requiring a separate original document.
6. Open **Export draft**, follow the backend's readiness checks and download the clearly labeled draft worksheet. If not all rows are review-approved, explain the blocker or explicitly choose a partial draft; **never call a partial export a validated final quotation**.
7. Optionally show **Unsent clarification** and **Activity history**. Neither sends a message to the customer.

**Meaning to the distributor:** "Instead of a final quote appearing from a black box, every requested item, stock warning and price source is reviewable before a salesperson prepares a commercial response."

### Optional exception (30–45 seconds)

Use `fixtures/rfq_samples/cross_brand_collision.txt` to show a repeated manufacturer part number with different brands, or ask for an item without an MPN. Show the visible warning and human correction path; do not imply the system has chosen a substitute.

## Compact three-minute version

- **0:00–1:00**: Update data → source-backed Omron and WAGO additions → mark accept/reject → Review done.
- **1:00–2:20**: New RFQ → upload two-line buyer BOM → compare source and exact matches → Prepare quote draft.
- **2:20–3:00**: Evidence drawer → Export draft → close with: "Is this source-checking and RFQ cleanup costing your sales team time today?"

If live processing would make the demo exceed three minutes, preload a synthetic case **with a truthful explanation** and demonstrate the real user interactions. Do not pretend a saved case was created live.

## Live failure / recovery matrix

| What happens | Correct response in the demo |
| --- | --- |
| Luna unavailable, times out, or creates an ungrounded field | Show the warning and existing source. Use deterministic extraction or manual review. Do not claim the AI extracted it correctly. |
| A forwarded email has superseded quantities, or multiple items are omitted | Compare with the source, enter/correct each missing row, and keep approvals pending until verified. These source shapes still require independent live testing. |
| Headerless CSV columns are ambiguously inferred | Do not approve. Re-upload with explicit manufacturer / MPN / quantity headers, or manually correct each field. |
| Scanned or password-protected PDF fails | Show the retained original and the extraction failure. Manual entry exists; OCR is not promised in the default demo. |
| Stock is less than requested quantity | Show requested versus recorded catalog stock. Leave the quote blocked until a human confirms an authorized resolution; no reservation happens automatically. |
| A price, unit, customer, or currency is unknown | Keep it blank/flagged, request clarification, or use verified distributor records. Do not calculate a final commercial quote from invented facts. |
| Model-corrected distributor proposal loses item identity | Refuse approval, follow the prior-evidence link, and correct with a complete grounded source. The active catalog must remain unchanged. |
| Browser refresh or export problem | Open the saved case again; inspect backend state and logs in `.demo-runtime/logs/`. A demo-only restart clears its isolated store, so never restart after staging cases unless prepared to re-enter them. |

## Evidence gates and honesty

Run the repository's existing backend, frontend and Playwright suites; in particular, `tests/test_demo_fixture_contract.py` verifies the two demo files match after accepted catalog updates. The synthetic scorecard and 108-trial performance benchmark are **not** measures of live Luna extraction, human effort, customer acceptance, or hosted throughput.

For a real buyer meeting, obtain feedback on the actual manual RFQ workflow: formats they receive, time spent cleaning BOMs, catalog trust, stock source, pricing rules and how a pilot could use **consented/redacted** sample documents.

**Do not claim:** automatic quotation sending, customer-approved sell price, live warehouse availability, inventory reservation/deduction, cross-tenant isolation, validated OCR, commercial time savings, broad arbitrary-email extraction accuracy, or production readiness. A single-distributor demo is the current scope.
