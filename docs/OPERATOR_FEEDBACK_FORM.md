# RFQ Assistant operator feedback record

Use one copy of this form for each **authorized, synthetic or appropriately redacted evaluation RFQ**. Keep completed records and customer files in the customer-approved private location; do not commit filled forms, source documents, contact details, prices, or access credentials to this repository.

This form records observations. It does not validate the product, prove accuracy, or establish time savings by itself. Record failures and uncertainty, including when the operator stops or switches back to the manual process.

## Evaluation authorization

- Evaluation reference (non-sensitive ID): `[...]`
- Date and environment/release: `[...]`
- Operator role (no personal name required): `[...]`
- Data class: `SYNTHETIC / AUTHORIZED REDACTED`
- Written data-use authorization confirmed: `YES / NO`
- Agreed scope and component family: `[...]`
- Approved file formats: `[...]`
- Source/ground-truth record location (private link or ID only): `[...]`

**Stop here if authorization or an independent ground-truth source is missing. Do not add the RFQ itself to this record.**

## RFQ and workflow timing

- Number of annotated requested line items: `[...]`
- Number of submitted sources / attachments: `[...]`
- Formats used: `[...]`
- Manual preparation time, minutes: `[...] / NOT MEASURED`
- Assisted active review time, minutes: `[...] / NOT MEASURED`
- Assisted elapsed time from submit to usable draft, minutes: `[...] / NOT MEASURED`
- Waiting time excluded from active review time (for example supplier response): `[...]`
- Number of reviewer corrections: `[...]`
- Reviewer effort per RFQ, minutes: `[...] / NOT MEASURED`
- Did the operator complete the case, stop, or use a manual fallback? `COMPLETED / STOPPED / MANUAL FALLBACK`
- If stopped or fallback, why? `[...]`

Capture manual and assisted time using the same start/end rules, scope, operator familiarity, and input set. Do not subtract supplier waiting time from only one side of the comparison. Keep raw observations; report medians and sample counts across several RFQs before describing a trend.

## Ground-truth comparison

Use a human-checked annotation created independently of the application output. Count an item as correct only when the source supports the value and its locator.

| Measure | Correct / total or count | Notes / evidence reference |
|---|---:|---|
| Source line-item recall | `[...] / [...]` | |
| Manufacturer agreement | `[...] / [...]` | |
| Exact MPN agreement | `[...] / [...]` | |
| Quantity agreement | `[...] / [...]` | |
| Unit agreement | `[...] / [...]` | |
| Exact catalog match agreement | `[...] / [...]` | |
| False exact matches | `[...]` | Include expected and actual match IDs in private evidence only |
| Critical extraction mistakes not flagged for review | `[...]` | Any occurrence is a stop-and-investigate event |
| Duplicate/conflicting line cases correctly surfaced | `[...] / [...]` | State whether quantity, revision, manufacturer, or MPN conflicted |
| Lines with a verifiable source locator | `[...] / [...]` | |
| Lines needing human correction | `[...]` | |

- Were any required lines silently omitted? `YES / NO / UNKNOWN`
- Did an attachment fail or remain partially processed? `YES / NO`
- Did the UI make the failure and recovery path clear? `YES / NO / PARTLY`
- Did any output contain unsupported price, stock, lead-time, substitution, or commercial data? `YES / NO`
- Evidence reference and exact case/line references (private, non-sensitive IDs only): `[...]`

## Operator experience

- Which step took the most effort? `INTAKE / SOURCE CHECK / CORRECTIONS / MATCH REVIEW / EXCEPTIONS / EXPORT / OTHER: [...]`
- Which information was difficult to verify? `[...]`
- Which warning was unclear, late, or missing? `[...]`
- Did source evidence let you find the value in the original file? `YES / NO / PARTLY`
- Did the draft worksheet fit the existing process? `YES / NO / PARTLY`
- What did the operator do outside the app to finish the task? `[...]`
- Most useful change before another evaluation: `[...]`
- Other comments (no RFQ text or personal data): `[...]`

## Disposition

- Critical unflagged error occurred: `YES / NO`
- Continue, narrow, or stop evaluation: `CONTINUE / NARROW / STOP`
- Reason and owner of follow-up: `[...]`
- Re-test required before further use: `YES / NO`
- Reviewer sign-off/reference in the approved private system: `[...]`

A single successful RFQ is not an accuracy claim. Keep customer results clearly separate from synthetic fixtures and record the number and type of RFQs behind every summary. Do not share a result externally until its sample, method, limitations, and customer approval have been reviewed.
