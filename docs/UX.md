# UX and visual design blueprint

**Direction (redesigned 2026-10-31):** A clear RFQ operations desk: fast, legible, keyboard-first and audit-friendly. Not a chat playground, animated agent dashboard or neon AI demo.

## Product landing page

- The root route (`/`) is one continuous marketing page for independent industrial component distributors; `/workspace` opens the actual local product.
- Visual direction: cinematic, editorial imagery and large display type with deliberate section changes; graphite and cool paper tones with the existing copper accent.
- Show the real workflow in readable interface fragments: intake, line review, exact catalog matching, and draft preparation. The interactive example is clearly labeled as illustrative data.
- Product images are generated industrial scenes and must remain labeled as illustrative, not customer locations or results.
- Claims stay within the product blueprint. No customer logos, testimonials, accuracy/time-saved metrics, fabricated catalog evidence, autonomous quotes, or substitution claims.
- Primary CTA is "Open workspace". Do not collect an email or imply a sales/contact workflow that is not implemented.
- Motion demonstrates the workflow and reveals imagery; it must remain subtle, use transform/opacity or one-time image masking, and honor reduced-motion preferences.

## Design personality

- Cool metal-tint frame around a white work sheet, near-black primary text, and a distinct copper accent used for the product mark, primary action and key data only.
- IBM Plex Sans for interface text and IBM Plex Mono for IDs and tabular values; both bundled locally.
- Status uses label + icon + color, never color alone.
- Dense but readable tables with sticky headers, clear typography and column alignment.
- Optimized for desktop sales desks (1440px viewport); tablet navigation collapses and the phone uses a menu sheet and stacked list rows.
- No charts, scores or decorative AI imagery on the critical quote-review screen.

### Operations overview

- The initial screen answers: **which RFQs need a person now?**
- Summary values and status bars come directly from saved cases and unresolved-line counts. Do not show sales, revenue, price, availability, lead-time or accuracy figures unless their source is authorized and current.
- Show a short actionable attention queue and a breakdown by actual workflow state. Link to the full RFQ inbox for search and filtering.
- The persistent sidebar exposes only Overview, RFQ inbox and Catalog. Line review is a case-specific view, not a second global destination.
- The logo is a custom RFQ document/check mark; do not use emoji or a generic AI symbol.
- A single primary action appears per screen: New RFQ, Export draft, or Import catalog, depending on context.

## Information architecture

**Navigation:** Overview | RFQ inbox | Catalog. Exports are generated from a reviewed RFQ; they are not a separate global destination in this slice. Settings are outside the local prototype.

**Top bar:** Current workspace and page context. Product identity and keyboard shortcuts live in the navigation; the local demo and storage notice stays visible in the sidebar.

### Screen 1 — RFQ inbox

- Empty state: explain supported input and point to the single "New RFQ" action.
- Each row: customer label (if provided), source type, upload time, line count, status and unresolved count.
- Status: New, Processing, Needs review, Ready to export, Exported, Failed.
- Primary CTA: "New RFQ"; never "Send quote" on this screen.

### Screen 2 — Create RFQ

    +-------------------------------------------------------+
    | New RFQ                                               |
    |                                                       |
    | [ Drop PDF / XLSX / CSV here ]  or [ Paste email ]      |
    | Max size / file-type rules and processing notice      |
    |                                                       |
    | [Optional case title]  [Select sample catalog]        |
    |                                                       |
    |                    [Cancel] [Extract line items]       |
    +-------------------------------------------------------+

Before upload, provide a clear notice about local storage and how third-party processors would handle data if they are introduced.

### Screen 3 — Review workbench (core product)

    +---------------------------------------------------------------------+
    | RFQ #DEMO-007  Needs review  |  34 lines / 8 unresolved | Export [X]  |
    +---------------------------+-----------------------------------------+
    | ORIGINAL SOURCE           | QUOTATION PREPARATION                   |
    | PDF p2 / Sheet Items 18   | Filters: All Exact Ambiguous Missing    |
    |                           +-----------------------------------------+
    | Highlighted row / text    |  #  Qty  OEM   MPN     Match     Status |
    | source preview            |  1  10   ACME  A-123   SKU-501   Exact  |
    |                           |  2   ?   ...   B-244   --        Fix    |
    |                           |  3   4   --    XG-42   2 options Review |
    |                           +-----------------------------------------+
    | Source document pages     | Selected line: editable attributes      |
    |                           | Candidate catalog match + evidence      |
    |                           | [Approve] [Mark needs clarification]     |
    +---------------------------+-----------------------------------------+
    | Warnings  Audit history  Keyboard shortcuts  Last saved             |
    +---------------------------------------------------------------------+

**Review behavior:** Clicking a grid row scrolls source to its exact page/sheet/line; clicking source locators focuses the row. Edits are staged and audited. Bulk approve may be offered only for deterministic exact matches after the reviewer explicitly checks the visible set. Missing quantity/manufacturer and all substitution candidates must not be silently bulk approved.

### Screen 4 — Export preview

- Show all approved rows, unresolved rows count, columns, draft notice, and last review time.
- If unresolved required fields remain, block final-ready export; allow explicit **partial/draft-only** export with omissions visible and traceable.
- Two actions: "Download quote worksheet" and "Copy unsent reply draft".
- No SMTP or email-send button in v0.

### Screen 5 — Catalog import

- Mapping step for uploaded CSV: Internal SKU, Manufacturer, Manufacturer Part Number, Description, optional price/availability timestamp.
- Show validation counts: valid, duplicates, collision, invalid, missing manufacturer.
- Never automatically treat descriptions as equivalent when parts differ.

## UI states to implement carefully

| State | Visible behavior |
| --- | --- |
| Uploading | Determinate progress where available; clear cancel |
| Processing | Steps shown as plain language, no fake progress countdown |
| Extraction partial | "We may have missed lines"; explicit page/sheet warnings |
| Exact match | Manufacturer + normalized MPN + catalog row source |
| Multiple exact candidates | "Needs review" with all ambiguous rows |
| No match | No invented SKU; suggest manually adding/catalog lookup |
| Empty/unreadable PDF | Specific failure and try-another-file route |
| Source unavailable | Block unverified claim and surface original file issue |
| Export success | Download link, included/excluded line summary |
| Server failure | Error visible; user-entered edits preserved where feasible |

## Interaction details

- Keyboard: Tab navigation through cells; Enter commits edit; Escape cancels; Ctrl/Cmd+F searches extracted rows; shortcuts documented, no conflicts with screen readers.
- Source document must be readable, zoomable and selectable; if highlight coordinates unavailable, display page number and extracted text without pretending bounding boxes exist.
- Save state without destroying manual corrections when OCR reruns.
- Text accessible to assistive technology, AA contrast target, semantic labels and predictable focus management.
- Confirm destructive actions and make sensitive upload deletion clear.

## Copy rules

Use clear language: "Exact catalog number", "Manufacturer missing", "Possible collision", "Needs human review", "Draft only".

Never use: "100% accurate", "AI verified", "Equivalent certified", "Guaranteed match" without explicit validated standards and evidence.

## Design validation with five real users

Observe whether a sales rep can identify an ambiguous line, fix a quantity, approve an exact MPN, export the correct CSV, and explain what remains their responsibility. Capture task time, clicks, confusion and objections. Visual polish is secondary to accurate action.
