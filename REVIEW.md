# Review policy

Run three passes and tag each finding with its pass.

## Passes
- **Bugs**: logic errors, broken edge cases, regressions, missing tests for changed behaviour.
- **Security**: tenant leaks (any query outside `tenant_session`, any id taken from the client), missing RLS on a
  new table, auth gaps, PII or secrets in logs, prompt-injection paths from document text into tools.
- **Compliance**: a write that skips `approvals.consume()`, merged gates, an invented default for an unread value,
  edits to append-only records, money without a currency code.

## Important vs Nit
Important: anything in Security or Compliance; any Bug that changes stored data. Nit: naming, style, comments.

## Skip
`frontend/lib/api/gen/**`, `uv.lock`, `pnpm-lock.yaml`, anything ruff/eslint/mypy already enforce.
