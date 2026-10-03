"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { LotCell } from "@/components/production/LotCell";
import { Button, Card, ErrorNote, PageTitle, Pill, STATUS_TEXT } from "@/components/ui";
import { decideApproval, getOrder, issueInvoice, stageInvoice, unwrap } from "@/lib/api";
import { day, money } from "@/lib/format";
import { canEdit, useMe } from "@/lib/hooks";

export default function OrderPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const me = useMe();
  const q = useQuery({ queryKey: ["order", id], queryFn: () => unwrap(getOrder({ path: { order_id: id } })) });
  const [staged, setStaged] = useState<{ approval_id: string; summary: { text?: string } } | null>(null);
  const [invoice, setInvoice] = useState<{ id: string; number: string } | null>(null);

  const stage = useMutation({
    mutationFn: () => unwrap(stageInvoice({ path: { order_id: id } })),
    onSuccess: (r) => setStaged(r as never),
  });
  const approveAndIssue = useMutation({
    mutationFn: async () => {
      await unwrap(decideApproval({ path: { approval_id: staged!.approval_id }, body: { approve: true } }));
      return unwrap(issueInvoice({ path: { order_id: id }, body: { approval_id: staged!.approval_id } }));
    },
    onSuccess: async (inv) => {
      setInvoice({ id: inv.id, number: inv.number });
      setStaged(null);
      await qc.invalidateQueries();
    },
  });

  if (q.error) return <ErrorNote error={q.error} />;
  const o = q.data;
  if (!o) return <p className="text-sm text-muted">Loading…</p>;

  return (
    <>
      <Link href="/orders" className="text-sm text-muted hover:text-ink">← Orders</Link>
      <PageTitle title={`Order ${o.number}`} sub={`${o.customer} · deliver ${day(o.delivery_date)}`}>
        <Pill tone={o.status === "approved" ? "carbon" : "ledger"}>{STATUS_TEXT[o.status] ?? o.status}</Pill>
      </PageTitle>
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card className="overflow-x-auto p-5">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr><th className="pb-2 font-normal">Item</th><th className="pb-2 font-normal">Lots shipped</th><th className="pb-2 text-right font-normal">Qty</th><th className="pb-2 text-right font-normal">Price</th><th className="pb-2 text-right font-normal">Total</th></tr>
            </thead>
            <tbody>
              {o.lines?.map((l, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="py-2">{l.description}</td>
                  <td className="py-2"><LotCell orderId={o.id} lineId={l.id} lots={l.lots ?? []} editable={canEdit(me.data?.role)} /></td>
                  <td className="num py-2 text-right">{Number(l.quantity)} {l.unit}</td>
                  <td className="num py-2 text-right">{money(l.unit_price, o.currency)}</td>
                  <td className="num py-2 text-right">{money(l.line_total, o.currency)}</td>
                </tr>
              ))}
              <tr className="border-t-2 border-ink font-medium"><td className="py-2" colSpan={4}>Total</td><td className="num py-2 text-right">{money(o.total, o.currency)}</td></tr>
            </tbody>
          </table>
          <p className="mt-4 text-xs text-muted">
            Written on the paper as “{o.customer_as_written}”.{" "}
            {o.source_document_id && <Link className="underline" href={`/documents/${o.source_document_id}`}>See the original</Link>}
          </p>
        </Card>
        <div className="space-y-4">
          {invoice && (
            <div className="rounded-xl border border-ledger bg-ledger-soft p-5">
              <p className="font-semibold text-ledger">Invoice {invoice.number} issued.</p>
              <p className="mt-1 text-sm">It has not been emailed. Open it, or export it for QuickBooks or Xero from Invoices.</p>
              <a className="mt-3 inline-block text-sm font-medium underline" href={`/api/invoices/${invoice.id}/pdf`} target="_blank" rel="noreferrer">Open PDF →</a>
            </div>
          )}
          {o.status === "approved" && canEdit(me.data?.role) && !staged && !invoice && (
            <Card className="p-5">
              <p className="font-medium">Ready to invoice</p>
              <p className="mt-1 text-sm text-muted">Issuing an invoice is its own decision. Keel shows you exactly what it will issue first.</p>
              <Button className="mt-4" onClick={() => stage.mutate()} disabled={stage.isPending}>Prepare invoice</Button>
              <ErrorNote error={stage.error} />
            </Card>
          )}
          {staged && (
            <div className="overflow-hidden rounded-xl border-2 border-ink">
              <div className="bg-ink px-5 py-3 text-bg">
                <p className="text-xs uppercase tracking-wider opacity-70">Approval needed · issue invoice</p>
                <p className="mt-1 font-medium">{staged.summary.text}</p>
              </div>
              <div className="flex gap-2 bg-surface p-5">
                <Button variant="approve" onClick={() => approveAndIssue.mutate()} disabled={approveAndIssue.isPending}>Approve and issue</Button>
                <Button variant="ghost" onClick={() => setStaged(null)}>Not now</Button>
              </div>
              <div className="bg-surface px-5 pb-4"><ErrorNote error={approveAndIssue.error} /></div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
