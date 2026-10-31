# RFQ Assistant

**Human-reviewed RFQ intake and quotation preparation for independent industrial component distributors.**

An early-stage, validation-first product project. This repository is a **product blueprint**, not a shipped application and not evidence of paying customers.

## The problem we are testing

A distributor receives an RFQ through an email, PDF bill of materials, spreadsheet, or typed part-number list. A salesperson reads the request, separates its line items, checks the company's item catalog, resolves ambiguities, and manually drafts a reply. We hypothesize that the repetitive, document-heavy steps consume enough time to justify a paid workflow assistant. Actual pain, frequency, existing systems, and willingness to pay **must be confirmed directly with buyers**.

## The proposed experience

    Buyer sends PDF / XLSX / email
                   |
                   v
            Upload / paste RFQ
                   |
                   v
       Extract lines + source evidence
                   |
                   v
      Match known SKUs / flag unknowns
                   |
                   v
          Salesperson reviews edits
                   |
                   v
       Export quote worksheet + draft
                   |
                   v
       Human sends through normal tools

**Never auto-send a quote. Never invent part numbers, prices, technical equivalence, inventory, or lead time.**

## First product slice

- Accept pasted email text and CSV/XLSX/PDF files.
- Produce editable, source-linked RFQ rows: part number, description, quantity, unit, notes, and extraction warnings.
- Import a small distributor-provided catalog CSV for **exact manufacturer part number matches**.
- Flag missing/contradictory data, duplicates, no-match lines, and possible equivalents as **review required**; no automatic engineering substitute.
- Let an operator approve every row and export a quote-preparation XLSX/CSV plus an **unsent** email draft.
- Record reviewer edits and a lightweight audit trail.

Use one component family for the initial benchmark; do not attempt a universal industrial search engine in v0.

## Who it is for

Small independent US/UK industrial electrical, automation, or electronic component distributors (ideally 5–50 people; evaluate up to 100) with manual quotation intake and a real inside-sales desk. Their website accepting RFQs is **qualification evidence**, not proof of purchasing intent.

## Repository guide

| File | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Instructions for coding agents and mandatory PR workflow |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Mission, user needs, functional boundaries, success criteria |
| [docs/SCENARIOS.md](docs/SCENARIOS.md) | Realistic illustrative workflows and expected human reactions |
| [docs/UX.md](docs/UX.md) | Screens, states, wireframes, interaction and visual design |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Lean architecture, contracts, data and security constraints |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Ordered build checkpoints and definition of done |
| [docs/TESTING.md](docs/TESTING.md) | Ground-truth, adversarial and end-to-end test plan |
| [docs/VALIDATION.md](docs/VALIDATION.md) | Buyer interviews, commercial experiments, outreach guardrails |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decisions, assumptions, open risks and pivot conditions |
| [SECURITY.md](SECURITY.md) | Safe handling and disclosure guidance |

## Build status

