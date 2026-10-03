"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorNote, Input, Label } from "@/components/ui";
import { commitCorrection, decideApproval, stageCorrection, unwrap, type BatchOut } from "@/lib/api";

type Row = { ingredient: string; lot_code: string; quantity: string; unit: string };

/** Correct a signed batch: edit, then approve exactly the listed changes. The old version stays on record. */
export function CorrectBatch({ batch, onCancel }: { batch: BatchOut; onCancel: () => void }) {
  const qc = useQueryClient();
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [rows, setRows] = useState<Row[]>(
    (batch.inputs ?? []).map((i) => ({
      ingredient: i.ingredient,
      lot_code: i.lot_code ?? "",
      quantity: i.quantity == null ? "" : String(Number(i.quantity)),
      unit: i.unit ?? "",
    })),
  );
  const [staged, setStaged] = useState<{ approval_id: string; summary: { text: string; changes: string[] } } | null>(null);

  const body = () => ({
    reason: reason.trim(),
    made_on: batch.made_on,
    quantity: batch.quantity,
    unit: batch.unit,
    prepared_by: batch.prepared_by,
    inputs: rows.map((r) => ({ ingredient: r.ingredient, lot_code: r.lot_code || null, quantity: r.quantity || null, unit: r.unit || null })),
  });
  const stage = useMutation({
    mutationFn: () => unwrap(stageCorrection({ path: { batch_id: batch.id }, body: body() })),
    onSuccess: (r) => setStaged(r as never),
  });
  const approve = useMutation({
    mutationFn: async () => {
      await unwrap(decideApproval({ path: { approval_id: staged!.approval_id }, body: { approve: true } }));
      return unwrap(commitCorrection({ path: { batch_id: batch.id }, body: { ...body(), approval_id: staged!.approval_id } }));
    },
    onSuccess: async (r) => {
      await qc.invalidateQueries();
      router.push(`/production/${r.batch_id}`);
    },
  });
  const set = (i: number, k: keyof Row, v: string) => {
    setStaged(null); // any edit needs a fresh approval
    setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  };

  if (staged) {
    return (
      <div className="overflow-hidden rounded-xl border-2 border-ink bg-surface">
        <div className="bg-ink px-5 py-3 text-bg">
          <p className="text-xs uppercase tracking-wider opacity-70">Approval needed · correct batch</p>
          <p className="mt-1 font-medium leading-snug">{staged.summary.text}</p>
        </div>
        <div className="space-y-3 p-5 text-sm">
          <ul className="space-y-1">
            {staged.summary.changes.map((c) => <li key={c} className="num">• {c}</li>)}
          </ul>
          <p className="text-muted">Reason: {reason}</p>
          <ErrorNote error={approve.error} />
          <div className="flex gap-2">
            <Button variant="approve" id="approve_correction" disabled={approve.isPending} onClick={() => approve.mutate()}>
              Approve correction
            </Button>
            <Button variant="ghost" onClick={() => setStaged(null)}>Back to editing</Button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <form
      className="space-y-3 rounded-xl border border-carbon bg-carbon-soft/40 p-5"
      onSubmit={(e) => {
        e.preventDefault();
        stage.mutate();
      }}
    >
      <p className="text-sm font-medium">Correct this record</p>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr><th className="pb-1 font-normal">Ingredient</th><th className="pb-1 font-normal">Lot</th><th className="pb-1 font-normal">Qty</th><th className="pb-1 font-normal">Unit</th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td className="py-1 pr-2">{r.ingredient}</td>
              <td className="py-1 pr-2"><Input id={`fix_lot_${i}`} className="num" value={r.lot_code} placeholder="not written down" onChange={(e) => set(i, "lot_code", e.target.value)} /></td>
              <td className="py-1 pr-2"><Input className="num" inputMode="decimal" value={r.quantity} onChange={(e) => set(i, "quantity", e.target.value)} /></td>
              <td className="py-1"><Input value={r.unit} onChange={(e) => set(i, "unit", e.target.value)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <label className="block">
        <Label hint="kept on the record">Why is this being corrected?</Label>
        <Input id="fix_reason" required minLength={5} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. rose water lot was on the jar label" />
      </label>
      <ErrorNote error={stage.error} />
      <div className="flex gap-2">
        <Button disabled={stage.isPending || reason.trim().length < 5}>Review the changes</Button>
        <Button type="button" variant="quiet" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}
