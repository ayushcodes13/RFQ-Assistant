# Decision and assumptions log

Do not silently revise architecture or customer claims. Add dated entries when real interviews or tests change the facts.

## 2026-10-27 — Initial direction

**Decision:** Test a small human-reviewed RFQ-to-quotation-preparation assistant.

**Why:** Potentially recurring manual work in independent industrial component distribution; small companies can be reached through identifiable owner/inside-sales roles and the workflow can be demonstrated using synthetic BOMs.

**Evidence status:** Research hypothesis. A distributor advertising an RFQ form only verifies that a request channel exists. It does **not** prove its staff have a significant bottleneck, its budget, willingness to pay or ROI.

## 2026-11-01 — ADR 002: Two source-separated operator workflows

**Observation:** The initial product workbench is centered on buyer requests, exact catalog matching, human review, and draft worksheet preparation. Distributors also need to add authorized catalog or commercial-reference data without replacing the active item master blindly. A buyer RFQ and a distributor data update have different owners, evidence, and write permissions.

**Decision:**
1. Keep two explicit entry points: **RFQ inbox** for buyer requests and **Update data** for distributor-owned information. Keep catalog browsing as a separate read/search surface.
2. Treat the first Luna call as an untrusted RFQ field proposal. Validate the returned JSON with Pydantic, deterministic numeric and verbatim-source checks, completeness accounting, and exact manufacturer+MPN matching.
3. After retrieval from approved distributor records, use a second bounded Luna call only to organize an evidence-backed quote proposal. The model cannot browse files or source prices independently. Pydantic validates the draft; Decimal arithmetic recomputes totals; deterministic source checks require request fields to cite the buyer and commercial values to cite distributor data.
4. Stage distributor catalog/reference changes as proposals. Compare each with active data, show new/changed/unchanged/conflicting states, and require a human accept/reject action for every write. Rejected changes remain in history and may be reopened as linked revisions.
5. Keep all model calls optional behind the configured GPT-6 Luna adapter. If disabled or unavailable, preserve source bytes and present an explicit manual/retry path; never claim extraction succeeded with zero proposals.

**Trade-offs:** This is broader than the original extraction-to-worksheet slice. It adds a distributor knowledge lifecycle and a second model stage, so processing cost, source retention, permissions, and recovery behavior must be tested separately. A single-host SQLite prototype remains unsuitable for multi-user production. No live-customer or production-readiness claim follows from this decision.

**Acceptance evidence:** Pydantic/schema tests, source-grounding tests, Decimal calculation tests, accept/reject/reopen persistence tests, and a 10-scenario human-input matrix spanning conversational, document, structured, conflicting, and insufficient input.

## Scope decisions

| Question | Current answer | Revisit when |
| --- | --- | --- |
| Broad AI agents vs simple workflow? | Single focused upload/review/export workbench | Clear pilot need for external automation |
| Which component category? | Select after initial buyer interviews | 2–3 matching buyer problems confirmed |
| Auto-equivalent recommendations? | **No** | Engineer-validated compatibility data and liability model exist |
| Direct ERP integration? | **No** | Pilot blocked by lack of CSV import pathway |
| Autonomous emails? | **No** | Explicit permissions and legal requirements defined |
| Price calculation? | **No by default** | Customer supplies authorized pricing policies and validation |
| Catalog source? | Customer-authorized CSV + permitted public data | Licensing/provenance requirements clarified |
| Hosting and AI vendors? | Local synthetic demo first | Real-file trial needs processor/security agreement |
| Product pricing? | Pilot fee and MRR are hypotheses | Actual buyer commits |
| Marketing claim? | "Preparing a tool to speed review" | Reproducible benchmarks support stronger language |

## Open risks

1. Manufacturer part numbers may be incomplete/ambiguous, making exact matching low coverage.
2. Customers may have effective ERP import features already.
3. Real bottleneck may be pricing/vendor follow-up, not extraction.
4. Part equivalence has physical/compliance consequences.
5. Many distributors are price sensitive or do not process enough multi-line RFQs.
6. Customer requests may contain personal and confidential commercial data.
7. Public catalog licenses may prohibit automated reuse or redistribution.
8. CSV output might not fit a particular ERP without customer-approved mapping.
9. UI might add clicks instead of reducing workload.
10. Time saved does not automatically mean cash saved.

## Change management

New major scope decisions require a short ADR-like section: date, observation/source, options, chosen trade-off, test, rollback/pivot criterion. Keep opposing evidence visible rather than deleting it.

## 2026-10-27 — ADR 001: Component Category & Synthetic Benchmark Selection

**Observation:** Direct customer discovery interviews are blocked pending live distributor access. Live prospect outreach cannot be conducted without external commercial agreements.

**Decision:**
1. Document the customer discovery blocker.
2. Select **Industrial Automation & Control** (Schneider Electric, Siemens, Omron, Eaton, Phoenix Contact) as the initial benchmark component family.
3. Establish a standard quotation-preparation CSV/XLSX export format with clear draft markings and blank pricing unless supplied.
4. Proceed through engineering checkpoints using a comprehensive, strictly labeled synthetic fixture suite and ground-truth annotations covering 20-line BOMs, multi-sheet workbooks, messy email text, cross-brand collisions, and security/adversarial edge cases.

**Rollback/Pivot Criteria:** If eventual customer interviews reveal that another component vertical (e.g. pneumatic fittings or fasteners) dominates manual RFQ volume, substitute the catalog and fixture pack without modifying the core deterministic extraction and matching engine.
