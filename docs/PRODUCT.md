# Product blueprint — what and why

**Status:** hypothesis / intended product behavior. Revised 2026-11-01 to include distributor knowledge updates and grounded quotation preparation. No paid customer or benchmark is claimed.

**Workspace scope:** the current dashboard is an individual operator's workspace for one distributor. That distributor may carry products from many manufacturers, so manufacturer stays on each catalog record as matching context; there is no separate manufacturer administration area in this workflow.

## One-sentence promise

Turn messy buyer requests into **reviewable, source-grounded quote drafts**, and let the distributor stage changes to its own catalog and commercial reference data without overwriting it before human approval.

## Ideal customer (starting hypothesis)

- Independent wholesale distributor of electrical, automation or electronic components, primarily US/UK.
- Typically 5–50 staff (up to 100 if operationally relevant).
- Receives multi-line RFQs or BOMs by email, PDF, spreadsheet, or website form.
- A real inside-sales/quotation operator spends meaningful time turning those requests into quote inputs.
- Company uses a catalog, stock list or ERP and will share sample **authorized** product data for a limited pilot.

**Exclusions:** high-volume self-checkout stores, OEMs selling only their own products, single-item counter sales without document-heavy RFQs, heavy engineered-to-order quoting, and businesses requiring fully autonomous pricing.

## Jobs to be done

- **Inside sales:** "When a customer sends a messy parts list, let me see every requested line in an editable table, identify matches quickly, and keep responsibility for the quote."
- **Sales manager:** "I want fewer overlooked line items and more consistent, measurable throughput, without letting software send unsafe quotes."
- **Owner:** "I want to know whether a small team can process more requests without more clerical work."
- **Customer buyer:** "I want a timely, accurate reply, including honest clarification questions when the request is incomplete."

## What happens before

1. Customer sends unstructured request, sometimes with multiple attachments.
2. A rep opens files, copies 20–100 rows into Excel, separates quantities and units.
3. Rep checks part-number and manufacturer references in item master or websites.
4. Rep asks the customer about ambiguous parts and manually drafts a quote or sends RFQ data to ERP.
5. Mistakes or missing rows may be discovered only after review.

These are **illustrative possible workflows**, not verified facts about any named company. Interviews in docs/VALIDATION.md must establish real baselines.

## What happens with v0

1. Receive the buyer's messy email, pasted text, chat, transcript, PDF, XLSX, or CSV from the distributor; show a clear privacy notice.
2. Create a case with original source files and processing status.
3. Extract every detectable line and source page/sheet/row. Display unknown or conflicting values.
4. Compare *provided* manufacturer part numbers against a customer-authorized catalog CSV using deterministic normalization plus manufacturer context.
5. Show exact match, no match, ambiguous candidate, duplicate and extraction-error states. **Do not rank loose technical substitutes as safe matches**.
6. Operator corrects lines, picks exact known SKU if appropriate, marks non-matches for follow-up, and checks all line items.
7. Retrieve only distributor-authorized catalog and commercial reference evidence for the reviewed request. A bounded LLM may organize a quote proposal from those retrieved records; Pydantic schemas, Decimal arithmetic, deterministic grounding checks, and reviewer actions gate its output.
8. Export a CSV/XLSX quotation-preparation sheet and an **unsent** customer reply draft with clarification questions.
9. Preserve an audit record of edits, knowledge changes, approvals, and rejection/revision history.

## Two operator workflows

### Prepare a buyer's RFQ

The distributor pastes or uploads what the buyer actually sent, even when it is typo-filled, conversational, incomplete, multilingual, or split across files. Extraction proposes JSON fields with source locations. Pydantic validates the structure; deterministic checks verify numeric values, verbatim evidence, completeness, and exact manufacturer plus MPN catalog matches. An optional second model call receives only retrieved distributor records and the extracted request, then proposes a quote draft with evidence references. Pydantic validates the draft shape; Python `Decimal` recomputes line and grand totals; deterministic source checks verify every customer-facing request value against the buyer source and every price/availability/term against the distributor source. Any missing or conflicting evidence stays a reviewer task. Nothing is approved or sent automatically.

