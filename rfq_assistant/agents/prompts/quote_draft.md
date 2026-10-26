Given:
- validated RFQ lines,
- approved catalogue matches,
- authoritative inventory results,
- authoritative pricing results,
- customer-specific commercial policy,
construct a PROPOSED quotation draft.

Do not invent missing commercial data.
Do not change the requested MPN.
Do not replace an item with an alternate unless alternate_approved=true.
Keep unavailable/unpriced items visible as exceptions.

For each line include:
- requested item
- quoted catalogue item
- requested quantity
- available quantity
- unit price
- currency
- source price ID
- lead time / availability source
- exception notes

Then produce a concise customer-facing email draft. The email is not authorised to send.
