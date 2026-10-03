# Keel

Keel turns small food producers' paperwork into orders, invoices and food-safety records. Owners photograph or upload what they already use: order pads, scans and emailed orders. Every value links back to where it was written, and nothing is created, sent or posted without a person's approval.

Keel is two components:

- **`backend/`**: FastAPI with LangGraph and deepagents. It handles tenants and users, documents and the AI pipeline, approval-gated workflows, invoicing and the Ask Keel agent.
- **`frontend/`**: Next.js 16. It provides the Desk, the review screen with evidence boxes, orders, invoices, catalog, team and the Ask Keel panel.

Postgres holds everything. Row-level security isolates each business's data.

## What works today

| Area | Details |
|---|---|
| Tenancy | Sign up a business, sign in with a password or magic link, invite teammates with roles (owner/admin/member/viewer), switch between businesses. Postgres RLS on every tenant table; the app's database role cannot bypass it. |
| Paper in | Drag and drop, file picker, or a phone camera upload. The same photo uploaded twice is processed only once. |
| Reading | PDF text layer → CPU OCR (PP-OCR via RapidOCR) → extraction (GPT-6 Luna with a key, or an offline rules engine) → Gemini 3.8 Flash re-read when checks fail. |
| Checks | Line and total maths, grouped pricing, crossed-out lines, unreadable fields (left empty, never guessed), dates, and instructions written on the paper (ignored). |
| Evidence | Each value is boxed on the page image. Hover a field to see where it was read; click to correct it. |
| Approvals | LangGraph workflow pauses at a gate. The approval is bound to a hash of exactly what will be written; edits made after approval need a new approval. |
| Orders → invoices | Prices come from the customer's price list or the catalog, never the paper. Issuing an invoice is a separate approval. Invoices export as PDF and as QuickBooks or Xero CSV. |
| Ask Keel | A deepagents agent with skills (`backend/skills/`), shared rules, tenant memory, read-only tools and streamed answers. It works offline without API keys. |
| Metering | The Desk shows token and page cost for every model call, per tenant. |

## Run it locally

You need Python 3.13 with [uv](https://docs.astral.sh/uv/), Node 22 with pnpm, and either Docker (for Postgres) or a local Postgres 16+ with pgvector.

```bash
make setup                 # backend + frontend dependencies
make db                    # Postgres 17 + pgvector in Docker (creates roles keel_owner / keel_app)
cp backend/.env.example backend/.env   # optional: add OPENAI_API_KEY / GOOGLE_API_KEY
make migrate
make seed                  # demo business with sample documents
make dev                   # API :8000, worker, web :3000
```

Open http://localhost:3000 and sign in as **owner@demo.keel** with password **keel-demo-2026**, or create your own business.

Without API keys, Keel runs fully offline:
- The local rules engine reads typed and OCR'd order sheets.
- Ask Keel answers through an offline tool-calling model.

Add `OPENAI_API_KEY` for GPT-6 Luna extraction and full agent answers, and `GOOGLE_API_KEY` for Gemini handwriting re-reads.

**Postgres without Docker:** create the roles and databases in `backend/scripts/init-db.sql` (for example `sudo -u postgres psql -f backend/scripts/init-db.sql`), then continue from `make migrate`.

**Everything in Docker:** `docker compose up --build`, then `docker compose exec api keel seed`.

## Checks

```bash
make test        # 16 backend integration tests against real Postgres (RLS, approvals, injection, OCR, agent)
make lint        # ruff + eslint
make typecheck   # mypy --strict + tsc
make e2e         # Playwright: sign-up → catalog → upload → review → approve → invoice → Ask Keel (needs make dev)
```

## Docs

- [`intent.md`](intent.md) and [`plan.md`](plan.md): AI-native SDLC artifacts (intent and build plan).
- [`docs/FINAL_REVIEW.md`](docs/FINAL_REVIEW.md): locked decisions; [`docs/PRODUCT_EVALUATION.md`](docs/PRODUCT_EVALUATION.md): what to build first and why.
- [`docs/PROPOSAL.md`](docs/PROPOSAL.md) and [`docs/TECH_DEEP_DIVE.md`](docs/TECH_DEEP_DIVE.md): vision and technology research.
- [`CLAUDE.md`](CLAUDE.md) and [`REVIEW.md`](REVIEW.md): conventions and review policy.
