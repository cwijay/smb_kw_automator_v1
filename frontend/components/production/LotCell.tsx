"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { allocate, listLots, unwrap } from "@/lib/api";

/** Which product lots went out on an order line. This is what makes a forward trace reach the customer. */
export function LotCell({ orderId, lineId, lots, editable }: { orderId: string; lineId: string; lots: string[]; editable: boolean }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const options = useQuery({ queryKey: ["lots", "product"], queryFn: () => unwrap(listLots()), enabled: open });
  const save = useMutation({
    mutationFn: () => unwrap(allocate({ path: { order_id: orderId, line_id: lineId }, body: { lot_code: code.trim() } })),
    onSuccess: async () => {
      setOpen(false);
      setCode("");
      await qc.invalidateQueries({ queryKey: ["order", orderId] });
    },
  });
  return (
    <div className="flex flex-wrap items-center gap-1">
      {lots.map((l) => (
        <Link key={l} href={`/trace?lot=${encodeURIComponent(l)}`} className="num rounded bg-inkblue-soft px-1.5 py-0.5 text-xs text-inkblue">
          {l}
        </Link>
      ))}
      {editable && !open && (
        <button className="text-xs text-muted underline-offset-2 hover:underline" onClick={() => setOpen(true)}>
          + lot
        </button>
      )}
      {open && (
        <form
          className="flex items-center gap-1"
          onSubmit={(e) => {
            e.preventDefault();
            if (code.trim()) save.mutate();
          }}
        >
          <input
            autoFocus
            id={`lot_${lineId}`}
            list={`lots_${lineId}`}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Lot code"
            className="num w-24 rounded border border-inkblue bg-surface px-1.5 py-0.5 text-xs"
          />
          <datalist id={`lots_${lineId}`}>
            {options.data?.filter((o) => o.kind === "product").map((o) => <option key={o.code} value={o.code}>{o.name ?? ""}</option>)}
          </datalist>
          <button className="rounded bg-ink px-1.5 py-0.5 text-xs text-bg" disabled={save.isPending}>Add</button>
          <button type="button" className="text-xs text-muted" onClick={() => setOpen(false)}>✕</button>
          {save.error && <span className="text-xs text-danger">{(save.error as Error).message}</span>}
        </form>
      )}
    </div>
  );
}
