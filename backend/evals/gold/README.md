# Gold sets for the parser bake-off

One JSON per document, next to the document file:

```json
{"file": "order-typed.pdf", "mime": "application/pdf", "kind": "order_pad",
 "expected": {"customer_name": "Rasoi Kitchen", "lines[0].quantity": "11", "ingredients[1].lot_code": null}}
```

- Keys are field paths in the extraction schema (`keel/documents/schemas.py`).
- `null` means the paper is empty there. An engine that returns a value for it has **invented** one; that
  count is the first thing to look at in a report.
- Numbers compare numerically (`11` = `11.000`), text compares case- and space-insensitively.

`synthetic/` is generated (`keel evals synthetic`), deterministic and committed; CI gates on it.
**Real customer pages never go in git.** Keep them in a private directory with the same layout:

```bash
keel evals parsers --engines local-rules,luna,gemini,sol,reducto,ade --gold ~/private-gold --out evals/reports
```

Engines without a key are skipped and listed in the report. Tier-4 prices in `platform/config.py` are
placeholders until set from your plan.
