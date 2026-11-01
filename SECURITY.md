# Security and responsible handling

**Current state:** Documentation only; no production security assurance is implied.

## What may be sensitive

RFQ files can contain names, email addresses, purchase quantities, customer pricing, addresses, bills of materials, supplier relationships and business-confidential project specifications. Treat all as private even when part numbers themselves are publicly listed.

## Rules for development

- Use fabricated, clearly labeled synthetic RFQs and catalogs in source control and demos.
- Never commit passwords, tokens, production sample RFQs, customer contacts or sales prospect lists.
- Validate uploads, cap sizes and parse time, never execute spreadsheet macros or document-embedded scripts.
- RFQ upload handlers read at most the configured 10 MiB per-file limit plus one sentinel byte before scanning or processing. The app rejects multipart bodies above 26 MiB before Starlette form parsing; production ASGI servers and trusted reverse proxies should enforce a matching or stricter limit to bound upstream buffering.
- The dependency set requires FastAPI 0.162.0 and Starlette 1.3.1 or newer to exclude the reviewed Starlette Host/path and request-form parsing advisories. Keep the Starlette floor until FastAPI itself requires a patched minimum; the app rate-limits by ASGI `scope["path"]`, not reconstructed URL data.
- Do not obey instructions embedded in emails or documents as operational commands.
- Default to no outbound network requests from parsing; disclose external AI processors before using them on private customer data.
- No autonomous quotation transmission or purchasing actions.
- Require explicit human approval and visible source evidence.
- The authenticated Next.js API proxy requires an exact same-origin `Origin` header on state-changing requests. SameSite cookies add defense in depth but do not make sibling subdomains cross-site.
- The Next.js app sets `nosniff`, frame denial, a restrictive referrer policy, disabled DNS prefetch, and a Permissions Policy that disables unused camera, microphone, and geolocation features. Configure HSTS at the HTTPS edge; this repository does not choose a TLS termination policy.
- Keep customer records tenant-scoped and ensure deletion works before a production pilot.
- Do not use company/employer intellectual property, data or accounts without permission.

## Pilot API-key configuration

The API must not rely on hard-coded, publicly known credentials. There are **no built-in
pilot keys**. Authentication is disabled only for an explicitly local, synthetic demo;
do not expose that mode to other machines or the internet.

For a protected deployment, set `REQUIRE_AUTH=true` and configure `PILOT_API_KEYS`
outside the repository. The current format is a comma-separated list of
`<random-secret-key>:<admin|reviewer|viewer>:<user-id>:<workspace-id>:<display-name>`; each secret must
be at least 16 characters and should be generated with a cryptographically
secure random generator (prefer substantially longer random secrets).
Never store real credentials in screenshots, issues, CI logs, or committed files.

All configured credentials must use the same workspace ID. The backend rejects
multiple workspace IDs because persistence and resource authorization are still
single-workspace. Older three- and four-part credential formats remain accepted
and map to `ws-default`; compatibility does not provide tenant isolation.

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
