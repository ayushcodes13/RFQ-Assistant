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

- [ ] Build an upload screen and pasted text entry.
- [ ] Validate size/type and reject unsafe inputs.
- [ ] Persist original source and content digest locally.
- [ ] Parse CSV/XLSX deterministically (multiple sheets and empty rows tested).
- [ ] Parse text PDFs; scanned PDF support behind feature flag.
- [ ] Generate line entries with source locations and parse warnings.
- [ ] Show failures and allow manual correction without losing originals.

**Exit:** All supported synthetic fixtures produce reviewable rows or explicit error messages. No silent dropped lines.

## Phase 3 — Catalog lookup

- [ ] Import and validate small sample item-master CSV.
- [ ] Check exact manufacturer+part number; collision is a separate outcome.
- [ ] Preserve meaningful part-number suffixes, revision and packaging context.
- [ ] Expose matches/non-matches with clear origin and no fake availability.
- [ ] Add tests for near-identical MPNs and cross-brand collisions.

**Exit:** Every suggestion is traceable to an actual imported catalog row.

## Phase 4 — Review workbench

- [ ] Build source viewer + editable line grid.
- [ ] Support missing-value warnings, ambiguous selections and reviewer notes.
- [ ] Explicitly approve/correct/mark unresolved with audit trail.
- [ ] Prevent accidental auto-approval or loss of manual edits.
- [ ] Verify keyboard accessibility and all empty/loading/error states.

**Exit:** A user can find and correct a wrong quantity, inspect its source and review a complete case.

## Phase 5 — Exports and local end-to-end

- [ ] Generate deterministic CSV/XLSX quote-preparation export with known schema.
- [ ] Clearly distinguish draft from approved output.
- [ ] Draft email with unresolved questions, but no send action.
- [ ] Confirm malformed/unresolved rows are blocked or explicitly excluded.
- [ ] Run end-to-end tests upload -> inspect -> edit -> approve -> export.
- [ ] Run adversarial PDF/CSV/injection tests and document limitations.

**Exit:** Full workflow operates on synthetic sample RFQs without unsafe claims.

## Phase 6 — Pilot readiness (not required for initial demo)

- [ ] Obtain consent and review data retention, processors, deletion and permissions.
- [ ] Isolate customer files and users with authentication.
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

**Next development PR:** start Phase 1 fixture pack + schema definitions **after** enough discovery evidence exists. Avoid jumping to a multi-category product.
