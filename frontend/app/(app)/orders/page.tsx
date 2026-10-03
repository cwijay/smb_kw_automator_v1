"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Card, Empty, PageTitle, Pill, STATUS_TEXT, statusTone } from "@/components/ui";
import { listOrders, unwrap } from "@/lib/api";
import { day, money } from "@/lib/format";

export default function OrdersPage() {
  const q = useQuery({ queryKey: ["orders"], queryFn: () => unwrap(listOrders()) });
  return (
    <>
      <PageTitle title="Orders" sub="Every order here was approved by a person and links back to its paper." />
      {q.data?.length === 0 && <Empty title="No orders yet">Approve an order on the Desk to see it here.</Empty>}
      {!!q.data?.length && (
        <Card className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 py-2.5 font-normal">Order</th>
                <th className="px-4 py-2.5 font-normal">Customer</th>
                <th className="px-4 py-2.5 font-normal">Deliver</th>
                <th className="px-4 py-2.5 text-right font-normal">Total</th>
                <th className="px-4 py-2.5 font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((o) => (
                <tr key={o.id} className="border-t border-line hover:bg-surface-2">
                  <td className="px-4 py-2.5"><Link href={`/orders/${o.id}`} className="num font-medium underline-offset-4 hover:underline">{o.number}</Link></td>
                  <td className="px-4 py-2.5">{o.customer}</td>
                  <td className="px-4 py-2.5">{day(o.delivery_date)}</td>
                  <td className="num px-4 py-2.5 text-right">{money(o.total, o.currency)}</td>
                  <td className="px-4 py-2.5"><Pill tone={o.status === "approved" ? "carbon" : statusTone(o.status)}>{STATUS_TEXT[o.status] ?? o.status}</Pill></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </>
  );
}
