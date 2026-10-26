# Implementation plan and checkpoints

**Rule:** Follow checkpoints in order. Tick only when there is demonstrable evidence; record test commands, artifacts or screenshots in the associated PR.

## Phase 0 — Validate the workflow

- [ ] Interview at least 5 relevant operators; record exact RFQ types, manual steps and biggest bottlenecks. *(Blocked pending live customer access; documented in docs/DECISIONS.md ADR 001)*
- [ ] Find 2–3 prospects willing to share sanitized sample RFQs and sample catalog format. *(Blocked pending commercial agreements; proceeding with synthetic data)*
- [x] Choose exactly one product family and one target export format. *(Selected Industrial Automation & Control; standard quote-preparation CSV/XLSX)*
- [ ] Record a baseline: manual time, error counts and cost assumptions per RFQ.
- [x] Decide whether to proceed, narrow, or pivot; update docs/DECISIONS.md. *(Recorded ADR 001 in docs/DECISIONS.md)*

**Exit:** At least two operators confirm the same costly workflow, and one agrees to a benchmark, ideally paid. This is a guideline, not proof of demand.

## Phase 1 — Test fixtures and schemas

- [x] Create synthetic email, CSV, XLSX, native PDF and scanned PDF fixtures; mark each SYNTHETIC.
- [x] Annotate expected rows including quantities, manufacturer names, MPNs and source locators.
- [x] Define Pydantic/API and TypeScript types for cases, rows, catalogs, matches, audit.
- [x] Lock explicit error states and non-goals.
- [x] Add lint/test commands and automated checks in a PR.

**Exit:** Golden examples can be verified programmatically independent of a UI. (Verified via pytest suite in tests/test_schemas_and_fixtures.py)

## Phase 2 — Single-document ingestion

- [x] Validate size/type and reject unsafe inputs. *(Defenses implemented in rfq_assistant/ingestion/validator.py)*
- [x] Persist original source and content digest locally. *(Implemented in rfq_assistant/ingestion/storage.py)*
- [x] Parse CSV/XLSX deterministically (multiple sheets and empty rows tested). *(Implemented in rfq_assistant/ingestion/parsers/spreadsheet_parser.py)*
- [x] Parse text PDFs; scanned PDF support behind feature flag. *(Implemented in rfq_assistant/ingestion/parsers/pdf_parser.py)*
- [x] Generate line entries with source locations and parse warnings. *(Implemented across all parsers, zero silent dropped lines)*
- [x] Show failures and allow manual correction without losing originals. *(Explicit errors on corrupt/scanned files; line-level warnings)*
- [x] Build an upload screen and pasted text entry. *(Implemented in frontend/src/components/IngestModal.tsx)*

**Exit:** All supported synthetic fixtures produce reviewable rows or explicit error messages. No silent dropped lines. (Verified via pytest suite in tests/test_ingestion_and_parsers.py)

## Phase 3 — Catalog lookup

- [x] Import and validate small sample item-master CSV. *(Implemented in rfq_assistant/matching/catalog.py)*
- [x] Check exact manufacturer+part number; collision is a separate outcome. *(Implemented in rfq_assistant/matching/engine.py)*
- [x] Preserve meaningful part-number suffixes, revision and packaging context. *(Implemented in rfq_assistant/matching/normalizer.py)*
- [x] Expose matches/non-matches with clear origin and no fake availability. *(Strict MatchCandidate grounding, blank prices unless authorized)*
- [x] Add tests for near-identical MPNs and cross-brand collisions. *(Verified in tests/test_matching_and_audit.py)*

**Exit:** Every suggestion is traceable to an actual imported catalog row. (Verified via pytest suite in tests/test_matching_and_audit.py)

## Phase 4 — Review workbench

- [x] Build source viewer + editable line grid. *(Implemented in frontend/src/components/WorkbenchView.tsx)*
- [x] Support missing-value warnings, ambiguous selections and reviewer notes. *(Inline validation, warning pills, candidate cards)*
- [x] Explicitly approve/correct/mark unresolved with audit trail. *(Audit drawer, operator action log)*
- [x] Prevent accidental auto-approval or loss of manual edits. *(Batch approve restricted to verified exact matches; manual edits staged)*
- [x] Verify keyboard accessibility and all empty/loading/error states. *(Shortcuts modal, empty states, tab navigation)*

**Exit:** A user can find and correct a wrong quantity, inspect its source and review a complete case. (Verified via Next.js production build and interactive workbench)

## Phase 5 — Exports and local end-to-end

- [x] Generate deterministic CSV/XLSX quote-preparation export with known schema. *(Implemented in rfq_assistant/exports/generator.py)*
- [x] Clearly distinguish draft from approved output. *(Prominent DRAFT banner in worksheets and emails)*
- [x] Draft email with unresolved questions, but no send action. *(Implemented in rfq_assistant/exports/email_draft.py)*
- [x] Confirm malformed/unresolved rows are blocked or explicitly excluded. *(ExportValidationError stops unapproved exports unless allow_partial is set)*
- [x] Run end-to-end tests upload -> inspect -> edit -> approve -> export. *(Tested in tests/test_exports.py)*
- [x] Run adversarial PDF/CSV/injection tests and document limitations. *(Tested corrupt PDF, macro rejection, prompt injection)*

**Exit:** Full workflow operates on synthetic sample RFQs without unsafe claims. (Verified via pytest suite in tests/test_exports.py)

## Phase 6 — Pilot readiness (not required for initial demo)

- [ ] Obtain consent and review data retention, processors, deletion and permissions.
- [x] Isolate customer files and users with authentication. *(Implemented pilot API key & RBAC in rfq_assistant/auth.py, cross-case export boundary isolation, and optimistic concurrency in rfq_assistant/cases/manager.py)*
- [ ] Benchmark on historical RFQs with human-reviewed ground truth.
- [ ] Measure end-to-end reviewer time against manual baseline.
- [ ] Agree paid pilot success criteria, refund conditions only if feasible and documented.
- [ ] Fix actual operator pain before adding a second feature family.
- [ ] Publish an honest case study only with customer permission.

## Stop / pivot criteria

- Actual staff say parsing is easy and waiting for manufacturer spot prices dominates quote time.
- The ERP already imports BOMs with sufficient accuracy.
- The company handles too few multi-line RFQs for reasonable ROI.
- Exact catalog identifiers are missing from most incoming documents and safe resolution is too expensive.
- Reps reject added review work, or source provenance cannot be maintained reliably.

**Current milestone status:** Phases 1 through 5 fully implemented and verified via automated test suites and synthetic fixtures. Phase 6 (pilot readiness and customer onboarding) is the next milestone when customer discovery and pilot agreements commence.
