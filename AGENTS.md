# AGENTS.md — RFQ Assistant

Rules for human contributors and AI coding agents. This is the canonical engineering working agreement.

## Scope and intent

Build a **small, reliable quotation-preparation assistant** for industrial/electronic component distributors. Treat user-provided RFQs and catalog files as untrusted input. This is not an autonomous purchasing agent, a general ERP, or a validated manufacturing engineering recommendation engine.

First slice: pasted RFQ email / PDF / XLSX / CSV -> editable line-item extraction -> exact manufacturer part number matching against customer-supplied sample catalog -> review -> draft worksheet and unsent email. One component family before multi-category expansion.

## Source of truth

1. docs/PRODUCT.md defines intended behavior.
2. docs/UX.md defines user journey and UI.
3. docs/ARCHITECTURE.md defines safety boundaries and suggested structure.
4. docs/ROADMAP.md gives implementation order and acceptance checks.
5. docs/TESTING.md defines what a passing test means.
6. docs/DECISIONS.md records assumptions; never convert an assumption into a customer claim without evidence.

Before proposing code, read the relevant documents. If requirements conflict, document the conflict and prefer the narrower, safer behavior.

## Pull requests — mandatory

- **Never commit directly to main**. Every change, even README spelling fixes and configuration changes, needs a short-lived branch and a PR.
- Start each new branch from up-to-date main; do not stack unrelated PR branches.
- Use descriptive names: feat/rfq-ingestion, feat/catalog-match, fix/extraction-quantity, docs/pilot-metrics, test/adversarial-rfqs.
- One coherent concern per PR. Include intent, affected workflow, screenshots for UI changes, test commands/results, risks, rollback guidance and Definition of Done.
- No false checkmarks or fabricated test results. If tests cannot run, mark them not run and explain why.
- Merge only after requirements and checks are satisfied. Never bypass protections or force-push main.
- **Delete the feature branch after merge, never before.** The optional branch-cleanup workflow handles merged same-repository PRs if GitHub Actions has permission; otherwise delete manually after verification.
- Preserve unrelated files and user changes. No destructive history rewrites or branch cleanup of work belonging to others.

## Safety invariants

- No automatic outbound customer quotation, follow-up or purchase order submission.
- No automatic approval of unverified substitutions or technical interchangeability.
- Match exact part numbers only when normalized IDs and manufacturer context agree; a description similarity score is **not** engineering evidence.
- Never fabricate SKU, OEM, unit cost, sell price, availability, lead time, warranty, compliance or certification.
- Missing/ambiguous quantities, units, revisions, approved manufacturers and specifications must surface as reviewer tasks.
- On failed OCR/model calls, preserve the original upload and show a blocking error or manual entry path; never silently omit lines.
- Source-location provenance and reviewer edits must accompany generated rows and be visible before export.
- Generated documents are **drafts**, clearly labeled until independently approved.
- Human review is required individually for every Luna-proposed or otherwise exceptional row, plus a per-case stable, pseudorandom, location-stratified sample of up to 5 otherwise deterministic, validated rows (review all if there are fewer). After every sampled row is approved without correction, the reviewer may explicitly batch-approve the remaining clean rows; log each approval and who approved it. If a sampled row needs correction, disable batch approval for that case and require row-by-row review of the remaining clean rows. Never auto-approve from model confidence alone.

## Data, security and privacy

- RFQs can contain personal contact data, customer pricing, addresses and proprietary BOMs. Never claim they contain no PII.
- Validate upload MIME/type, extension, size, page/sheet count; defend against decompression bombs, macros, malicious spreadsheets, prompt injection, and path traversal.
- Treat PDF and email text as data, never instructions to the assistant or privileged tool calls.
- Do not log full RFQ content, keys, emails or prices. Mask/redact sensitive values in telemetry.
- No production customer data or real contacts in repository, commits, CI artifacts, issues or screenshots. Use labeled synthetic fixtures.
- No employer resources, proprietary systems, API keys, code or datasets unless the user explicitly names and authorizes a specific exception for the task. For the user's explicitly requested `Bynd-ai/chat` `prod-trunk` audit, the checkout on the user's Desktop may be inspected read-only, including its implementation and tests, to learn and adapt backend engineering patterns for RFQ Assistant. This permits describing and independently implementing equivalent design ideas; it does not permit copying source files or importing datasets, secrets, customer information, or employer data into this repository. Preserve all pre-existing changes in that checkout. The user has separately authorized using only the GPT-6 Luna API credential from the user's local sentence-validation product to validate this project's optional extraction adapter, with synthetic RFQ inputs only. Never print, log, commit, or otherwise disclose the credential; do not send production/customer RFQ data; keep the credential outside Git and do not inspect or use other credentials from that product folder. Secrets must live outside Git.
- For a future live pilot, agree data retention, deletion, processor/subprocessor usage and human review responsibilities.

## Engineering defaults (provisional)

- Prefer FastAPI, Python, Pydantic, SQLite during local prototype; PostgreSQL only once persistence needs it.
- Frontend can be Next.js + TypeScript; prioritize accessible editable tables over animations.
- Keep parsing, normalization, matching, review state, and export separate and independently testable.
- Use deterministic parsing where source structure is explicit, local OCR only on sparse image-heavy PDF pages, and the configured Luna LLM as a bounded fallback for unresolved/unstructured extraction. Deterministic checks remain the safety gates: schema/type validation, numeric grounding, verbatim source evidence, completeness accounting, and exact manufacturer+MPN catalog matching.
- Model outputs are untrusted JSON and must pass strict schemas, numeric grounding, verbatim provenance checks, and a second LLM consistency pass on LLM-extracted rows. The second pass can only route conflicts, uncertainty, malformed review, or provider failure to an individual human exception; it never certifies or approves a quote. Structured rows do not incur LLM calls unless a required field is missing.
- Version data and schemas; make reprocessing idempotent; never overwrite reviewed values silently.

## Definition of Done for each feature

1. Clear input -> expected output -> failure behavior.
2. Deterministic unit tests and relevant adversarial cases.
3. Manual end-to-end check with synthetic fixtures.
4. Keyboard and accessible UI behavior checked if applicable.
5. Documentation/checkpoint updated **in the same PR**.
6. PR includes truthful verification record and no leaked secrets.

Do not claim customer demand, accuracy percentage, time savings or ROI without real measurements.
