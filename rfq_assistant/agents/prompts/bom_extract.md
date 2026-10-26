Task: map this document into RFQ line items.
For each logical line:
- original line identifier
- raw manufacturer
- raw manufacturer part number
- customer/internal part number, if explicitly labelled
- raw description
- quantity
- unit
- requested delivery date, if line-specific
- notes
- provenance

Do not combine rows merely because descriptions look similar.
Do not split a single wrapped row merely because it spans text lines.
Do not remove leading zeroes from part numbers.
Do not convert part numbers to numbers.
Do not infer quantity from packaging or description text unless the source explicitly defines that relationship.
