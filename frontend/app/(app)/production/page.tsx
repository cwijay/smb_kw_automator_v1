"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Card, Empty, PageTitle, Pill } from "@/components/ui";
import { listBatches, unwrap } from "@/lib/api";
import { day } from "@/lib/format";

export default function ProductionPage() {
  const q = useQuery({ queryKey: ["batches"], queryFn: () => unwrap(listBatches()) });
  return (
    <>
      <PageTitle title="Production" sub="Signed-off batch records. They can't be edited, only superseded, so the history holds up in an audit." />
      {q.data?.length === 0 && <Empty title="No batches yet">Choose “Batch sheets” on the Desk and drop a batch sheet to record one.</Empty>}
      {!!q.data?.length && (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 py-2.5 font-normal">Batch</th>
                <th className="px-4 py-2.5 font-normal">Product</th>
                <th className="px-4 py-2.5 font-normal">Made</th>
                <th className="px-4 py-2.5 font-normal">Output lot</th>
                <th className="px-4 py-2.5 text-right font-normal">Yield</th>
                <th className="px-4 py-2.5 font-normal">Ingredient lots</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((b) => {
                const missing = b.inputs?.filter((i) => i.status === "missing").length ?? 0;
                return (
                  <tr key={b.id} className="border-t border-line hover:bg-surface-2">
                    <td className="px-4 py-2.5">
                      <Link href={`/production/${b.id}`} className="num font-medium underline-offset-4 hover:underline">{b.number}</Link>
                      {b.version > 1 && <span className="ml-1 text-xs text-muted">v{b.version}</span>}
                    </td>
                    <td className="px-4 py-2.5">{b.product ?? "—"}</td>
                    <td className="px-4 py-2.5">{day(b.made_on)}</td>
                    <td className="px-4 py-2.5">
                      {b.output_lot && <Link href={`/trace?lot=${encodeURIComponent(b.output_lot)}`} className="num text-inkblue underline-offset-4 hover:underline">{b.output_lot}</Link>}
                    </td>
                    <td className="num px-4 py-2.5 text-right">{b.quantity ? `${Number(b.quantity)} ${b.unit ?? ""}` : "—"}</td>
                    <td className="px-4 py-2.5">
                      {missing ? <Pill tone="carbon">{missing} untraceable</Pill> : <Pill tone="ledger">all recorded</Pill>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
