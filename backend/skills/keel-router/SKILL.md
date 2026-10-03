---
name: keel-router
description: >
  Picks the one skill that fits a plain-language request when it isn't obvious which applies, e.g.
  "help with the paperwork", "what should I do today", "is everything OK". Routes to ask-keel for
  questions about records, keel-onboard for setup, and names the screen for anything that changes records.
allowed-tools: business_snapshot, onboarding_status
metadata:
  gates: []
  fallback: ask one short clarifying question
---

# Router

Answer with **one recommendation, one reason, one ask**.

1. If setup isn't finished (`onboarding_status` has a `next`), and the request is general, recommend that
   next step.
2. Questions about orders, invoices, sales, documents, lots or HACCP → follow `ask-keel`.
3. Anything that would create, send, approve or change a record (an order, an invoice, a batch, a
   correction, the profile) → Keel's chat can't do it. Name the screen where it's done and what the
   owner will be asked to approve there.
4. If two readings are equally plausible, ask one short question instead of guessing.

Never chain several skills in one answer, and never present a guess as a record.
