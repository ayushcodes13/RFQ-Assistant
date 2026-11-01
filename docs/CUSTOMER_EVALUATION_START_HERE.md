# Operator-led evaluation: start here

**Audience:** independent industrial/electronic component distributor operators, sales managers, and owners evaluating RFQ Assistant.

**Status:** controlled synthetic-data evaluation kit. It is **not** a customer-validated product, an independently verified accuracy benchmark, or approval to process live customer data. The app is a single-workspace local prototype. See [production onboarding](PRODUCTION_CUSTOMER_ONBOARDING.md) before any customer-data pilot.

## What the evaluator is testing

Can an inside-sales operator (a) stage manufacturer/catalog updates and approve only the correct changes, then (b) turn a buyer BOM into a reviewable quotation worksheet with correct manufacturer, part number, quantity, price provenance and clearly displayed exceptions?

The operator should keep their usual quotation/ERP process in charge. Nothing here sends an email, reserves stock or guarantees availability. The first session uses **only synthetic files** committed under `demo-data/`. Real buyer RFQs, customer catalogs, commercial prices, contacts, and provider keys must not be uploaded to a public demo, GitHub issue, CI run, or shared support chat.

## Five-minute preparation

1. Run locally on an isolated machine with the project dependencies installed as described in [README](../README.md). From the repository root run `./scripts/demo.sh`; open `http://localhost:3010/workspace`.
2. Confirm the app displays **RFQ inbox**, **Catalog**, **Update data**, and the synthetic sample item master. Do not assume a live LLM: the demo launcher does not configure one.
3. Run the [two-workflow demonstration](DEMO_3_MINUTES.md) once before involving an evaluator. Record the commit SHA, environment, whether Luna/OCR was configured, and actual test results. The isolated demo launcher resets its own state when started again.
4. Ask the evaluator to work through the interface themselves while an observer records tasks, confusion, corrections, and completion time. If recording a screen or voice, obtain separate permission. Do not record confidential information.
5. Copy the blank [session scorecard](../demo-data/evaluation-session-sheet.csv) into a **private approved location**. Never commit a completed scorecard, a customer document, or personally identifying feedback to the repository.

## Operator script: first session, synthetic sources only

| Step | Operator action | What the observer must verify |
| --- | --- | --- |
| A1 | Open **Update data** and upload `demo-data/distributor-update-demo.csv`. | Three proposals are visible, with original source location and old/new values; nothing applies automatically. |
| A2 | Accept the two new Omron/WAGO items; reject the Schneider stock change. | The active catalog stays unchanged before **Review done**; each proposal has an explicit decision. |
| A3 | Click **Review done** and search in **Catalog**. | Only accepted products exist. Schneider stock stays at 150. Decision history contains the rejection. |
| A4 | Open the rejected item and describe a correction. | The system proposes a new reviewable change; it does not silently change the catalog. This step needs a configured authorized model and is marked **not tested** if no model is available. |
| B1 | Go to **RFQ inbox → New RFQ**, upload `demo-data/buyer-two-line-bom-demo.csv`, add a synthetic buyer label, and submit. | Both lines appear: Omron G2R-1-S quantity 4 and WAGO 2002-1201 quantity 6, with exact manufacturer+MPN matches and source row/cell evidence. |
| B2 | Open source evidence and review each line before approval. | The operator can locate original values and correct or withhold approval; no unseen automatic approval. |
| B3 | Prepare the quote draft, inspect prices/stock, then export the worksheet. | Prices are catalog-backed, calculations are deterministic, and the XLSX is downloadable and marked draft. No customer email is sent. |
| B4 | Try an unresolved row, missing quantity, unknown item or stock shortfall. | The interface identifies the blocker, preserves the source, and offers a manual/clarification path rather than an invented complete quote. |

The tests in [PR #106](https://github.com/ayushcodes13/RFQ-Assistant/pull/106) cover a deterministic browser version of steps A1–B3. They **do not** establish that humans can use the interface unaided or that the model reliably understands arbitrary customer requests.

## Real-human input challenge

After the primary script, try the ten **synthetic** input shapes from [H01–H10](HUMAN_INPUT_TEST_MATRIX.md). Do not score an unclear case as correct simply because the app returned a row: compare every requested item to a separate human annotation of the original source. For each scenario, record one of **correct**, **reviewable uncertainty**, **silent omission/wrong output**, or **blocked with recovery**.

- H01–H06: typo-heavy email, shorthand, forwarded correction, dictation, mixed-language note, and a non-catalog-ready generic request.
- H07–H10: unusual spreadsheet, loose CSV, wrapped PDF, and scanned/corrupt input.

The repo has synthetic parser and mocked-provider coverage for these cases, and the operator audit records live-model failures on some multi-item/ambiguous messages. Repeat these probes with the *actual* configured model and preserve failures in private review records. Do not call mocked tests live-model accuracy.

## How to measure (no invented numbers)

Before showing the app, ask the evaluator to complete an equivalent, consented synthetic RFQ manually using their normal process. Define the same start/end points for the manual and assisted runs, then time active effort and elapsed time separately. Count every correction and every omitted or incorrectly grounded manufacturer, MPN, quantity, unit, price or source. Record where they stopped or switched to their old tools.

Use the more detailed [operator feedback record](OPERATOR_FEEDBACK_FORM.md) for each task. The CSV template is only a convenient session index, not a substitute for source-by-source ground-truth checks. Ask the operator which step would save real work, whether they would repeat the workflow next week, and what would prevent a paid pilot.

**Proposed internal advancement gates (not achieved claims):** no unflagged critical item/quantity/price errors; no unauthorized catalog writes or external sends; every processed source accounted for; a human can understand and recover from a failure; the exported worksheet is usable in the evaluator's existing workflow; and at least two target-role operators provide specific repeated-workflow feedback. Any unflagged critical error is a stop-and-investigate event, even if aggregate test scores are high.

## End of session: record the outcome

Write a short evaluation summary in the **approved private system** with the build SHA and environment, test cases and input types, manual versus assisted effort (if truly measured), critical errors, corrected rows, remaining tasks, and specific operator comments. Classify the result as **synthetic demo completed**, **operator evaluation completed**, or **customer-data pilot authorized**; these are not interchangeable.

A successful synthetic demo may justify another meeting. It does **not** permit processing live RFQs. Before any real customer-data pilot, complete the signed scope/data-processing requirements, per-customer isolated environment, HTTPS/auth/roles, private storage/retention, malware-scan enforcement, model/provider authorization, cross-customer security tests, and recovery checks in [production onboarding](PRODUCTION_CUSTOMER_ONBOARDING.md).

## Customer-facing explanation

> RFQ Assistant helps an inside-sales team review incoming BOMs and update its approved distributor catalog. It keeps the source beside each proposed line and prepares a draft worksheet; people still verify prices, availability, exceptions and the final quotation. We are evaluating whether this reduces manual review effort with real operator feedback. This demonstration uses synthetic data.
