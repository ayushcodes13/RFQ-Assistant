# Human-input test matrix

This suite is intended to exercise the request intake as real people use it: the input may be a document, a fragment of conversation, a transcript, a correction, or too little information. A passing case means the system preserves the source and either produces grounded fields or an explicit review/error state. It does not mean the software understands every buyer or is production-ready.

| ID | Input kind | Synthetic example shape | Required behavior |
| --- | --- | --- | --- |
| H01 | Rambling email with typos | `hey can u quote 4 of the phoenix 2900364 power thing? need it next month` | Preserve the quantity and MPN only if verbatim-grounded; flag missing details; ignore delivery date for catalog matching. |
| H02 | Chat shorthand | `need 2 6ES7134-6GD01-0BA1 + 5 of same relay as last time` | Keep the known part and quantity; do not guess what “same relay” means; request clarification for that line. |
| H03 | Forwarded thread with correction | Earlier message asks for 8; later buyer message says “Correction: make that 3” | Keep both source regions and mark the conflict/revision for reviewer resolution; never silently choose by line order. |
| H04 | Dictation transcript | `uh four, no sorry fourteen, Siemens six ES seven one three four...` | Preserve uncertain transcription and numeric conflict as reviewer work; do not clean up a part number from phonetics without evidence. |
| H05 | Mixed English/Hinglish note | Natural-language item details plus a Hindi/English delivery aside | Extract only schema-supported values that can be grounded; retain unsupported text and surface unknown fields. |
| H06 | Generic buyer RFQ template | Addresses, deadline, warranty/tax terms, and product/service description without manufacturer MPN | Do not treat it as a catalog-ready parts list; retain it and show an explicit no-usable-line/manual-review outcome. |
| H07 | Spreadsheet with title rows and unusual headers | Existing synthetic `xlsx_title_then_header.xlsx` plus alternate-header fixtures | Preserve all item rows and workbook source locators; unknown columns do not become invented product facts. |
| H08 | Loose CSV / pasted ERP export | Headerless or extra-column catalog/BOM content | Keep the first row as data where headers are absent; report uncertain column mapping and avoid importing distributor changes until accepted. |
| H09 | Native PDF with wrapped rows and footnotes | Existing synthetic wrapped/multipage PDF fixtures | Preserve page and text provenance; avoid merging footnotes into MPN or quantity fields. |
| H10 | Image-only/scanned PDF or broken attachment | Existing scanned fixture and corrupt/password-protected fixtures | OCR-disabled/unavailable, corrupt, or encrypted inputs produce explicit blocking state; never report an empty successful quote. |

## Data-update actions to run for each applicable case

1. Stage the proposed distributor fact without changing the active catalog.
2. Check identity matching by internal SKU, otherwise exact manufacturer+MPN. A duplicate or ambiguous identity is a conflict, not an overwrite.
3. Verify every proposed field against the uploaded/pasted distributor source and show the current value beside the proposed value.
4. Accept only the selected, complete proposal; verify catalog version changes and an audit event is written.
5. Reject another proposal; verify the active catalog is byte-for-byte unchanged and rejection remains visible.
6. Reopen a rejected proposal with a correction; verify the new proposal references the earlier one and does not mutate the active record before explicit acceptance.

## Quote-stage checks

- Distributor retrieval uses approved source records and emits stable source IDs/locators.
- Every price, stock/availability value, and commercial term cites a distributor source; every requested item/quantity cites the buyer source.
- Pydantic rejects malformed model output; deterministic grounding rejects non-verbatim evidence and source-ID mismatch.
- Decimal line and grand totals are recomputed independently. A conflicting model-supplied total blocks export and is shown for review.
- A clean model response never approves or sends a quotation.

Local execution on 2026-11-01: `pytest -q tests/test_human_input_matrix.py` passed **11 tests**. This includes ten source shapes (six conversational inputs and four file-layout cases) and a combined case-intake pass that verifies source retention plus either parsed lines, visible warnings, or explicit failure. The ten shapes are synthetic and run without a live model; this is not evidence of customer accuracy or the live GPT-6 Luna path. It also does not cover a full UI quote approval/export run for each source shape. The matrix is executable locally; hosted CI status must be checked separately.
