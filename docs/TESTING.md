# Test strategy: trustworthy over flashy

Tests described here are **planned**, not executed. No performance or accuracy claims are established.

## Golden fixture pack

Maintain a synthetic annotated corpus covering:
- Clean 20-line XLSX and multiple-sheet workbook.
- Email with 2 lines, missing manufacturer, and natural-language quantity.
- PDF with repeated table headers, page breaks and footnotes.
- Rotated/scanned PDF with uncertain OCR.
- Same MPN used by two distinct manufacturers.
- Near-identical MPN suffixes: ABC-12, ABC-12A, ABC-12-R2.
- Duplicate item requests split across multiple lines/units.
- Contradictory email vs attached spreadsheet quantities.
- Part described as "equivalent" without engineering documentation.
- Blank quantities, zero/negative quantities and unit ambiguity.
- Headerless CSVs: first record must remain a line item, never mistaken for a header.
- Empty/header-only RFQs and document-level fatal parse errors: block case creation and clean up partially saved files.
- Nonempty quantity with missing MPN and description: preserve as an unresolved review row instead of silently dropping it.
- Catalog duplicate IDs, unknown SKU, stale price, malformed CSV.
- Catalog imports are atomic: any malformed row, duplicate SKU inside an upload, missing OEM/MPN or invalid/nonfinite price or stock quantity rejects the entire import without changing existing catalog matching.
- Malicious spreadsheet formula or macros, prompt-injection PDF content, corrupt/password-protected files.
- Formula-like user/customer/catalog fields in generated CSV and XLSX (including leading whitespace, plus, minus and at-sign); exported text must not execute spreadsheet formulas.
- Zero-line exports must fail even in partial-draft mode.

## Key invariants

1. Every exported row has a corresponding source locator or explicit user-entered origin.
2. System never fabricates a catalog SKU/price/stock/lead time.
3. Cross-manufacturer IDs never auto-approve because of a matching part number alone.
4. Changes made by a human persist through reprocessing.
5. Unresolved required attributes, nonpositive/nonfinite quantities, unknown selected SKUs and high-severity extraction contradictions block a full validated export, **even if the line is marked approved**. Such rows may appear only in prominently labeled partial drafts.
6. Broken files or model errors cannot produce a silent "all clear".
7. No outbound email or order submission exists in v0.
   Unsent customer clarification drafts must never describe an unresolved collision or critical source contradiction as verified, or ask customers to resolve a line that only awaits internal review.
8. No sensitive data appears in test fixtures, telemetry or CI logs.

## Metrics (to measure, not promises)

- **Line recall:** detected true RFQ line items / human-annotated true lines.
- **Critical field exactness:** exact agreement on MPN, manufacturer, quantity and unit for annotated comparable fields.
- **Unflagged critical error count:** wrong quantity/MPN/brand exported as approved without reviewer warning.
- **Source coverage:** proportion of generated rows with valid original page/sheet/row link.
- **Match precision:** correct exact catalog row among candidates / proposals with a selected catalog row.
- **Manual correction burden:** number and duration of corrections per RFQ.
- **Workflow time:** elapsed human work from opening original RFQ to export-ready reviewed draft (manual vs assisted on comparable documents).
- **Abstention quality:** whether ambiguous/unknown rows were actually flagged.

Reported results require fixture count, sample distribution, annotation method, pass criteria and known limitations. Separate synthetic fixture scores from real-client metrics.

## Test layers

**Unit:** parsers, quantity and units, MPN normalization, catalog collisions, export validators, schema constraints.

**Integration:** upload -> parse -> catalog lookup -> human review -> export; ingest failures/retries, permission checks, idempotency and version changes.

The local persistence integration check reconstructs the catalog and case
manager over the same SQLite file and verifies that case fields, corrected line
values, version numbers, audit events, catalog rows, and source files remain
available after the original manager objects are discarded.

**UI:** keyboard-only editing, source navigation, warning notices, export confirmation, empty/loading/error states and prevention of accidental approval.

**Security:** dangerous uploads, oversized sheets, path traversal, prompt injection, tenant isolation, retention/deletion and leaked logs.

**Pilot:** operator-led blind review of historical RFQs with manual baseline and measured corrections. Maintain a holdout set not used for tuning.

## Release blocker examples

- Missing or modified quantity with no warning.
- Unapproved alternative presented as an exact matching part.
- Displayed source snippet does not correspond to underlying file.
- A corrupted file causes a successful zero-line quote without error.
- Export bypasses review state.
- Private RFQ appears in another workspace or public file.

## Evidence required in each PR

Record commands actually executed, test count/results, failed cases, screenshots for UX and remaining risks. "Not run" is acceptable when honest; invented passes are not.
