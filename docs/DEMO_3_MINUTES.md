# Three-minute RFQ Assistant buyer demo

**Status:** reproducible presenter runbook for the existing local prototype. This is **not** a screen recording, a hosted deployment, a measured customer success story, or evidence of extraction accuracy. All input data is synthetic. Run the preflight before presenting.

## Outcome we want the buyer to judge

Show the proposed **pre-ERP quotation preparation step**: incoming RFQ file or email -> extracted lines with source evidence -> exact-catalog matching and visible exceptions -> human review -> **draft** worksheet. Ask whether that step is genuinely painful in the buyer's existing process. Do not position this as an autonomous quoting engine.

### Preflight, 10-15 minutes before the meeting

1. Clone and open this repository on an isolated machine. **No real customer, employer or personal production data**.
2. Start backend from repository root:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   pytest -v
   uvicorn rfq_assistant.api.app:app --host 127.0.0.1 --port 8000
   ```
3. Start frontend in a separate terminal:
   ```bash
   cd frontend
   npm install
   npm run build
   npm run dev
   ```
4. Open `http://localhost:3000`. Confirm the **Cases Inbox**, **New RFQ Intake**, review workbench, **Audit Log** and **Export Quotation Worksheet** work.
5. Confirm the sample catalog is available at `fixtures/catalogs/industrial_components_sample_catalog.csv` (the README says the backend loads it locally).
6. Stage **two or three separate synthetic cases** before recording:
   - Upload `fixtures/rfq_samples/industrial_control_bom_20lines.xlsx` to demonstrate **file upload and parsing**.
   - Paste the contents of `fixtures/rfq_samples/messy_email_quote_request.txt` into **Paste Email / Parts List** to demonstrate **an unspecified sensor** and review warnings.
   - Optionally paste `fixtures/rfq_samples/cross_brand_collision.txt` to demonstrate **XG-42 manufacturer ambiguity**. Confirm actual behavior before claiming it appears. Use `fixtures/ground_truth/annotations.json` for fixture expectations.
7. Leave **unresolved rows unapproved**. Preview the export modal and make sure draft versus final behavior matches the current build. Do not make up per-row extraction counts, hit rates or warnings: speak only about what the local app actually shows.
8. Check that the screen share has no Gmail, CRM, Apollo, Hunter, customer identities, secrets, or employer material visible. Turn off notifications.

### Live demo: 3:00 total

| Time | Presenter action in the actual app | Narration / buyer value |
| --- | --- | --- |
| **0:00-0:25** | Open **Cases Inbox**. Click **New RFQ Intake**, choose **Upload File**, select `industrial_control_bom_20lines.xlsx`, add a synthetic case title, submit. | "This starts where your quote requests arrive: a spreadsheet or PDF, or an email body. Instead of auto-quoting, we first make a working sheet that a salesperson can check." |
| **0:25-0:55** | Open the new **Review Workbench**. Click one extracted row. Show **Original Source Evidence**, sheet/row locator and text snippet next to the line grid. | "The rep can see exactly which source line the part number and quantity came from. We want to catch errors before they reach pricing." |
| **0:55-1:25** | Switch to pre-staged messy-email case and use **Action Required**. Select its unresolved item from "the sensor from last time" (or whatever the current parser shows). If the ambiguous item was not captured, state this as a limitation rather than simulate a warning. | "This is the important failure mode. A mention without an exact manufacturer or part number is not permission to guess a product." |
| **1:25-1:50** | If verified in preflight, open pre-staged `cross_brand_collision.txt` and highlight XG-42. Otherwise stay on the messy-email case and show whatever missing fields and review decisions are actually present. | "Even an identical part number can belong to multiple brands. We keep that for human resolution instead of choosing a plausible substitute." |
| **1:50-2:20** | In the workbench, select a known row. Show editable quantity and its **source snippet**, then review action controls and **Audit Log**. Do **not** change a real/ambiguous quantity to a guess. | "A salesperson can correct and approve data. The review log records who changed what; the software does not approve technical equivalence or customer pricing." |
| **2:20-2:45** | Click **Export Quotation Worksheet**. Show that unresolved lines block a clean validated export; if appropriate, select **Allow Partial Draft Export** and demonstrate XLSX or CSV download. | "The result is a clearly labeled preparation draft, not an issued quote. Prices and lead times remain your team's responsibility." |
| **2:45-3:00** | Point to **Unsent Customer Clarification Draft**, then close the modal. | "Does your team already have a better way to handle this pre-ERP cleanup, or would a 5-10 RFQ pilot be worth testing?" |

