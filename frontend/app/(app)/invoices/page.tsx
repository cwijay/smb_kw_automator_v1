"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, Empty, PageTitle, Pill } from "@/components/ui";
import { listInvoices, unwrap } from "@/lib/api";
import { day, money } from "@/lib/format";

export default function InvoicesPage() {
  const q = useQuery({ queryKey: ["invoices"], queryFn: () => unwrap(listInvoices()) });
  return (
    <>
      <PageTitle title="Invoices" sub="Issued from approved orders. Export for your ledger when you're ready.">
        <a className="rounded-lg border border-line bg-surface px-3.5 py-2 text-sm font-medium hover:bg-surface-2" href="/api/invoices/export.csv?format=qbo">QuickBooks CSV</a>
        <a className="rounded-lg border border-line bg-surface px-3.5 py-2 text-sm font-medium hover:bg-surface-2" href="/api/invoices/export.csv?format=xero">Xero CSV</a>
      </PageTitle>
      {q.data?.length === 0 && <Empty title="No invoices yet">Open an order that isn&apos;t invoiced and choose “Prepare invoice”.</Empty>}
      {!!q.data?.length && (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 py-2.5 font-normal">Invoice</th>
                <th className="px-4 py-2.5 font-normal">Customer</th>
                <th className="px-4 py-2.5 font-normal">Issued</th>
                <th className="px-4 py-2.5 font-normal">Due</th>
                <th className="px-4 py-2.5 text-right font-normal">Total</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {q.data.map((i) => (
                <tr key={i.id} className="border-t border-line">
                  <td className="num px-4 py-2.5 font-medium">{i.number}</td>
                  <td className="px-4 py-2.5">{i.customer}</td>
                  <td className="px-4 py-2.5">{day(i.issue_date)}</td>
                  <td className="px-4 py-2.5">{day(i.due_date)}</td>
                  <td className="num px-4 py-2.5 text-right">{money(i.total, i.currency)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <Pill tone="ledger">{i.status}</Pill>{" "}
                    <a href={`/api/invoices/${i.id}/pdf`} target="_blank" rel="noreferrer" className="ml-2 text-sm underline underline-offset-4">PDF</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
