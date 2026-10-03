"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Card, ErrorNote, PageTitle, Pill } from "@/components/ui";
import { getBatch, unwrap } from "@/lib/api";
import { day } from "@/lib/format";

export default function BatchPage() {
  const { id } = useParams<{ id: string }>();
  const q = useQuery({ queryKey: ["batch", id], queryFn: () => unwrap(getBatch({ path: { batch_id: id } })) });
  if (q.error) return <ErrorNote error={q.error} />;
  const b = q.data;
  if (!b) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <>
      <Link href="/production" className="text-sm text-muted hover:text-ink">← Production</Link>
      <PageTitle title={`Batch ${b.number}`} sub={`${b.product ?? "Unknown product"} · made ${day(b.made_on)}${b.prepared_by ? ` by ${b.prepared_by}` : ""}`}>
        <Pill tone="ledger">signed off{b.version > 1 ? ` · v${b.version}` : ""}</Pill>
      </PageTitle>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card className="overflow-x-auto p-5">
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">Made from</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="pb-2 font-normal">Ingredient</th><th className="pb-2 font-normal">Lot</th><th className="pb-2 text-right font-normal">Qty</th></tr>
            </thead>
            <tbody>
              {b.inputs?.map((i, n) => (
                <tr key={n} className="border-t border-line">
                  <td className="py-2">{i.ingredient}</td>
                  <td className="py-2">
                    {i.lot_code ? (
                      <Link href={`/trace?lot=${encodeURIComponent(i.lot_code)}`} className="num text-inkblue underline-offset-4 hover:underline">{i.lot_code}</Link>
                    ) : (
                      <Pill tone="carbon">not written down</Pill>
                    )}
                  </td>
                  <td className="num py-2 text-right">{i.quantity !== null ? `${Number(i.quantity)} ${i.unit ?? ""}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card className="space-y-3 p-5 text-sm">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Output lot</p>
            {b.output_lot ? (
              <Link href={`/trace?lot=${encodeURIComponent(b.output_lot)}`} className="num text-2xl font-semibold text-inkblue">{b.output_lot}</Link>
            ) : (
              "—"
            )}
            {b.quantity && <p className="num text-muted">{Number(b.quantity)} {b.unit}</p>}
          </div>
          <p className="text-muted">Trace this lot to see every supplier lot behind it and every customer it reached.</p>
          {b.source_document_id && (
            <Link href={`/documents/${b.source_document_id}`} className="inline-block underline underline-offset-4">See the original batch sheet</Link>
          )}
        </Card>
      </div>
    </>
  );
}
