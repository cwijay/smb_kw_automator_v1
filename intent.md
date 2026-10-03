# Intent: Keel, the paper-to-production back office for small food producers

**Author:** C. Wijayasundara (founder), drafted with Claude.

**Status:** draft. The founder approves it.

**Date:** 3 Oct 2026.

**Spec (Stage 2):** [docs/PRODUCT_EVALUATION.md](docs/PRODUCT_EVALUATION.md) and [docs/FINAL_REVIEW.md](docs/FINAL_REVIEW.md).

**Background:** [docs/PROPOSAL.md](docs/PROPOSAL.md) and [docs/TECH_DEEP_DIVE.md](docs/TECH_DEEP_DIVE.md).

## Problem

Small food producers (kulfi and ice-cream makers, bakeries, sauce makers, caterers, small co-packers) run on paper:
- handwritten customer order pads;
- scanned batch and QC sheets with handwritten lot numbers and tick marks;
- HACCP temperature logs;
- invoices keyed into QuickBooks by hand.

Nothing links these records. As a result:
- orders get missed or invoiced late, and revenue leaks;
- critical food-safety readings are left blank and nobody notices until an inspection;
- answering "which customers received lot X?" takes hours.

Today's tools don't fix this:
- **Food-safety apps and MRP tools** need staff to type data in at the line.
- **Bookkeeping AI** (QuickBooks, Xero) only sees data after someone has keyed it in.
- **General assistants** (ChatGPT, Claude's SMB plugin) keep no regulated records and enforce no approvals.

## Proposed outcome

The owner photographs, forwards or uploads the paper they already use. Keel turns it into linked, trusted records, and every number points back to the spot on the page it came from.

1. **Orders.** A handwritten order becomes an approved order the same day. Nothing is invented: an unreadable field is named, never guessed.
2. **Invoices.** Every approved order produces an invoice PDF and a QuickBooks or Xero import, emailed only after approval. A daily check catches orders that were never invoiced.
3. **Batches and HACCP.** Batch and QC sheets become batch records linked to ingredient lots. HACCP readings are checked against critical limits, and a blank reading is flagged as *missing*, never as "passed".
4. **Traceability.** "Which customers got lot L-1042?" is answered in under a minute, and an inspection binder is generated on demand.
5. **Ask Keel.** Plain-language questions over all of the above, answered with sources.

**Success measures (pilot)**
- At least 95% of orders invoiced within 24 hours.
- Zero invented quantities or lot codes on the gold set.
- At least 97% field accuracy after review routing.
- HACCP record completeness visible and improving.
- A recall trace in under 60 seconds.
- The owner saves at least 5 admin hours a week.
- AI and infrastructure cost of at most $5 per site per month.

## Affected users and systems

**Users**
- **Owner/admin:** approves and configures.
- **Office staff:** upload paperwork and review flagged fields.
- **Production lead:** batch and HACCP sign-off.
- **Later:** an accountant (read and export) and a food-safety consultant (several organisations).

**Systems**
- Keel is the **new** system of record for orders, batches, lots and HACCP records.
- QuickBooks or Xero stays the record for money; Keel writes to it or produces an import file.
- Email (inbound forwarding and outbound invoices).
- Phone camera via a PWA.
- Model APIs: OpenAI GPT-6 Luna, Google Gemini 3.8 Flash and Fireworks GLM-5.3, with Reducto, LandingAI ADE and GPT-6 Sol as tier-4 candidates.

## Constraints

- **Budget:** no funding and no cloud credits. Use free tiers (Cloud Run, Neon, R2), pay-per-use APIs only, no always-on GPUs. AI plus infrastructure must cost at most $5 per site per month.
- **Team:** one founder, building with Claude Code. Exactly **two code components**: a Next.js frontend and one FastAPI backend (a modular monolith with API and worker run modes).
- **Trust:**
  - every write that sends, spends, publishes or commits sits behind a separate, specific approval, enforced in code with an approval hash;
  - document text is treated as data, never instructions;
  - HACCP and batch records are append-only.
- **Tenancy:**
  - identity comes from a session cookie the backend verifies;
  - the organisation comes from membership;
  - Postgres RLS on every tenant table;
  - UUIDs only;
  - no runtime DDL;
  - no in-process state.
- **Regulatory:**
  - Keel prepares records and does not file tax returns;
  - children's data and day care are out of scope;
  - food-safety records keep provenance (transcribed from a photo, confidence, verified by whom).
- **Stack:**
  - backend: Python 3.13, FastAPI, SQLAlchemy 2.1, deepagents 0.7.21 (below 0.8), langgraph 1.2, Postgres 17 with pgvector;
  - frontend: Next.js 16, React 19, Tailwind 4, TypeScript 6.x.
- **Process:**
  - tests, lint, type checks, the OpenAPI diff and eval smoke runs all gate deploys;
  - no `|| true`;
  - files stay under about 400 lines.

## Out of scope (for this intent)

- Bookkeeping and tax beyond the ledger hand-off.
- Day care and franchisor features.
- Learning across tenants.
- Exporting skills to Claude or ChatGPT.
- SSO/SCIM, SOC 2.
- Connectors built by tenants.
- A dedicated graph database.

## Open questions

1. Will the design partner commit to the 2-week concierge test, and consent to their pages being used as the gold set?
2. Which of the partner's products are on FDA's Food Traceability List (FSMA 204)? This sets how much traceability detail the records must hold.
3. QuickBooks or Xero (or both) at launch? Does the partner's ledger allow write access, or is an import file enough?
4. Market order after the partner: US or UK?
5. Which tier-4 engine wins the bake-off on handwritten critical fields: Reducto, ADE or GPT-6 Sol?
6. Email provider for outbound invoices (Postmark vs SES), and whether WhatsApp intake is needed in the pilot.