### Operator notes and safety

- The **Upload File** UI supports native PDF, XLSX, CSV and text. Do not claim scanned PDFs/OCR are fully supported unless independently tested; the repo describes deterministic extraction first.
- The current `ExportModal` computes its unresolved banner from case summary props; after editing/approving rows, **return to Cases Inbox and reopen the case** before relying on the banner. The backend export validation is the authority.
- Do **not** press "Approve Exact Matches" until a human has actually checked those lines, even for fictional fixtures. Batch approval is available, but not mandatory for this three-minute demo.
- The sample is a **quotation preparation draft**. The app has no outbound quote-sending action. Never claim live ERP integration, customer rollout, automatic supplier pricing, measured efficiency, or exact extraction accuracy.
- If a step fails during the demo, show the failure and explain the limitation. Do not use edited screenshots, staged values masquerading as live output, or invented source pinpoints.
- Never put prospective customers' real BOMs into the public repository. Any pilot using their files needs an explicit data-use/retention agreement and redaction or authorized environment.

### Buyer conversation immediately after the demo

Ask these, in order:

1. "How does an RFQ arrive today: XLSX, PDF, email, supplier portal, or your ERP?"
2. "Which part actually takes effort: cleaning line items, confirming part numbers, checking availability, negotiating price, or something else?"
3. "Would a 5-10 **redacted or synthetic** request comparison against your current process give us a meaningful answer?"
4. "Who owns quotation intake and could judge the output with us?"

**Offer:** a **scoped, evaluation-only pilot**, not a free production integration. Start with 5-10 redacted/synthetic RFQs, one component family and the buyer's own empty quote worksheet template. Produce a readout of missing fields, wrong/unflagged MPNs, reviewer edits and the team's qualitative feedback. Agree scope, price, privacy and measurement plan before touching live documents. Do not promise fixed time savings.

### Pilot scorecard, to fill with actual evidence later

| Metric | How measured | Baseline | Assisted | Status |
| --- | --- | --- | --- | --- |
| Input format / line count | Count true RFQ line items in agreed fixtures | Not measured | Not measured | Pending |
| Exact MPN/manufacturer/quantity agreement | Human-ground-truth comparisons per field | Not measured | Not measured | Pending |
| Unflagged critical mistakes | Wrong critical fields without a warning | Not measured | Not measured | Pending |
| Source locator coverage | Exported line items with valid origin | Not measured | Not measured | Pending |
| Human corrections | Count and time of reviewer edits | Not measured | Not measured | Pending |
| Pre-quote preparation time | Matched manual vs assisted runs, excluding supplier waiting | Not measured | Not measured | Pending |

Stop or narrow scope if unflagged critical mistakes occur. No invented ROI percentage or unsupported claim of "faster quotes."

### Recording checklist

- Start with title card: **RFQ Assistant | Synthetic quotation preparation example**.
- Record at 1080p with legible row text; include the warning/clarification moment.
- Trim to around three minutes only after confirming the unedited live app walkthrough works.
- Use a representative fixture, not a customer file.
- Add final caption: **Early-stage prototype. Human-reviewed draft only. No live prices or suppliers.**
- Review the recording for real names, customer data and unsupported product claims before sharing.

### Run verification

This runbook was written after reading the repository README, `AGENTS.md`, `docs/SCENARIOS.md`, `docs/TESTING.md`, and UI source components (`IngestModal`, `WorkbenchView`, `ExportModal`). **The application and tests were not executed in this documentation PR** because the connected environment does not provide the repository checkout or a working local browser. The presenter must execute the preflight and record actual results before representing the demo as tested.