### Update distributor data

The distributor can edit a catalog row or upload authorized catalog/reference documents, or paste ordinary text into a conversation-style intake. Plain-language updates use the configured GPT-6 Luna adapter when enabled; structured catalog files use deterministic extraction. The system extracts candidate facts and compares them with current records. It shows additions, unchanged facts, changed values, and conflicts with evidence from the supplied source and current record. Each proposed change remains staged until the distributor accepts or rejects it. Rejected proposals remain visible and can be reopened with a plain-language correction. The active catalog is changed only by an explicit accept action; rejected or unresolved facts do not affect matching or quotations. A request quantity above recorded stock is a human-review blocker; recorded stock is only a catalog value, not a live availability guarantee.

Each RFQ workbench lists its original sources and generated draft worksheets, with download/open actions and visible extraction or missing-file problems. One case can contain pasted buyer email/text plus up to five supported attachments (six source documents total). Each source has its own processing state and provenance; partial failures remain visible and can be retried without discarding successful sources. Duplicate and conflicting requests are preserved for review rather than silently merged. Background ingestion is enabled by default; the isolated local demo launcher uses synchronous ingestion for predictable walkthroughs.

## Non-negotiable safety

A high-confidence visual similarity score is not proof that parts are interchangeable. The tool must never invent missing pricing, stock, warranty, hazardous/material ratings or pressure/electrical specifications. Pricing and lead time are blank unless explicitly supplied and current. An operator must verify each quote line and authorize any substitution.

## v0 deliverables

| Feature | Acceptance |
| --- | --- |
| Intake | Accept at least text, CSV, XLSX, and readable PDF fixtures; invalid files safely rejected |
| Row extraction | Reproduce quantities/units/MPNs with source locator; detect missing/conflicting fields |
| Catalog | Import a small synthetic CSV with approved manufacturer, MPN, internal SKU |
| Matching | Exact MPN+manufacturer matching; report non-match or ambiguous instead of guessing |
| Review | Editable table; row-level resolution; prevent export of unresolved required fields without explicit exception |
| Export | Deterministic schema + clear draft banner; quote price blank when not authorized |
| Audit | Log source file reference, changes, reviewer confirmation and timestamps |

## Not in the current prototype

- Autonomous email sending, inbox access or CRM sequencing.
- Live price calculation, dynamic margin policy, stock or lead-time prediction.
- OEM-certified cross-brand or engineering substitution advice.
- Direct ERP write-back, ordering, payment or procurement.
- General-purpose multi-agent architecture, unrelated RAG pipelines.
- Images of equipment nameplates, CAD parsing and technical configuration.
- Universal coverage of every distributor category.
- Production customer-data hosting before security and retention decisions.

## Future expansions — only if customers ask

1. Optional read-only inbox ingest (explicit customer authorization).
2. Larger manufacturer catalogs and cite-backed cross-reference review.
3. Configurable quote templates and customer-specific formats.
4. Read-only ERP sync with permissioned catalog updates.
5. Quote follow-up and activity reporting.
6. Broader product categories and separate engineering-domain validators.

## Outcome measurement

Measure the **same** historical RFQs with and without the tool. Track line extraction recall, quantity/MPN exactness, missing-line count, reviewer correction count, time to approved draft, number of unresolved clarifications, and operator acceptance. Do not convert time saved into actual payroll savings unless the customer confirms economic effect.

## What proves customers need it?

A direct quote from a buyer describing a repeated problem, observed workflow volume, willingness to provide anonymized test files, a measurable trial benchmark, and ideally a paid pilot. A public RFQ form alone does not qualify as demand proof. See docs/VALIDATION.md.