- [x] Product scope, design and build checklist documented
- [ ] Buyer conversations confirm the narrow bottleneck *(Pending commercial agreements; proceeding with synthetic validation)*
- [x] Synthetic sample pack and ground truth created *(Phase 1 complete in PR #2)*
- [x] Upload and parser working locally *(Phase 2 complete in PR #3)*
- [x] Catalog matching and review UI working locally *(Phase 3 & 4 complete in PR #4 & #6)*
- [x] Tested quotation worksheet and export *(Phase 5 complete in PR #5)*
- [x] Independent realistic end-to-end demo *(All 7 scenarios verified in PR #7)*
- [ ] One opt-in customer pilot with measured baseline *(Phase 6 pilot readiness)*

## Running locally

### 1. Backend (FastAPI + Python 3.10+)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pytest -v   # Run the unit, integration, contract, and scenario tests

# Start backend server on port 8000 (preloads synthetic catalog automatically)
uvicorn rfq_assistant.api.app:app --host 127.0.0.1 --port 8000
```

### 2. Frontend (Next.js + TypeScript)
```bash
cd frontend
npm install
npm run check:types  # Fail if generated OpenAPI types are stale
npm run build        # Verify typecheck and production build
npm run e2e          # Full-stack Playwright happy path (starts backend + Next)
npm run dev          # Starts web app at http://localhost:3000
```

Frontend wire types come from the backend OpenAPI schema. After changing API
models, regenerate and commit both files:

```bash
python -m rfq_assistant.scripts.export_openapi
cd frontend && npm run gen:types
```

The browser talks to the same-origin Next.js API proxy. Configure
`RFQ_ASSISTANT_API_URL` and, when the backend requires it,
`RFQ_ASSISTANT_API_KEY` in the **server environment only**; never use a
`NEXT_PUBLIC_` variable for credentials. This proxy does not provide user or
tenant authentication: the local demo is single-user, and a shared API key is
not sufficient authorization for a distributor pilot.
When enabling the optional Luna fallback, `RFQ_LLM_DEPLOYMENT_VERSION` may be
set to an immutable provider deployment revision to enable retry-safe caching
of validated model results. If the provider offers only a mutable model alias,
leave this unset; deterministic parse/OCR retry caching still works.
Set `RFQ_LLM_TIMEOUT_SECONDS` to bound each provider request (default 12),
`RFQ_LLM_MAX_ATTEMPTS` to bound transport retries (default 2, maximum 3), and
`RFQ_LLM_RETRY_BASE_SECONDS` / `RFQ_LLM_RETRY_MAX_DELAY_SECONDS` to control
transient-error backoff (defaults 0.2 / 2 seconds). Only timeouts, HTTP 408,
429, and 5xx are retried; permanent errors and malformed responses are not.
If a provider's `Retry-After` is longer than the configured maximum, the call
fails promptly and unresolved fields go to human review instead of waiting
through a long quota pause.
The reused Luna client applies process-local concurrency limits and a circuit
breaker. Set `RFQ_LLM_REDIS_URL` and install `pip install -e '.[production]'` to enable atomic
request-start pacing shared across worker processes; `RFQ_LLM_SHARED_PACE_PREFIX`
can separate provider quotas (default `{rfq-luna}:provider`). A shared 429
`Retry-After` hold pauses other workers using that prefix. Redis calls have
short socket timeouts and fall back to process-local pacing during an outage,
so configure a Redis health alert before relying on the global quota. Without
the URL, pacing remains process-local. Configure `RFQ_LLM_MAX_CONCURRENT_REQUESTS`
(default 2), `RFQ_LLM_REQUESTS_PER_MINUTE` (default 60),
`RFQ_LLM_CIRCUIT_FAILURE_THRESHOLD` (default 4),
`RFQ_LLM_CIRCUIT_OPEN_SECONDS` (default 30), and
`RFQ_LLM_ADMISSION_TIMEOUT_SECONDS` (default 10). If either provider gate
rejects a call, the affected extraction goes to human review. Global pacing is
shared when Redis is configured; concurrency limits and the circuit breaker
remain process-local and require separately coordinated deployment settings.
Open `http://localhost:3000` for the product landing page and `http://localhost:3000/workspace` for the RFQ workspace. The workspace supports RFQ intake, line-level provenance review, catalog browsing, approval, and draft worksheet export.

### Client demo

For a clean, predictable demo, start both applications with the isolated demo launcher:

```bash
./scripts/demo.sh
```

It starts the API with synchronous ingestion, serves the workspace at
`http://localhost:3010/workspace`, and uses a fresh SQLite database and file
storage under `.demo-runtime/`. This reset does not delete or change `storage/`
or its existing RFQs. The launcher refuses to use occupied ports; choose
alternates with `RFQ_DEMO_BACKEND_PORT` and `RFQ_DEMO_FRONTEND_PORT`. Stop only
the processes started by this script with `./scripts/demo.sh stop`. Synthetic
drag-and-drop examples are in `demo-data/` (email text, PDF, XLSX, and catalog
CSV). The catalog is preloaded automatically in a fresh demo database.

### Local persistence

The API stores RFQ cases, extracted lines, audit events, and the imported catalog
in `storage/rfq_assistant.sqlite3`; uploaded source files and generated exports
remain under `storage/`. These local files are ignored by Git. Set
`RFQ_ASSISTANT_DB_PATH` to place the SQLite database elsewhere. This supports
restart recovery for a single local/demo workspace; it does not provide
production backup, encryption, tenant isolation, or a customer data-retention
policy.


## Engineering principles

**Small, inspectable, fail-closed, privacy-aware.** Prefer deterministic extraction of IDs/quantities and exact catalog matching over fancy agents. Use models only where document layout or language extraction needs them. Each output shows a source and allows correction. Make it obvious when the system does not know.

**Ownership:** Personal project only. Do not transfer any employer-owned code, credentials, datasets, repositories or contacts.

## Development workflow

Every change to application code, documentation or configuration happens on a feature branch and is proposed to **main through a pull request**. Follow [AGENTS.md](AGENTS.md). After a PR is successfully merged, its feature branch should be deleted; the repository includes a best-effort same-repository branch cleanup workflow.

## License

No open-source license has been selected. Public visibility does **not** grant reuse permission. Choose a license explicitly before external code contributions.
