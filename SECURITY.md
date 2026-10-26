# Security and responsible handling

**Current state:** Documentation only; no production security assurance is implied.

## What may be sensitive

RFQ files can contain names, email addresses, purchase quantities, customer pricing, addresses, bills of materials, supplier relationships and business-confidential project specifications. Treat all as private even when part numbers themselves are publicly listed.

## Rules for development

- Use fabricated, clearly labeled synthetic RFQs and catalogs in source control and demos.
- Never commit passwords, tokens, production sample RFQs, customer contacts or sales prospect lists.
- Validate uploads, cap sizes and parse time, never execute spreadsheet macros or document-embedded scripts.
- Do not obey instructions embedded in emails or documents as operational commands.
- Default to no outbound network requests from parsing; disclose external AI processors before using them on private customer data.
- No autonomous quotation transmission or purchasing actions.
- Require explicit human approval and visible source evidence.
- Keep customer records tenant-scoped and ensure deletion works before a production pilot.
- Do not use company/employer intellectual property, data or accounts without permission.

## Pilot API-key configuration

The API must not rely on hard-coded, publicly known credentials. There are **no built-in
pilot keys**. Authentication is disabled only for an explicitly local, synthetic demo;
do not expose that mode to other machines or the internet.

For a protected deployment, set `REQUIRE_AUTH=true` and configure `PILOT_API_KEYS`
outside the repository. The format is a comma-separated list of
`<random-secret-key>:<admin|reviewer|viewer>:<display-name>`; each secret must
be at least 16 characters and should be generated with a cryptographically
secure random generator (prefer substantially longer random secrets).
Never store real credentials in screenshots, issues, CI logs, or committed files.

With `REQUIRE_AUTH=true`, missing keys reject API access (503) rather than
falling back to test credentials. Malformed, duplicate, weak or invalid-role
entries also reject the configuration. Rotate and revoke keys after any
exposure. API keys are a limited pilot boundary, **not** tenant isolation,
session management, HTTPS termination, or production-grade identity.
The current browser prototype is not an authenticated enterprise workspace.

## Before pilot deployment

Document authentication, access control, encryption, environment separation, data residency, subprocessors, retention, deletion, backup, logging minimization, incident response, permission to process customer data and how a quote is approved. Make contractual scope clear: the software is a **preparation assistant**, not an engineering certification or price authority.

## Reporting vulnerabilities

Do not put sensitive exploit details or live customer files in public issues. Contact the maintainer through a private channel agreed by repository owner. An official security policy and disclosure address can be added once the project is operational.
