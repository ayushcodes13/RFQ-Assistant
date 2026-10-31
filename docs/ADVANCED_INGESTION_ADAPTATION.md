# Advanced ingestion architecture: RFQ adaptation

This note records the backend patterns worth applying to RFQ Assistant, what the
current code already does, and what still needs to change. It describes the
reference project's ideas at an architectural level; its code, credentials, and
data are not copied into this product.

## RFQ workflow today

```mermaid
flowchart TD
    A[Upload or paste RFQ] --> B[Validate type, size, malware, digest]
    B --> C[Persist original + PROCESSING case]
    C --> D[SQLite queue: lease, heartbeat, retry]
    D --> E{Same source and parser profile cached?}
    E -->|Hit| J[Load case-scoped parsed artifact]
    E -->|Miss| F{Format adapter}
    F -->|PDF| G[pypdf native text + PyMuPDF image triage]
    G --> H[Bounded local Tesseract on selected pages]
    F -->|XLSX / CSV| I[Read-only openpyxl / streaming CSV]
    F -->|Text| I2[Line-based deterministic extraction]
    H --> COV[Structured lines + candidates + coverage manifest]
    I --> COV
    I2 --> COV
    COV --> SAVE[Save parser artifact with source/profile digest; lease-fenced]
    SAVE --> J
    J --> K{Unresolved fields or unknown regions?}
    K -->|No| M[Exact manufacturer + MPN catalog lookup]
    K -->|Yes, Luna configured| L[Luna proposes grounded fields]
    K -->|Yes, Luna unavailable| N[Preserve as visible human-review exceptions]
    L --> O[Strict JSON/schema + numeric + verbatim evidence gates]
    O --> P[Second Luna consistency check; warning-only; skip if no rows]
    P --> M
    N --> M
    M --> Q[Risk-stratified sample of up to five clean rows]
    Q --> HUMAN[Human reviews exceptions and sample]
    HUMAN --> BATCH[Explicit batch approval only after clean sample]
    BATCH --> T[Blocked or draft-labeled worksheet + unsent email]
```

The deterministic path is deliberate. A workbook cell under a recognized
`Quantity` heading is already structured evidence; re-asking a model to read it
adds latency and cost without adding useful information. The model is reserved
for uncertain or unfamiliar layouts, and its output is only a proposal. Numeric,
schema, verbatim-source, exact-match, reviewer, and export checks remain
deterministic gates. Quantity text is parsed as a decimal, checked against the
source quote, then rejected if the application's numeric representation would
overflow or change that value. The second model pass can add a warning; it cannot approve.

## Patterns to transfer

| Engineering pattern | RFQ fit | Current state | Work still needed |
|---|---|---|---|
| Extract once into versioned, reusable document artifacts | Avoid redoing expensive parsing/OCR/model work after retries or case reopen | Deterministic parse/OCR and validated Luna results are zlib-compressed and cached per case by source digest and complete parser/model profile; Luna caching is enabled only when `RFQ_LLM_DEPLOYMENT_VERSION` pins an immutable revision; raw payloads are capped at 10 MiB, writes are lease-fenced, and case deletion cascades to artifacts | Extend reuse across cases only after workspace/tenant identity and retention are real; verify the provider’s deployment versioning contract before enabling the pin in production |
| Page-level PDF triage and bounded OCR | Spend CPU/OCR only on pages likely to need it; make failures visible | Native text uses pypdf to preserve RFQ row grouping; PyMuPDF estimates image coverage; local Tesseract has a 10-page/document cap and two-page concurrency; manifests now persist per-page counts/hashes, empty state, and OCR decision/outcome including failures | Add page rotation/render state and parser-version provenance |
| Structured Excel ingestion without interpreting formulas as facts | Preserve identifiers and quantities while preventing workbook calculations from becoming trusted inputs | openpyxl is read-only; all visible/hidden sheets are inspected; formula-backed quantity is not calculated; manifests include header row, formula count, hidden/empty sheet status, row/column limit state, disposition counts, and hashes | Add stronger formula-to-line field receipts and parser-version provenance |
| Versioned processing and fenced worker writes | Prevent stale retries from overwriting newer work | SQLite queue uses claim leases, heartbeat, bounded retries/backoff, and fenced snapshots | Keep this for local single-host use; production needs a shared queue/store adapter, worker supervision, dead-letter visibility, and tenant-aware idempotency |
| Bound concurrency and expensive stages | Keep OCR/model work from overwhelming the process and expose latency contributors | Two concurrent ingestion workers; PDF OCR capped at two pages; LLM input bounded; parse/OCR reuse on same-case retries; stage timings and token/call telemetry are persisted without RFQ text | Add per-stage queue wait, OCR, extraction, validation, and persistence metrics with sanitized outcome labels; configure global model/OCR budgets across workers |
| Model-assisted interpretation with deterministic checks | Recover unfamiliar input without trusting model output | Luna-only optional adapter; strict Pydantic JSON, source quote/field verbatim checks, numeric/unit grounding, one repair attempt, second warning-only consistency call; case stores model, deployment pin, prompt hash, schema and validator versions, call/repair/review counts, stage time, and tokens when reported | Verify provider deployment immutability guarantees and evaluate cache-hit behavior on a labeled retry corpus |
| Reduce human effort through risk-based sampling | Review a few representative clean rows while keeping ambiguous rows visible | Up to five clean rows are sampled across extraction path and source location; the UI states the sampled strata and that this is not a statistical guarantee; exceptions stay individual; a correction disables batch approval | Validate the workload/error tradeoff on held-out, customer-approved RFQs before using this as a production approval policy |

