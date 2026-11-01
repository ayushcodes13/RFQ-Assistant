# UX and visual design blueprint

**Direction (redesigned 2026-11-01):** A clear distributor operations desk: fast, legible, keyboard-first and audit-friendly. Conversational input is a way to give the system source material; it is not an open-ended agent that can silently edit company data.

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
- The persistent sidebar exposes Overview, RFQ inbox, Catalog, and Update data. Line review is a case-specific view, not a second global destination. The sidebar has an accessible desktop collapse control and a mobile menu; every icon-only control has a name and tooltip.
- The logo is a custom RFQ document/check mark; do not use emoji or a generic AI symbol.
- A single primary action appears per screen: New RFQ, Export draft, or Import catalog, depending on context.

## Information architecture

**Navigation:** Overview | RFQ inbox | Catalog | Update data. Exports are generated from a reviewed RFQ; they are not a separate global destination in this slice. Settings are outside the local prototype.

**Top bar:** Current workspace and page context. Product identity and keyboard shortcuts live in the navigation; the local demo and storage notice stays visible in the sidebar.

### Screen 1 — RFQ inbox

- Empty state: explain supported input and point to the single "New RFQ" action.
- Each row: customer label (if provided), source type, upload time, line count, status and unresolved count.
- Show the case ID beside the request title so repeated titles remain distinguishable. Give a compact count of requests needing attention.
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

- Keep a Documents area visible in the workbench. List the original request and every generated draft worksheet, with a way to open/download each. Show extraction warnings and missing generated files beside the list. Refresh after a draft export completes.
- If a requested quantity exceeds the matched catalog row's recorded stock quantity, state both quantities beside the line and require the operator to resolve availability before a validated export. Treat catalog stock as a recorded figure, not live availability.

### Screen 4 — Export preview

- Show all approved rows, unresolved rows count, columns, draft notice, and last review time.
- If unresolved required fields remain, block final-ready export; allow explicit **partial/draft-only** export with omissions visible and traceable.
- Two actions: "Download quote worksheet" and "Copy unsent reply draft".
- No SMTP or email-send button in v0.

### Screen 5 — Catalog import

- Mapping step for uploaded CSV: Internal SKU, Manufacturer, Manufacturer Part Number, Description, optional price/availability timestamp.
- Show validation counts: valid, duplicates, collision, invalid, missing manufacturer.
- Never automatically treat descriptions as equivalent when parts differ.
- The catalog is one distributor's product data. Keep the manufacturer field per catalog item because a distributor may carry multiple manufacturers; do not add manufacturer administration/configuration screens.
- Each item offers Edit and Ask AI. Manual edits and AI suggestions both create a source-backed proposal. The active catalog changes only after the user accepts the proposal in Update data.

### Screen 6 — Update distributor data

- Use a conversation-shaped source intake with a large paste area and file drop/browse control. Say plainly that users can paste a note for configured GPT-6 Luna or upload a structured catalog/reference file; no prompt-writing knowledge is expected. Handle one source at a time so source evidence remains clear.
- Show each processing result as a proposal list grouped by **New**, **Changed**, **Already in catalog**, and **Needs clarification**. A proposal displays current value, proposed value, source evidence and the exact record it would change.
- Each change has explicit Accept and Reject controls. Accept commits only that one validated change and writes an audit event. Reject leaves the current record untouched and keeps the proposal in history.
- A rejected item can be reopened. A plain-language correction box creates a new proposal linked to the original; it never edits an active catalog value directly.
- If source evidence is missing, contradictory, unsupported, or the item identity is ambiguous, disable Accept and explain what is needed.
- Empty/loading/parse/provider/database errors preserve the original source and show a recovery action. Do not show a success state when no proposal was grounded.
- The catalog view retains the browse/search function and offers the source update workflow as the clear adjacent action.

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
- Selecting a document source opens a right-side evidence drawer beside the review workspace, not a centered dialog or a half-page takeover. PDF evidence shows the recorded page and overlays only parser-provided normalized bounds; without bounds it shows the page and extracted snippet without an invented highlight. XLSX and CSV evidence shows a bounded neighborhood around the recorded row and highlights only the recorded source cells (or the target CSV row). The drawer always names the file and location and offers the original source.
- Pasted email/text has line and snippet provenance in the line detail, but no document-citation badge or coordinate drawer. Do not create page/box coordinates for text-only sources.
- Save state without destroying manual corrections when OCR reruns.
- Text accessible to assistive technology, AA contrast target, semantic labels and predictable focus management.
- Confirm destructive actions and make sensitive upload deletion clear.

## Copy rules

Use clear language: "Exact catalog number", "Manufacturer missing", "Possible collision", "Needs human review", "Draft only".

Never use: "100% accurate", "AI verified", "Equivalent certified", "Guaranteed match" without explicit validated standards and evidence.

## Design validation with five real users

Observe whether a sales rep can identify an ambiguous line, fix a quantity, approve an exact MPN, export the correct CSV, and explain what remains their responsibility. Capture task time, clicks, confusion and objections. Visual polish is secondary to accurate action.
