# Keel: working notes for Claude

Two components: `backend/` (FastAPI modular monolith; `keel api|worker|migrate|seed|openapi`) and `frontend/`
(Next.js 16). Spec: `intent.md`, `plan.md`, `docs/FINAL_REVIEW.md`.

## Commands
- `make test` (pytest against Postgres `keel_test`), `make lint`, `make typecheck`, `make build`, `make e2e`
- `make openapi` after any API change; never hand-edit `frontend/lib/api/gen/`.

## Conventions
- Tenant isolation is Postgres RLS. Do tenant work inside `tenant_session(org_id, user_id)`; the app role has no BYPASSRLS.
  Identity comes only from the session cookie (`api/deps.py`). Never read org or user ids from headers or the body.
- Every tenant table: `org_id` column + `tenant_rls()` in its migration + a test that another tenant can't see it.
- Writes that create, send, spend or post go through `workflows/approvals.consume()` with a hash-bound approval.
- Extraction values carry a status; unreadable stays `null`. Never default a missing number to 0.
- Money is `Decimal` + ISO currency code. Model IDs and thresholds live in `platform/config.py`.
- Model ids are UUIDv7, assigned at construction (`Base.__init__`).
- Files stay under ~400 lines; tools return compact JSON.

## Things Claude gets wrong here
- Next.js 16: route `params` are async; read `frontend/node_modules/next/dist/docs/` before using a Next API.
- `pkill -f <pattern>` matches its own shell command line; stop servers by PID.
- JSONB edits need a deep copy + `flag_modified`, or SQLAlchemy won't persist them.