## Why not copy every reference behavior

Some reference behaviors serve conversational search across long financial
documents, rather than extracting RFQ line items. In particular, LLM summaries
of every worksheet can multiply model calls and delay a quote request. RFQ
Assistant should keep full row structure and source coordinates, summarize only
when a measured operator task benefits, and avoid paying for model work on rows
the parser can read exactly. Likewise, a Redis-backed multi-host queue belongs
in the production deployment milestone; the local SQLite queue is simpler and
already has the right lease/fencing concepts for this prototype.

## Production-quality work still required

1. **Coverage manifest closure:** the implementation aggregates observed
   non-empty regions and records empty page/sheet state, OCR decision/outcome,
   detected header row, hidden-sheet status, formula-backed fields, and explicit
   limit/parser-failure state. Continue with per-row disposition reconciliation,
   hidden row/column coverage, and render/rotation handling for OCR. A failure or
   cap must never disappear from the report or permit the clean-row batch path.
2. **Processing provenance:** the case now saves a parser/OCR profile hash,
   prompt hash, schema and validator versions, model label, call/repair/review counts, stage
   durations, and token totals when the provider reports usage. Add immutable
   deployment and validator version identifiers, queue-wait/retry measurements,
   and sanitized outcome labels.
3. **Retry-safe derived artifacts:** parser/OCR results are cached per case by
   source digest and parser/OCR profile; a retry with the same profile reuses
   them, and a changed digest/profile cannot hit. Extend to workspace-scoped
   reuse only after tenant identity and retention controls exist. Oversized
   derived artifacts are skipped rather than allowed to grow without a bound.
   Cache validated Luna results only when the deployment version is explicitly
   pinned and that key also includes model, prompt, schema, validator, and exact
   source segments.
4. **Human effort policy:** keep all uncertain, OCR-derived, guessed-layout,
   formula-backed, collision, and missing-field rows as individual exceptions.
   Sample at most five otherwise-clean rows across meaningful strata. If a
   sample needs correction, expand review to the affected stratum (or all clean
   rows when the scope cannot be safely determined); never batch-approve the
   remainder on a failed sample.
5. **Production worker boundary:** replace SQLite/local filesystem with a
   durable shared queue, private object storage, authenticated tenant-aware
   persistence, worker isolation for LibreOffice/OCR, resource limits, backup,
   monitoring, retention, and deletion controls before a real customer pilot.

## Acceptance evidence for the end-to-end target

- A corpus that varies page rotation, native/scanned/mixed PDFs, repeated table
  headers, multiple/hidden/formula-heavy sheets, blank/title rows, unfamiliar
  headers, and text RFQs; every nonempty source region reconciles to the manifest.
- Mutations to model JSON (wrong type, missing/duplicate line, invented number,
  quote mismatch, wrong source locator, invalid unit) are rejected or become a
  visible exception; malformed second-pass output never approves.
- Repeated jobs, expired leases, worker crashes, and changed source/model
  versions prove that cached artifacts are reused only when safe and stale
  writes cannot win.
- The UI shows concise counts for clean rows, exceptions, sampled rows, source
  coverage, and model/OCR warnings. A reviewer can navigate each item back to
  its original page/sheet/row and exports remain blocked until policy passes.
- Report extraction recall, critical-field exactness, unflagged critical error
  count, coverage, correction burden, and review time separately. Five sampled
  rows are a workload control, not proof of a statistical accuracy rate.
