"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type ReactNode } from "react";
import { Button, Card, Empty, ErrorNote, Input, PageTitle, Pill } from "@/components/ui";
import { listLots, trace, unwrap } from "@/lib/api";
import { day } from "@/lib/format";

type Lot = { code: string; kind: string; ingredient: string | null; supplier: string | null; depth?: number };
type BatchRow = { number: string; made_on: string | null; output_lot: string; product: string | null };
type Reach = { order_number: string; delivery_date: string | null; customer: string | null; email: string | null; lot: string; product: string; quantity: string | null };

export default function TracePage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <Trace />
    </Suspense>
  );
}

function Trace() {
  const router = useRouter();
  const code = useSearchParams().get("lot") ?? "";
  const [draft, setDraft] = useState(code);
  const [shown, setShown] = useState(code);
  if (shown !== code) {
    setShown(code); // followed a lot link: show its code in the box
    setDraft(code);
  }
  const lots = useQuery({ queryKey: ["lots"], queryFn: () => unwrap(listLots()) });
  const t = useQuery({ queryKey: ["trace", code], queryFn: () => unwrap(trace({ path: { code } })), enabled: !!code, retry: false });
  const r = t.data;

  return (
    <>
      <PageTitle title="Trace a lot" sub="Back to the supplier lots it was made from, forward to every batch and customer it reached." />
      <form
        className="mb-6 flex max-w-xl gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim()) router.push(`/trace?lot=${encodeURIComponent(draft.trim())}`);
        }}
      >
        <Input id="trace_lot" list="lot_codes" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Lot code, e.g. a milk lot or a finished product lot" />
        <datalist id="lot_codes">
          {lots.data?.map((l) => <option key={l.code} value={l.code}>{`${l.kind}${l.name ? ` · ${l.name}` : ""}`}</option>)}
        </datalist>
        <Button>Trace</Button>
      </form>

      {!code && lots.data?.length === 0 && <Empty title="Nothing to trace yet">Sign off a batch sheet first; its lots appear here.</Empty>}
      {t.error && <ErrorNote error={t.error} />}
      {t.isFetching && <div className="processing h-2 rounded-full" aria-label="Tracing" />}
      {r && (
        <div className="space-y-5">
          <RecallLine customers={r.customers as Reach[]} batches={r.batches as BatchRow[]} gaps={r.gaps ?? []} code={code} />
          <div className="grid items-stretch gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr]">
            <Column title="Made from" empty="No supplier lots behind this lot.">
              {(r.backward as Lot[]).map((l) => (
                <LotChip key={l.code} code={l.code} sub={[l.ingredient, l.supplier].filter(Boolean).join(" · ") || l.kind} />
              ))}
              {(r.gaps ?? []).map((g) => (
                <div key={g} className="rounded-lg border border-dashed border-carbon bg-carbon-soft px-3 py-2 text-sm">{g}</div>
              ))}
            </Column>
            <Arrow />
            <Column title="Batches" empty="Not used in any batch yet.">
              <div className="rounded-lg border-2 border-inkblue bg-inkblue-soft px-3 py-2">
                <p className="text-xs uppercase tracking-wide text-inkblue">Traced lot</p>
                <p className="num text-xl font-semibold">{(r.lot as Lot).code}</p>
                <p className="text-xs text-muted">{(r.lot as Lot).ingredient ?? (r.lot as Lot).kind}</p>
              </div>
              {(r.batches as BatchRow[]).map((b) => (
                <div key={b.number} className="rounded-lg border border-line px-3 py-2 text-sm">
                  <p className="font-medium">Batch <span className="num">{b.number}</span> · {b.product ?? "—"}</p>
                  <p className="text-xs text-muted">
                    {day(b.made_on)} → lot{" "}
                    <Link href={`/trace?lot=${encodeURIComponent(b.output_lot)}`} className="num text-inkblue underline-offset-2 hover:underline">{b.output_lot}</Link>
                  </p>
                </div>
              ))}
            </Column>
            <Arrow />
            <Column title="Reached" empty="Not allocated to any order yet. Add lots on an order's lines to close the loop.">
              {(r.customers as Reach[]).map((c, i) => (
                <div key={i} className="rounded-lg border border-line px-3 py-2 text-sm">
                  <p className="font-medium">{c.customer ?? "Unknown customer"}</p>
                  <p className="text-xs text-muted">
                    Order <span className="num">{c.order_number}</span> · {day(c.delivery_date)} · lot <span className="num">{c.lot}</span>
                  </p>
                  {c.email && <p className="text-xs text-muted">{c.email}</p>}
                </div>
              ))}
            </Column>
          </div>
        </div>
      )}
    </>
  );
}

function RecallLine({ customers, batches, gaps, code }: { customers: Reach[]; batches: BatchRow[]; gaps: string[]; code: string }) {
  const people = new Set(customers.map((c) => c.customer)).size;
  return (
    <Card className="flex flex-wrap items-center gap-3 p-4">
      <p className="text-sm">
        Lot <span className="num font-semibold">{code}</span> went into <b>{batches.length}</b> batch(es) and reached <b>{people}</b> customer(s).
      </p>
      {gaps.length > 0 ? <Pill tone="carbon">{gaps.length} trace gap(s)</Pill> : <Pill tone="ledger">no gaps</Pill>}
    </Card>
  );
}

function Column({ title, empty, children }: { title: string; empty: string; children: ReactNode }) {
  const items = Array.isArray(children) ? children.flat().filter(Boolean) : children ? [children] : [];
  return (
    <Card className="space-y-2 p-4">
      <h2 className="text-xs font-medium uppercase tracking-wide text-muted">{title}</h2>
      {items.length ? children : <p className="text-sm text-muted">{empty}</p>}
    </Card>
  );
}

function LotChip({ code, sub }: { code: string; sub: string }) {
  return (
    <Link href={`/trace?lot=${encodeURIComponent(code)}`} className="block rounded-lg border border-line px-3 py-2 text-sm hover:border-inkblue">
      <span className="num font-medium">{code}</span>
      <span className="block text-xs text-muted">{sub}</span>
    </Link>
  );
}

function Arrow() {
  return <div aria-hidden className="hidden items-center text-2xl text-muted lg:flex">→</div>;
}
