# Workspace Isolation Design

Status: design contract only. The application remains a single-workspace service. Do not configure unrelated distributors in one deployment or database until the implementation and adversarial tests below are complete.

## Boundary

An authenticated principal belongs to exactly one server-configured workspace. `workspace_id` is resolved from the validated credential/session at the API boundary; it is never accepted from a request body, query string, or browser-controlled header. Roles remain scoped to that principal's workspace (`admin`, `reviewer`, `viewer`). Missing identity, missing workspace, or mismatched ownership fails closed. Unknown and foreign-owned object IDs return the same not-found response so the API does not disclose whether another workspace owns a record.

The anonymous local demo principal maps to one fixed local workspace. It must not be combined with protected customer traffic or exposed as an internet service. Until the whole boundary is implemented, protected deployment remains one isolated instance, database, storage root, and worker pool per customer.

## Ownership model

Every durable or file-backed object is owned by a workspace directly or through an immutable parent relationship:

| Resource | Ownership rule | Required access path |
| --- | --- | --- |
| RFQ case and source documents | Direct `workspace_id` on the case and each source document; source digest and filename are not authorization keys | Case lookup/list/create/delete is scoped before returning data or filesystem paths |
| RFQ lines, provenance, review decisions, audit events | Inherit case ownership and carry a workspace key for database constraints | Composite parent reference `(workspace_id, case_id)`; writes verify both |
| Ingestion jobs and processing artifacts | Same workspace and case as the parent; workspace captured at enqueue | Worker claim, retry, artifact read/write, heartbeat and final lease-fenced commit verify ownership |
| Catalog, catalog snapshots and catalog update proposals | Direct workspace ownership; proposal source object belongs to the same workspace | Every list, match, import, stage, accept/reject/reopen and source preview is scoped |
| Export manifests and files | Same workspace and case; file path is derived from trusted server-side workspace and case IDs | List, generate, download and delete resolve the manifest after scoped case authorization |
| Quote drafts and quote evidence | Same workspace and case; source IDs may reference only same-workspace RFQ/catalog records | Retrieval, stale-source check, approval and rejection are scoped before processing |
| Session, cache and rate-limit state | Authenticated user/workspace or trusted deployment boundary | Never key security decisions only by a caller-provided object ID |

Catalog matches must use the authenticated workspace's active catalog snapshot. A catalog row from another workspace may not influence candidates, collision results, prices, stock values, or quote evidence.

## SQLite migration contract

1. Add an explicit schema version and transactional, restartable migration. Do not infer or merge workspaces from display names, user IDs, catalog contents, or filenames.
2. Existing single-workspace records migrate together into one deterministic legacy workspace ID supplied by deployment configuration. Migration must inventory rows and files before/after and abort on orphaned records, conflicting ownership, or an unknown schema version.
3. Do not enable multi-workspace mode as a side effect of migration. Until all tables, files, endpoints, background work and tests are scoped, startup rejects a configuration containing credentials from more than one workspace.
4. Use workspace-scoped primary/unique keys and foreign keys where the SQLite schema permits them. Add an index for each common `(workspace_id, resource_id)` lookup. Verify `PRAGMA foreign_keys=ON` on every connection.
5. Migration rollback restores the prior database from a verified backup. File migration is staged by workspace, verified with hashes, and atomically switched only after every required object is present. Never delete the original until verification succeeds.
6. Reprocessing and retry are idempotent within the same workspace. A job or idempotency key from another workspace cannot attach to, replace, or reveal an existing case.

## API and worker contract

Resolve identity once in the authentication dependency and pass an immutable workspace context into every service and persistence operation. Do not rely on route-level authorization alone: scoped lookups must happen before source paths, catalog candidates, export manifests, or audit data are read. All case routes, catalog and update routes, commercial quote routes, upload/source previews, and downloads require explicit review against this rule.

The worker receives `(workspace_id, case_id, source_digest)` from trusted persisted job data. It verifies case ownership when claiming and before every artifact read/write or final snapshot commit. A stale lease or workspace mismatch cannot commit. Logs and metrics use opaque workspace identifiers and must not contain RFQ text, prices, keys, or customer identities.

## Adversarial acceptance tests

Use two synthetic workspaces with deliberately overlapping-looking IDs and different catalogs. Assert that Workspace A cannot:

- read or list B's case, lines, audit, review plan, source bytes, PDF page, spreadsheet preview, clarification draft, quote, export list, manifest, or download;
- edit, rematch, approve, reject, delete, or export B's case or line;
- list, import over, stage, accept/reject/reopen, preview, or match against B's catalog/update proposal;
- cause an ingestion job, retry, cache artifact, quote source check, or export operation to process B's data;
- gain admin/reviewer rights by changing a request actor, role, workspace ID, cookie, URL, or guessed object ID.

For each resource, exercise list, read, create, update, delete, retry, and download where supported. Verify denial has no observable side effect, does not alter audit state, does not enqueue work, and returns no foreign metadata. Also test the inverse direction, same-workspace success for each role, no-workspace and invalid-credential rejection, migration from a populated legacy database, interrupted/repeated migration, orphan detection, and recovery from backup. Run the same access tests through API routes and service/persistence entry points so a future internal caller cannot bypass the boundary.

## Go-live gate

Shared multi-workspace mode remains off until every ownership row and API path is implemented, migration and rollback are exercised on synthetic snapshots, the two-workspace adversarial matrix passes, worker crash/retry isolation is verified, file deletion/retention is demonstrated, and independent security review finds no cross-workspace path. A passing unit suite alone does not establish production readiness.
