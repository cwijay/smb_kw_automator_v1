"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { GateFrame, useDecide, Warnings, type Summary } from "@/components/review/Gate";
import { Button, Pill, Select } from "@/components/ui";
import { listProducts, unwrap, type ApprovalOut } from "@/lib/api";

type Ingredient = { path: string; ingredient: string | null; lot_code: string | null; quantity: string | null; unit: string | null };
type Proposal = {
  product: { id: string; name: string; sku: string } | null;
  product_as_written: string | null;
  batch_number: string | null;
  made_on: string | null;
  output_lot: string | null;
  quantity: string | null;
  unit: string | null;
  prepared_by: string | null;
  ingredients: Ingredient[];
  missing_lots: string[];
  acknowledged_missing_lots: boolean;
  warnings: string[];
};

/** Batch sign-off: what was made, from which lots. Signed batches are append-only, so this is the last look. */
export function BatchApproval({ approval, runId, editable }: { approval: ApprovalOut; runId: string; editable: boolean }) {
  const p = approval.proposal as unknown as Proposal;
  const s = approval.summary as unknown as Summary;
  const act = useDecide(runId);
  const products = useQuery({ queryKey: ["products"], queryFn: () => unwrap(listProducts()), enabled: !p.product });
  const [productId, setProductId] = useState("");

  return (
    <GateFrame label="sign off batch" summary={s} approveLabel="Sign off batch" editable={editable} act={act}>
      <dl className="grid grid-cols-[7rem_1fr] gap-y-1 text-sm">
        <dt className="text-muted">Product</dt>
        <dd>
          {p.product ? (
            <>
              {p.product.name} <span className="text-xs text-muted">{p.product.sku}</span>
            </>
          ) : (
            <Pill tone="carbon">“{p.product_as_written ?? "unreadable"}” is not a product</Pill>
          )}
        </dd>
        <dt className="text-muted">Output lot</dt>
        <dd className="num font-medium">{p.output_lot ?? <span className="text-danger">none</span>}</dd>
        <dt className="text-muted">Made</dt>
        <dd>
          {p.made_on ?? "date unreadable"}
          {p.quantity && <span className="num"> · {Number(p.quantity)} {p.unit}</span>}
          {p.prepared_by && <span className="text-muted"> · by {p.prepared_by}</span>}
        </dd>
      </dl>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted">
            <th className="pb-1 font-normal">Ingredient</th>
            <th className="pb-1 font-normal">Lot</th>
            <th className="pb-1 text-right font-normal">Qty</th>
          </tr>
        </thead>
        <tbody>
          {p.ingredients.map((i) => (
            <tr key={i.path} className="border-t border-line">
              <td className="py-1.5">{i.ingredient ?? "unreadable"}</td>
              <td className="num py-1.5">{i.lot_code ?? <Pill tone="carbon">no lot code</Pill>}</td>
              <td className="num py-1.5 text-right">{i.quantity !== null ? `${Number(i.quantity)} ${i.unit ?? ""}` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <Warnings items={p.warnings} />
      {editable && (!p.product || (p.missing_lots.length > 0 && !p.acknowledged_missing_lots)) && (
        <div className="space-y-2 rounded-lg bg-carbon-soft p-3 text-sm">
          {!p.product && (
            <Select id="pick_product" value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">“{p.product_as_written}” is which product?</option>
              {products.data?.map((pr) => <option key={pr.id} value={pr.id}>{pr.name} ({pr.sku})</option>)}
            </Select>
          )}
          {!p.product && (
            <Button variant="ghost" disabled={!productId || act.isPending} onClick={() => act.mutate({ action: "revise", product_id: productId })}>
              Use this product
            </Button>
          )}
          {p.missing_lots.length > 0 && !p.acknowledged_missing_lots && (
            <div className="space-y-2">
              <p>
                Correct the lot codes in “What Keel read” if they are on the sheet. If they really weren&apos;t written down, record that this batch
                can&apos;t be traced through {p.missing_lots.join(", ")}.
              </p>
              <Button variant="ghost" id="ack_missing" disabled={act.isPending} onClick={() => act.mutate({ action: "revise", acknowledge_missing_lots: true })}>
                Record as untraceable
              </Button>
            </div>
          )}
        </div>
      )}
      {p.acknowledged_missing_lots && p.missing_lots.length > 0 && (
        <p className="text-sm text-muted">Recorded as a trace gap: {p.missing_lots.join(", ")}. It will show on every trace through this batch.</p>
      )}
    </GateFrame>
  );
}
