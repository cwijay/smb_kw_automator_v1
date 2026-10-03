"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { GateFrame, useDecide, Warnings, type Summary } from "@/components/review/Gate";
import { Button, Pill, Select } from "@/components/ui";
import { listCustomers, listProducts, unwrap, type ApprovalOut } from "@/lib/api";
import { money } from "@/lib/format";

type Line = {
  path: string;
  description: string | null;
  product_id: string | null;
  product_name?: string;
  sku?: string;
  quantity: string;
  unit?: string;
  unit_price?: string;
  price_source?: string;
  line_total?: string;
};
type Proposal = {
  currency: string;
  customer: { id: string; name: string; matched_by: string } | null;
  customer_as_written: string | null;
  delivery_date: string | null;
  lines: Line[];
  held: { path: string; description: string | null; reason: string }[];
  blocks: string[];
  total: string;
  paper_total: string | null;
  warnings: string[];
};

/** Order gate: customer, priced lines, held lines. The approval is bound to this exact payload. */
export function OrderApproval({ approval, runId, editable }: { approval: ApprovalOut; runId: string; editable: boolean }) {
  const p = approval.proposal as unknown as Proposal;
  const s = approval.summary as unknown as Summary;
  const needsPick = !p.customer || p.lines.some((l) => !l.product_id);
  const customers = useQuery({ queryKey: ["customers"], queryFn: () => unwrap(listCustomers()), enabled: needsPick });
  const products = useQuery({ queryKey: ["products"], queryFn: () => unwrap(listProducts()), enabled: needsPick });
  const [customerId, setCustomerId] = useState("");
  const [linePicks, setLinePicks] = useState<Record<string, string>>({});

  const act = useDecide(runId);

  const paperDiffers = p.paper_total !== null && Number(p.paper_total) !== Number(p.total);
  return (
    <GateFrame label="create order" summary={s} approveLabel="Approve and create order" editable={editable} act={act}>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">Customer</span>
        {p.customer ? (
          <>
            <span className="font-medium">{p.customer.name}</span>
            <Pill tone="blue">{p.customer.matched_by === "owner" ? "picked by you" : `written “${p.customer_as_written}”`}</Pill>
          </>
        ) : (
          <Pill tone="carbon">“{p.customer_as_written ?? "unreadable"}” is not a customer yet</Pill>
        )}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted">
            <th className="pb-1 font-normal">Product</th>
            <th className="pb-1 text-right font-normal">Qty</th>
            <th className="pb-1 text-right font-normal">Price</th>
            <th className="pb-1 text-right font-normal">Total</th>
          </tr>
        </thead>
        <tbody>
          {p.lines.map((l) => (
            <tr key={l.path} className="border-t border-line">
              <td className="py-1.5">
                {l.product_id ? (
                  <>
                    {l.product_name} <span className="text-xs text-muted">{l.sku}</span>
                  </>
                ) : (
                  <span className="text-danger">“{l.description}” · no matching product</span>
                )}
              </td>
              <td className="num py-1.5 text-right">{Number(l.quantity)}</td>
              <td className="num py-1.5 text-right">
                {l.unit_price ? money(l.unit_price, p.currency) : "—"}
                {l.price_source && <p className="text-[11px] text-muted">{l.price_source === "customer_price_list" ? "their price list" : "catalog price"}</p>}
              </td>
              <td className="num py-1.5 text-right">{l.line_total ? money(l.line_total, p.currency) : "—"}</td>
            </tr>
          ))}
          <tr className="border-t-2 border-ink font-medium">
            <td className="py-2" colSpan={3}>Total to record</td>
            <td className="num py-2 text-right">{money(p.total, p.currency)}</td>
          </tr>
        </tbody>
      </table>
      {paperDiffers && (
        <p className="rounded-lg bg-carbon-soft px-3 py-2 text-sm">
          The paper says <span className="num">{money(p.paper_total, p.currency)}</span>. Keel uses your price list, so the recorded total differs. Check before approving.
        </p>
      )}
      {p.held.length > 0 && (
        <div className="text-sm">
          <p className="text-xs uppercase tracking-wide text-muted">Held back, not ordered</p>
          <ul className="mt-1 space-y-0.5">
            {p.held.map((h) => (
              <li key={h.path}>
                <span className="line-through decoration-muted">{h.description ?? "line"}</span> <span className="text-muted">· {h.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <Warnings items={p.warnings} />

      {editable && needsPick && (
        <div className="space-y-2 rounded-lg bg-carbon-soft p-3">
          <p className="text-sm font-medium">Keel won&apos;t guess. Pick the right records:</p>
          {!p.customer && (
            <Select id="pick_customer" value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
              <option value="">Choose the customer…</option>
              {customers.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          )}
          {p.lines.filter((l) => !l.product_id).map((l) => {
            const idx = l.path.match(/\d+/)?.[0] ?? "";
            return (
              <Select key={l.path} id={`pick_${idx}`} value={linePicks[idx] ?? ""} onChange={(e) => setLinePicks({ ...linePicks, [idx]: e.target.value })}>
                <option value="">“{l.description}” is which product?</option>
                {products.data?.map((pr) => <option key={pr.id} value={pr.id}>{pr.name} ({pr.sku})</option>)}
              </Select>
            );
          })}
          <Button variant="ghost" onClick={() => act.mutate({ action: "revise", customer_id: customerId || null, line_products: linePicks })} disabled={act.isPending}>Update the proposal</Button>
        </div>
      )}
    </GateFrame>
  );
}
