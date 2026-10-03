# Keel: product evaluation and improved product idea

**Date:** 3 October 2026.

**Inputs**
- [PROPOSAL.md](PROPOSAL.md) and the [technical deep-dive](TECH_DEEP_DIVE.md).
- Anthropic's `knowledge-work-plugins/small-business`.
- The sample documents in `doc_intelligence_ai_v2/docs`.
- A code review of the three earlier repos: `doc_intelligence_ai_v2`, `doc_intelligence_backend_api_v2.0` and `doc_intelligence_fe_v2`.

**Purpose:** an honest end-to-end assessment before any implementation starts, and a sharper product to build.

---

## 1. Verdict

**The problem is real and the technical plan is strong. But the product as currently framed is too broad to ship with one founder and no funding.**

What is too broad: "Glean for SMBs" spread across two unrelated verticals, covering bookkeeping, tax, compliance, multi-tenant hierarchies, a learning loop and plugin export.

The earlier attempts show the risk clearly:
- **9 months and about 100k lines of code** across three repos (five, counting `biz2bricks-core` and `agent_builder_v1`);
- **four different auth and tenancy contracts**;
- the one workflow that matters to a real customer (the design partner's order → production → HACCP → invoice) was **designed in detail but never built**.

**The improvement is to narrow hard:**
- **one vertical**: small food producers;
- **one end-to-end loop**: paper order → invoice → batch → food-safety record → lot trace;
- **one design partner**: the business behind the sample documents;
- **two code components**: a Next.js frontend and one Python backend.

Bookkeeping, tax and day care stay out until the first loop has paying users.

### Scorecard (1 = weak, 5 = strong)

| Dimension | Original proposal | Improved idea | Why it changes |
|---|---|---|---|
| Problem severity | 4 | **5** | Handwritten orders that are never invoiced lose revenue, and missing HACCP records are an inspection and recall risk. Both are pains owners *feel*, more than tidy books. |
| Willingness to pay | 3 | **4** | Selling "invoice every order the same day" and "pass the food-safety audit" is easier than selling "AI back office". |
| Competition | 2 | **4** | Bookkeeping and tax collide with Intuit, Xero JAX and Anthropic's free SMB plugin. Paper-first food-production operations sits between Jolt, FoodDocs and SafetyChain (food-safety apps that need digital entry) and MRP tools such as Katana and MRPeasy (also digital entry). |
| Founder fit and unfair advantage | 3 | **5** | You have real documents and a real business relationship (a design partner), plus working parsers, extractors and report generators. |
| Solo feasibility (time to first paid use) | 1 | **4** | A single loop on a two-component monolith, reusing proven code. |
| Distribution | 2 | **3** | Food-safety consultants, co-packers and distributors are a concentrated channel, much as accountants are for bookkeeping. |
| Technical differentiation | 4 | **4** | Unchanged: evidence down to the pixel, compile-once recipes, cost routing. |
| Regulatory risk | 2 | **4** | Drops children's data (day care) and tax filing (HMRC adviser registration). Food records are lower risk. |

---

## 2. What is strong (keep)

1. **Paper-first with evidence.** No incumbent turns a photographed order pad or batch sheet into trusted, linked records that point back to the source pixels. The sample documents show this is the real state of these businesses:
   - handwritten orders with grouped pricing and crossed-out lines;
   - QC batch sheets with handwritten lot numbers;
   - HACCP forms with blank critical readings;
   - no text layer on any scan.
2. **"Agents propose, code decides, humans approve."** Food safety and invoicing need this level of trust.
3. **Compile-once recipes and cost routing.** Unit cost is about $3–5 per site per month against $99+ revenue. That margin survives price competition.
4. **Linking documents to each other.** Order ↔ work order ↔ batch lot ↔ HACCP ↔ invoice ↔ supplier lot is exactly what an earlier analysis found missing at the design partner ("no bridge from handwritten orders to production"). It is also what a recall requires.
5. **Reusable assets.** Parser abstraction, extractor tool chain, PDF/XLSX report generators, usage and quota tracking, PII middleware, bulk LangGraph jobs, and the frontend's extraction, chat and agent UI components (§6.3).

## 3. What is weak or risky (change)

| # | Issue | Evidence | Change |
|---|---|---|---|
| 1 | **Scope is far too broad** | The BRD covers 10 connectors, an agent builder, SSO/SCIM and SOC 2. The proposal covers two verticals, bookkeeping, tax, a franchisor hierarchy, cross-tenant learning and plugin export. | Build one loop for one vertical. Every other feature waits for a paying user to ask for it. |
| 2 | **We were about to compete where the giants are** | Bookkeeping and tax are being bundled free by Intuit and Xero, and Anthropic's small-business plugin (900k+ installs) does AP, month-end and tax prep. | **Hand off to the ledger** instead: a clean QuickBooks or Xero import and sync. Don't do bookkeeping. |
| 3 | **The persona doesn't match the evidence** | The proposal targets an ice-cream *franchisee* (royalty reports, a POS). The samples come from a *small producer and wholesaler*: restaurant orders, kulfi batches, HACCP, work orders. | Re-target to **small food producers**: kulfi/ice cream, bakeries, sauces, caterers, co-packers. Franchisees can come later with a royalty add-on. |
| 4 | **Day care splits the effort and carries the most risk** | Children's data, rules that vary by state or Ofsted, and entrenched incumbents (Brightwheel, Procare). There are no samples or design partner. | Park it. Reconsider only once a day-care owner asks for it. |
| 5 | **We were selling the technology, not the outcome** | "Semantic layer", "graph RAG" and "agents" mean nothing to a kulfi maker. | Sell outcomes: *every order invoiced the same day*, *an audit-ready HACCP binder*, *a recall trace in 60 seconds*, *no lost orders*. The technology stays invisible. |
| 6 | **Features built before validation** | Cross-tenant learning needs many tenants. The franchisor hierarchy needs a franchisor. Plugin export needs traction. | Move them to "after 10 paying sites". |
| 7 | **Architecture sprawl, a lesson from the old repos** | Five repos, a shared ORM package, five frontend proxy families. Identity headers were trusted from the client, so knowing an email let you act as that user. Sessions were held in memory, and a table was created per organisation at runtime. | Two components, one OpenAPI spec, cookie sessions verified in the backend, organisation IDs taken from the membership table, RLS, JSONB records. No in-process state. |
| 8 | **No validation gate before building** | Nine months went into plumbing first. | A two-week concierge test and kill criteria before writing code (§7). |

---

## 4. The improved product

### 4.1 Positioning

> **Keel: the paper-to-production back office for small food producers.**
> Photograph an order, a batch sheet or a temperature log. Keel turns it into invoices, production records and an audit-ready food-safety file, with every number linked back to the paper it came from.

- **Who:** owner-operated food producers and wholesalers with 3–50 staff. Examples: kulfi and ice-cream makers, bakeries, sauce and condiment makers, caterers, small co-packers. Start where the design partner is, with the UK or US as the second market.
- **Why now:**
  - Cheap vision models can finally read their paperwork.
  - FDA's FSMA 204 traceability rule (compliance date pushed to July 2028 [U]) makes lot tracing a board-level topic for foods on the Food Traceability List. Check which of the partner's products are covered.
  - Retailers and distributors increasingly demand HACCP and traceability records from small suppliers.

### 4.2 The one loop to build first

```
① Order in         photo / email / WhatsApp of a handwritten order pad
      ↓            → lines, SKU match (fuzzy, pg_trgm), math check (grouped pricing, strike-throughs, circled total)
② Approve          owner taps ✓ (or fixes a highlighted field shown on the photo)
      ↓
③ Invoice out      invoice PDF + QuickBooks/Xero import file (the old QBO template) → emailed to customer
      ↓            daily "orders not yet invoiced" check catches missed revenue
④ Produce          approved orders → work order (base formula × batch scaling) → lot number
      ↓
⑤ Record           photo of the batch/QC sheet and HACCP log → structured record; blank or out-of-range
      ↓            critical readings flagged as missing (absent ≠ zero), owner notified
⑥ Trace & prove    "Which customers got lot L-1042?" / "Show the March HACCP file" → answers with source pages,
                   inspection binder PDF on demand
```

**Ask Keel (chat).** It covers everything above: SQL over the records first, then search over SOPs and notes.

### 4.3 What each stage needs (mapped to the sample documents)

| Stage | Sample-document type | Key fields | Validation | Output |
|---|---|---|---|---|
| Order | Handwritten order pad (photo) | Customer, date, order number, lines (SKU, quantity, price), total | Line math, grouped pricing, strike-throughs, circled total = sum, known customer and SKU | Order record and draft invoice |
| Invoice | QuickBooks import template (xlsx) | Invoice number, customer, items, rates, tax | Order ↔ invoice number reconciliation | PDF, QBO/Xero CSV, email |
| Batch / QC | Scanned formula batch sheet | Product, date, lot, preparer, ingredient lots and quantities, ticks | Quantities match the base formula × scale; ingredient lots present | Batch record linked to supplier lots |
| HACCP | Cooking/filling control record | Times, temperatures, Brix, operator initials | Critical limits from the HACCP plan (e.g. minimum fill temperature, minimum pack weight); blanks = missing | CCP log, deviation alert, binder |
| Work order | ERP work-order report (scan) | Products, quantities, gallons, premix | Recipe (compile once, then replay) | Production plan linked to orders |

### 4.4 Pricing and success metrics

- **Founding partner:** free for 3 months, then $49/month in exchange for feedback and a case study.
- **Standard:** **$149 per site per month.** Add-ons follow demand, e.g. a royalty pack for franchisees, or supplier invoices for cost of goods.
- **North-star metrics:**
  - the share of orders invoiced within 24 hours;
  - $ of unbilled orders caught;
  - HACCP record completeness %;
  - time to answer a recall trace;
  - the owner's admin hours saved per week.

### 4.5 Roadmap after the loop works

1. **Supplier invoices to cost of goods per SKU.** This is the "link invoices together" ask, and it gives margin per product.
2. **More small food producers.** Pack variants: bakery, sauces, caterers.
3. **Food-safety consultant channel.** Each consultant manages 10–50 producers, so this needs multi-organisation membership.
4. **Franchisee add-on** (royalty and ad fund) and **franchisor view**.
5. **Learning across tenants** (k-anonymous recipes), once there are more than 20 tenants.
6. **Other verticals** (day care etc.) as new packs, only when a design partner asks.

---

## 5. Competitive check for the new focus

These competitor details come from general knowledge and were not verified this session. Check them during discovery.

| Category | Examples | Why small producers still use paper | Keel's angle |
|---|---|---|---|
| Food-safety apps | Jolt, FoodDocs, Safefood 360, SafetyChain | Need tablets and digital entry at the line; often priced for larger plants | Paper and photo stay the input; Keel digitises them afterwards |
| MRP / inventory | Katana, MRPeasy, Craftybase | Need clean digital orders and BOMs | Turns paper orders into structured data that can feed these tools later |
| Bookkeeping | QuickBooks, Xero (with built-in AI) | Accept typed or imported data only | Keel is the source: it produces the import file and syncs |
| Horizontal AI | ChatGPT, Claude SMB plugin | No food-safety records, lot graph or approval-gated workflow | Vertical depth and evidence |

---

## 6. Two-component architecture

### 6.1 The two components

```
keel/
├── frontend/          Next.js 15+ (App Router, React 19, Tailwind, TanStack Query) — PWA with camera capture
│                      talks ONLY to the backend via same-origin /api (Next.js rewrite) — no CORS, no proxy families
│                      typed client generated from backend OpenAPI in CI
└── backend/           Python 3.12, FastAPI — one codebase, one container image, two run modes:
                         `keel api`     HTTP API (Cloud Run service)
                         `keel worker`  queue consumer / batch jobs (Cloud Run job or same service, flag-controlled)
                       modules (a modular monolith, not services):
                         identity/   auth (argon2 passwords, magic link, Google OAuth later), cookie sessions in
                                     Postgres, orgs, memberships(user↔org, role), invites, roles (owner/admin/member/viewer)
                         billing/    plans, quotas, usage meters (ported from core/usage), Stripe later
                         files/      upload, signed URLs, storage abstraction (R2/GCS/local), keys by org UUID
                         documents/  page parser (LiteParse → PP-OCRv5 → Luna → Gemini → ADE), validators, review queue
                         domain/     customers, products/SKUs, orders, invoices, formulas, batches/lots, haccp_logs
                         agents/     deepagents/LangGraph: intake, reconciliation, ask-Keel; tools call domain services
                         search/     pgvector + full-text hybrid, graph (edges) queries
                         semantic/   metric YAML (OSI-format) → SQL compiler, run_metric
                         reports/    PDF/XLSX/binder generators (ported), QBO/Xero export
                         audit/      append-only audit log, approvals ledger
                         platform/   db (SQLAlchemy async + RLS session hook), config, logging/OTel, errors
```

**External services:** Postgres (Docker locally, Neon in the cloud), object storage (MinIO/R2), model APIs.

**One repo, one CI, one docker-compose.**

### 6.2 Non-negotiables (lessons from the old repos)

1. Identity comes **only from a verified session cookie** (httpOnly, Secure, SameSite=Lax). `org_id` comes from the membership table, never from a client header.
2. Every request runs `SET LOCAL app.org_id = …` inside its transaction, and **RLS policies** enforce isolation on every tenant table.
3. **UUIDs only** for tenants in keys and paths (`{org_id}/docs/{doc_id}/...`), never organisation names.
4. **No runtime DDL.** Extracted records live in `records(org_id, type, schema_version, data jsonb, ...)` with typed domain tables for core entities.
5. **No in-process state:** sessions, rate limits, queues and caches go in Postgres (or Redis later).
6. **One OpenAPI spec and one generated TypeScript client**, regenerated and diff-checked in CI.
7. **Tests gate deploys:** pytest (unit, plus golden extraction evals), Vitest, and a Playwright smoke run of the loop. No `|| true`.
8. **Model IDs in config**; every LLM call logs tenant, model, tokens and $.
9. **No file larger than about 400 lines**, and one repository base class. This avoids the god files found in the old review.

### 6.3 Reuse map from the earlier repos

| Port as-is (adapt imports) | Port with changes | Discard |
|---|---|---|
| `agents/core/middleware` (resilience, PII safety, limits) → deepagents middleware | Storage (`storage/base.py`, `gcs.py`, plus upload/download from `backend_api/app/services/document/*`) → keyed by org UUID, R2/GCS/local | `biz2bricks_core` as a separate package |
| `core/usage/*` (token extractors, quota checker, usage queue) + `seed_tiers.py` | Org, user and folder services → memberships, invites, RLS | `simple_auth.py`, in-memory session and token registries, `debug.py` |
| Extractor tools (field analyzer → schema → extractor, line items) + prompts | Audit → one table plus an async writer | Header-trust `get_org_id`, public organisation list plus self-join registration |
| `gemini_parse_util.py`, `parse_service.py` (hash cache) → provider-agnostic page parser | Document agent tools split out of the 1,787-line `document/core.py` | `rate_limiter.py`, `session_manager.py`, `executors.py`, `nest_asyncio` |
| Sheets agent tools (DuckDB) with a `sqlglot` guard | RAG: Gemini File Search → pgvector + full text (keep `rag_search` citation formatting) | Custom `QueryClassifier` / `LLMToolSelector` |
| Report outputs (PDF, XLSX, dashboard data) | Per-organisation dynamic tables → JSONB `records` | Five frontend proxy route families, CORS docs, three deploy scripts |
| `bulk/state_graph.py` checkpointed job pattern | Frontend: extraction steps, chat, excel-chat, reports, usage, charts, FileUpload, agent graph/runs UI → one typed client, cookie auth | localStorage tokens, two generated type files |
| Password hashing helpers from `security.py` | Your earlier food-production design docs (pg_trgm SKU match, formula scaling, HACCP CCP, shadow mode then human approval) → **build them now as the core loop** | BRD enterprise scope (SSO/SCIM/SOC 2/10 connectors) for now |

---

## 7. Validate before building (2 weeks, about $0)

| Step | What | Pass bar |
|---|---|---|
| 1 | **Shadow the design partner** for one week: count orders, invoices, batch sheets and HACCP forms; time the admin work; note missed invoices | At least 5 hours a week of admin, or at least one revenue leak found |
| 2 | **Concierge test.** Process their real paperwork with a notebook and the existing parser (Luna and Gemini side by side), then hand back invoices and a HACCP binder by hand | Owner says they'd pay; accuracy at least 95% per field after review routing |
| 3 | **10 discovery calls** with similar producers (local food associations, co-packers, food-safety consultants) | At least 3 say they'd pay $99+/month; at least 1 more design partner |
| 4 | **Gold set:** label 100+ real pages (orders, batch, HACCP) | Sets the parser routing and becomes the regression test suite |

**Kill or pivot criteria**
- Fewer than 3 of 10 producers would pay.
- Handwriting field accuracy stays below 95% even with review routing.
- The design partner stops using it weekly by week 6 of the pilot.

If any one of these is hit, revisit the vertical, not the technology.

## 8. Build plan (after validation)

| Weeks | Deliverable |
|---|---|
| 1–2 | Monorepo, docker-compose, identity (sessions, organisations, memberships, invites), RLS, files, CI with tests gating deploys, generated client, Cloud Run + Neon pilot environment |
| 3–4 | Page parser + validators + review UI (photo with field boxes) for **orders**; SKU and customer matching; approval |
| 5 | Invoices: PDF + QBO/Xero export + email; "unbilled orders" check |
| 6–7 | Batch/QC and HACCP records; critical-limit rules; missing-reading alerts; binder PDF |
| 8 | Lot trace and Ask Keel (SQL first, then hybrid search); usage meter and quota |
| 9–10 | Pilot hardening with the design partner; second producer onboarded; pricing live |

---

## 9. What this means for the existing documents

- [PROPOSAL.md](PROPOSAL.md) stays as the long-term vision and technology reference. Its **Decisions D1–D7 still hold**: parser routing, models, embeddings, Postgres hybrid search, graph in Postgres, OSI semantic layer, free-tier hosting.
- **Changed priorities:**
  - the first vertical is small food producers, not franchisees or day care;
  - bookkeeping becomes ledger hand-off only;
  - the franchisor hierarchy, cross-tenant learning and pack export are deferred;
  - the architecture is **two components** (§6).
