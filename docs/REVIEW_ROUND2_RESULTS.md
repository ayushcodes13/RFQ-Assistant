# Review Round 2 remediation results

This table tracks the ordered work from the round-2 remediation brief. Only outputs
actually observed are recorded. `Pending` means the finding has not yet been reproduced
and fixed in its own PR.

| Finding | PR branch | Reproduction before | Reproduction after | Regression test | Gate status |
| --- | --- | --- | --- | --- | --- |
| P0-1 auth flag, key comparison, startup configuration | `fix/auth-flag-parsing` | Live isolated backend: `REQUIRE_AUTH=yes` with a configured synthetic key and no request key returned `200 []`; `REQUIRE_AUTH=true` returned `401`. | Live isolated backend: `REQUIRE_AUTH=yes` returned `401` anonymously and `200` with the configured key. Malformed `PILOT_API_KEYS` caused startup to exit with `Invalid pilot authentication configuration: Malformed PILOT_API_KEYS entry.` | `tests/test_auth_flag_parsing.py` covers yes/on aliases, demo fallback, startup cache, constant-time comparisons, malformed startup configuration and the warning when keys are configured while auth is disabled. | Merged as PR #48; hosted CI and CodeQL passed. |
| P0-2 batch concurrency and no-op version bump | `fix/batch-review-versions` | Live isolated backend: after a row changed from v1 to v2, stale `POST /review` returned `200` and approved it; stale `approve-remaining` returned `200` and approved 7 rows; no-op PATCH advanced v1 to v2. | Live isolated backend: stale `POST /review` returned `409` and left decision PENDING at v2; stale `approve-remaining` returned `409` and approved 0 remaining rows; no-op PATCH stayed v2. | `tests/test_batch_review_concurrency.py` covers both stale endpoint conflicts, no partial approval, unchanged no-op version/audit; `tests/test_review_sampling.py` retains successful sample and remainder workflow. | Local full gate passed: 451 pytest; evaluator 20/20 lines, 80/80 critical fields and 20/20 matches; corpus 30/30 flows, 180/180 critical fields and 128/128 concurrent IDs; frontend lint/typecheck/build; Playwright 11/11. Hosted CI pending. |
| P0-3/P0-4 list response shaping and sanitized API errors | Pending | Pending | Pending | Pending | Pending |
| P1-5 export pricing gate | Pending | Pending | Pending | Pending | Pending |
| P1-6/P1-7 warning lifecycle and audit events | Pending | Pending | Pending | Pending | Pending |
| P1-8 workbench UOM editing | Pending | Pending | Pending | Pending | Pending |
| P2-11 email draft numbering and truncation | Pending | Pending | Pending | Pending | Pending |
| P2-9/P2-10 demo runbook accuracy | Pending | Pending | Pending | Pending | Pending |
| P3-12..18 hardening and hygiene | Pending | Pending | Pending | Pending | Pending |

## P0-1 local verification

- Full Python suite: 448 passed, 7 deprecation warnings.
- Synthetic evaluator: 20/20 lines, 80/80 critical-field checks, 20/20 catalog-match checks.
- Synthetic API corpus: 30/30 full flows, 180/180 critical-field checks, 128/128 concurrent IDs.
- Frontend lint, generated type check, production build, and isolated Playwright: 11/11.
- No customer or personal RFQ data used.
