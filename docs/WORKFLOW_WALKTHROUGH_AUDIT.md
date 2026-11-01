# RFQ Assistant operator walkthrough audit

Updated: 2026-11-01

This audit records what an individual distributor operator can do in the local prototype, what was checked through the Aside browser, and the product gaps that remain for realistic customer traffic. It is not a claim of production readiness.

## Current operator journey

### Customer request inbox

1. The operator starts a request by pasting buyer email/text and attaching up to five supported PDF, CSV, or Excel files, or by uploading supported sources without pasted text. The form creates one case with independent source receipts, bounded to six sources total.
2. The parser records source regions and locations, then proposes line items. Deterministic parsing handles clear structures; the configured GPT-6 Luna fallback is used only for eligible unresolved text. Pydantic validates shape, and deterministic checks validate numeric/source grounding and exact manufacturer-plus-MPN matches.
3. The operator reviews exceptions and the stable sample of otherwise clean rows. Quantity above recorded catalog stock is shown with both figures and blocks approval until resolved.
4. Quote preparation shows catalog-backed prices, totals only when required values exist, validation blockers, and source evidence. Text-only RFQs have no citation drawer. Document-backed evidence opens in a right-side drawer and links to the original file. The quote remains a draft.
5. The Documents area lists the original request and generated worksheet files, including unavailable-file warnings. The operator can export a draft worksheet and an unsent reply; the application does not send to the buyer.

### Distributor data updates

1. The operator can edit a catalog item or use Ask AI to start a source-backed proposal for that item. Manufacturer remains a field on each item because one distributor can carry several manufacturers; there is no manufacturer administration area.
2. The operator can upload a structured catalog source without writing a prompt, or paste a note for GPT-6 Luna when configured.
3. Proposed additions, changed values, conflicts, and evidence remain staged until the operator accepts a proposal. Rejection leaves active data unchanged; a rejected proposal can be revised with ordinary text.
4. Rows identical to active catalog values are displayed as “no change needed” information and do not appear as decisions awaiting review.

## Issues found during the walkthrough

| Priority | User situation | Current behavior and risk | Next product work |
| --- | --- | --- | --- |
| High | A buyer email has a PDF and spreadsheet attached, or a forwarded email contains corrections from several people. | **Implemented in PR #77:** a case accepts pasted email/text plus up to five attachments, preserves source-level status and provenance, and surfaces duplicate or conflicting line requests for review. Synthetic tests cover the workflow; customer-format validation remains open. | Keep the synthetic multi-source regression suite; validate format coverage against consented, redacted samples before making customer accuracy claims. |
| High | A distributor relies on quote terms, warranty PDFs, lead-time sheets, or other reference documents. | Quote retrieval currently uses active catalog rows and accepted catalog-update evidence for those rows. It does not search a general library of manuals or commercial terms. | Define and build a source-indexed distributor reference library before claiming support for those facts. |
| High | The operator needs to remove a withdrawn price, currency, or stock figure. | The manual editor now stages explicit clear proposals for nullable price/currency and stock values; required identity and description fields still need a replacement value. Acceptance remains a separate human action. | Confirm clear proposals against the distributor's item-master policy and keep the nullable field list aligned with the catalog schema. |
| Medium | An uploaded request is scanned, encrypted, malformed, or contains unreadable pages. | The app fails visibly and retains source warnings, but OCR is not enabled by default in the local prototype. A manual entry path is needed when extraction cannot read the source. | Decide supported OCR formats and deploy a scanner/OCR service with size, password, and failure handling tested in the target environment. |
| Medium | Stock in the catalog differs from live stock in the ERP or warehouse. | The app compares requested quantity with the recorded catalog figure only. It does not query live inventory or promise availability. | Label stock age/source clearly and add a reviewed inventory integration only when authorized live data is available. |
| Medium | A previously created quote draft is reopened after a process restart. | Quote draft content now persists in SQLite. Quote approval records remain in memory, and the main workbench exposes preparation/review rather than a durable approval-and-send lifecycle. | Persist approval/rejection events before any integration that treats quote approval as durable. Keep transmission out of scope until explicitly designed. |
| Medium | A catalog file contains mostly unchanged rows and a few genuine updates. | The update screen now separates unchanged rows from actionable proposals and states when no action is needed. This keeps repeated full-catalog uploads from creating a large false pending queue. | Add a frontend regression test for mixed unchanged/changed/conflicting rows and keep testing large batches for usability. |
| Low | Two requests have the same title on the Overview screen. | The Overview now displays the case ID with customer, line, and unresolved counts so an operator can distinguish them. | Keep IDs visible in every compact request list and verify narrow screen layouts. |

## Verification performed

- Aside browser: inspected the live catalog, keyboard-shortcut dialog, Overview, RFQ workbench, quote draft, quote evidence drawer, stock shortfall state, and distributor update view.
- Synthetic human-input matrix: 11 tests covering ten messy input shapes plus case-boundary completeness passed.
- Full backend suite: 504 passed, 8 dependency deprecation warnings.
- Frontend: OpenAPI/type consistency, ESLint, and production build passed.
- UI probes used synthetic fixtures in an isolated local database. No customer data was used. The GPT-6 Luna quote-evidence path was not exercised in this browser session because no provider was configured for the isolated demo process.
