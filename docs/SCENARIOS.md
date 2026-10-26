# Scenarios, examples and likely user reactions

All company cases below are **fictional**, for product design/testing. They do not describe verified customers or measured labor savings.

## Scenario 1 — straightforward electrical BOM

**Who:** A 12-person electrical distributor with two inside-sales representatives.

**Inbound:** "Please quote by Thursday" plus a 34-row Excel BOM. Each row has manufacturer, MPN and quantity.

**Before:** The rep copies rows into their house quote sheet and separately searches the item catalog.

**With product:**

1. Drag BOM into the Intake screen.
2. Preview shows "34 candidate lines extracted"; row 18 is missing a quantity.
3. 26 lines have an exact manufacturer+MPN match in the uploaded catalog. Seven have no match. One is unresolved.
4. Rep fills in the missing quantity after asking the buyer, confirms matching entries, and exports a worksheet plus an unsent email draft.

**Happy reaction we hope to earn:** "I no longer need to retype all 34 rows, and I can see which ones need my attention."

**Bad reaction to test:** "I already paste these straight into my ERP; this adds another screen." If repeated, our workflow may not deserve a subscription.

## Scenario 2 — messy email with mixed part numbers

**Who:** Automation component distributor receiving an email body rather than a clean spreadsheet.

**Inbound:** "Need 3 x ABC-123, 4 ABC 124, and the sensor from last time; ASAP."

**Expected behavior:** Parse first two part references and quantities cautiously. Show the last request as **unknown item — clarification needed**; draft: "Could you confirm the sensor manufacturer's part number or send a photo/label?" Do not guess "sensor from last time" or search customer history without permission.

**Desired reaction:** "At least it tells me what it doesn't know."

**Failure reaction:** "It confidently quotes the wrong sensor." This is a stop-ship defect.

## Scenario 3 — same-looking part numbers from different brands

**Who:** Electronic-component distributor sourcing similar MPNs from separate brands.

**Inbound:** A PDF with "XG-42" but no manufacturer.

**Catalog:** Manufacturer A / XG-42; Manufacturer B / XG-42.

**Expected behavior:** Show two candidate exact-number collisions, **blocked for human manufacturer selection**. A partial-text fuzzy score must never automatically choose a manufacturer.

**Desired reaction:** "It didn't hide the ambiguity."

**Failure reaction:** A green badge means the system guessed a brand, potentially causing an incorrect shipment.

## Scenario 4 — contradictory quantities

**Inbound:** Email body says "20 pcs", attached XLSX row says "200 pcs" for the same part.

**Expected behavior:** Display both sources and warning: "Quantity mismatch between message and attachment"; require rep to select the correct quantity or ask buyer. Do not silently take the latest or largest value.

## Scenario 5 — unknown technical equivalent

**Inbound:** Buyer asks for an obsolete breaker model and says "equivalent acceptable if certified".

**Expected behavior:** Mark exact item unavailable in local catalog; allow rep to record a manually verified alternate, with source and explicit approval. The system is **not** authorized to infer electrical rating/fit/certification from generic text similarity.

**Desired reaction:** "It helps me prepare the enquiry without claiming a replacement is safe."

## Scenario 6 — broken or unsafe file

**Inbound:** Password-protected PDF, XLSM containing macros, or PDF with suspicious embedded instructions.

**Expected behavior:** Show "File cannot be safely processed" with specific user-safe guidance. Never run macros, fetch external URLs, obey instructions inside files, or claim all lines were extracted.

## Scenario 7 — export without prices

**Inbound:** 18 clean matched SKUs, but company has not uploaded a price list.

**Expected behavior:** Export a **quotation preparation draft** with price and lead-time fields empty. Never issue a priced quotation by inventing values.

**Expected manager reaction:** "Good—our team still owns the commercial terms."

## Scenario 8 — skeptical owner on a demo

**Buyer:** "My staff already uses Prophet 21 / an ERP. What's new?"

**Demo script:** Show the messy source -> extracted lines -> exact catalog matching -> review log -> ready-to-import CSV. Ask them whether the pre-ERP step is actually costly. If their ERP already handles it, learn, don't argue.

**Possible objections to document:** Data privacy, inaccurate substitutions, duplicate work, setup time, manual review burden, cost, insufficient volumes, and vendor credibility. Each has to be answered through measured evidence, not marketing.

## What a real pilot should learn

- Which input formats dominate?
- What percentage of submitted RFQs contain known MPNs?
- Is parsing slower than chasing suppliers or waiting for customer clarification?
- How often do staff correct the tool?
- Are they willing to route even a subset of real work through it?
- What is the difference between "interesting" and "worth paying for"?

No scenario should be copied into sales content as an actual customer success story.
