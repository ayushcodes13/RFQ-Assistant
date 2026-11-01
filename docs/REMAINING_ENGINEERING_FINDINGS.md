# Remaining Engineering Findings

Audit snapshot: 2026-11-01, `main` at `d107d083db8e415fb1b40a1751e8764557383ee7` (PR #70).

This is a delivery ledger for the remaining production-engineering work. Passing local and CI checks establish software behavior against synthetic fixtures; they do not establish real-distributor accuracy, operational readiness, or production security.

## Baseline

- PRs #58, #60–#69 had already merged before this audit. They cover individual review of Luna-derived rows, export readiness, local intake throttling, unsent clarification drafts, legacy XLS fail-closed behavior, a single-operator login gate, Redis fallback reporting, README screenshots, audit history, XLSX preflight performance, and catalog-edit/stock-shortfall workflow. PR #70 adds distinct per-user API credentials and encrypted sessions in the browser.
- The app remains explicitly single-workspace. [Persistence](../rfq_assistant/persistence.py) stores cases, catalog rows, proposals, quote drafts, and ingestion jobs in globally keyed tables without `workspace_id` or `organization_id`; [API initialization](../rfq_assistant/api/app.py) constructs one process-wide catalog, case manager, worker, and export generator. API credentials identify a user and role, but no organization boundary exists. Never host unrelated distributors in one deployment or database.
- A case still has one optional `source_file` in [the case schema](../rfq_assistant/schemas/models.py); `POST /api/rfqs` accepts one `file` or one `pasted_text` field in [the intake route](../rfq_assistant/api/app.py). Multi-file email-plus-attachment intake is unsupported. Existing source provenance is for that one source.
- [The onboarding gate](PRODUCTION_CUSTOMER_ONBOARDING.md) already says a customer environment needs isolation, deletion/retention, monitored processing, recovery, and cross-customer access tests. [Testing docs](TESTING.md) state that synthetic corpus and concurrency tests are not customer accuracy or full production-capacity evidence.
- CI runs Python 3.10–3.12, backend tests and coverage, frontend lint/build/typecheck, full-stack E2E, CodeQL, Bandit, npm audit, pip-audit, and Gitleaks. At this snapshot PR #70's complete check suite passed. Pip-audit remains informational; its finding set needs fresh, per-advisory triage before a dependency upgrade.
- Existing synthetic performance evidence is recorded in [the extraction/performance audit](EXTRACTION_AND_PERFORMANCE_AUDIT.md). It measures a 30-document corpus and 128 concurrent intake creations, not the requested 10/50/100/500-line workflow, varied attachment counts, full workflow p50/p95, peak memory, or recovery matrix.

## Findings and order

| Priority | Finding | Current evidence | State |
|---|---|---|---|
| P0 | User identity and role attribution | PR #70: backend-issued identity, separate keys/roles, encrypted short-lived browser session; protected E2E covers viewer denial/admin write/logout/tamper | Implemented for one workspace; merged |
| P0 | Tenant/workspace data isolation | Global tables and singleton service objects; no organization scope on cases, catalog, objects, jobs, exports, or audit | Open; do not claim multi-tenant readiness |
| P0 | Multiple email attachments in one RFQ | One `source_file`, one intake upload field, one source digest/job | Open |
| P0 | Production security and operations | Existing controls include role gates, upload limits/scanning, path defenses, formula escaping and case-scoped exports. Shared edge throttling, production storage/retention/deletion, conversion isolation, deployment headers/CSRF review and complete threat-driven access tests still need evidence | Partially implemented; adversarial review required |
| P1 | End-to-end performance/reliability | Current synthetic measures are narrower than requested; no 500-line/varied-multi-file matrix or full queue/crash/retry report | Open |
| P1 | Static analysis and dependency findings | CI type/lint/security checks exist, but mypy is non-blocking and pip-audit is informational | Open; refresh findings and ratchet without blanket suppressions |
| P1 | Distributor evaluation readiness | Synthetic/adversarial fixtures exist; no consented, redacted customer holdout, reviewer-time study, or buyer-demo evaluation receipt | Synthetic harness exists; real-world evidence open |

## Safe implementation sequence

1. **Workspace boundary design and migration contract.** Define workspace identity, legacy local-workspace migration, default-deny lookup semantics, and ownership on every persisted/resource type. Keep the single-workspace deployment guard active. Add adversarial acceptance tests before changing service behavior.
2. **Backend persistence isolation.** Add workspace-scoped compound keys/foreign keys and migration, then pass authenticated workspace context through every case, catalog, audit, quote, job, and export path. Avoid user-controlled workspace IDs. Test guessed IDs, cross-workspace list/read/edit/delete, and worker/job fencing.
3. **File/object isolation and frontend identity wiring.** Bind source/export objects and URLs to server-resolved workspace ownership; test direct object references and delete/retention behavior. Only then consider multiple workspaces in one deployment.
4. **Multi-attachment case model.** Add source-document records and per-attachment processing state, bounded multipart ingestion, digest-based duplicate accounting, conflict review and retry. Preserve the legacy single-source representation during migration. Require exact source document plus page/sheet/row provenance on every extracted field, partial-failure visibility, and one consolidated review/export.
5. **Security remediation in small PRs.** Review upload/parser/converter subprocess boundaries, ClamAV failure behavior, shared rate limiting, CSRF/CORS/security headers, output escaping, logging/secrets, and retention against current code and deployment assumptions. Fix only verified issues and record exploit-oriented tests.
6. **Measured reliability and performance.** Add synthetic 10/50/100/500-line plus varied-attachment runs; report intake, extraction/OCR/model, queue, matching, review, and export p50/p95, throughput, memory and failures. Add timeout, cancellation, duplicate submission, lock, worker kill/restart and idempotency cases. Optimize only measured bottlenecks.
7. **Quality gate and evaluation readiness.** Triage current advisory IDs; fix dependency compatibility in isolated PRs; ratchet mypy by module; verify OpenAPI generation. Publish the synthetic/adversarial scorecard, buyer-demo checklist, operator feedback form, and an opt-in path for consented/redacted customer examples. Keep all commercial claims unvalidated until measurements exist.

## Readiness decision

The repository supports a local synthetic demo. Per-user roles work within one isolated workspace. It is **not ready for a shared multi-organization deployment or production use**: tenant-scoped storage/API authorization and multi-attachment case processing remain P0 blockers. A controlled pilot also requires the onboarding, privacy, operational, and customer-approved evaluation gates in [PRODUCTION_CUSTOMER_ONBOARDING.md](PRODUCTION_CUSTOMER_ONBOARDING.md). No customer accuracy, capacity, or ROI result is claimed.
