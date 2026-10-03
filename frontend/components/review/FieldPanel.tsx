"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { useState } from "react";
import { Pill } from "@/components/ui";
import { correctField, unwrap, type FieldOut } from "@/lib/api";

const HEADER = ["customer_name", "order_number", "order_date", "delivery_date", "total_written"];
const HEADER_LABEL: Record<string, string> = {
  customer_name: "Customer",
  order_number: "Order no.",
  order_date: "Order date",
  delivery_date: "Deliver",
  total_written: "Total on paper",
};
const LINE_COLS = ["description", "quantity", "unit_price", "line_total"];

function Confidence({ f, low }: { f: FieldOut; low: number }) {
  if (f.status === "corrected") return <Pill tone="ledger">fixed by you</Pill>;
  if (f.status === "unreadable") return <Pill tone="carbon">couldn&apos;t read</Pill>;
  if (f.status === "blank") return <Pill>blank</Pill>;
  return <Pill tone={f.confidence < low ? "carbon" : "blue"}>{Math.round(f.confidence * 100)}%</Pill>;
}

function Value({
  f,
  documentId,
  active,
  editable,
  onSelect,
  low,
}: {
  f: FieldOut;
  documentId: string;
  active: boolean;
  editable: boolean;
  onSelect: (id: string) => void;
  low: number;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(f.value ?? ""));
  const save = useMutation({
    mutationFn: () =>
      unwrap(correctField({ path: { document_id: documentId, field_id: f.id }, body: { value: draft === "" ? null : draft } })),
    onSuccess: async () => {
      setEditing(false);
      await qc.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });
  const needs = f.status === "unreadable" || (f.status === "read" && f.confidence < low);

  if (editing) {
    return (
      <form
        className="flex gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <input
          autoFocus
          id={`edit_${f.id}`}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="num w-full min-w-0 rounded-md border border-inkblue bg-surface px-2 py-1 text-sm"
        />
        <button className="rounded-md bg-ink px-2 text-xs text-bg" disabled={save.isPending}>Save</button>
        <button type="button" className="px-1 text-xs text-muted" onClick={() => setEditing(false)}>✕</button>
      </form>
    );
  }
  return (
    <button
      type="button"
      onMouseEnter={() => onSelect(f.id)}
      onFocus={() => onSelect(f.id)}
      onClick={() => editable && setEditing(true)}
      className={clsx(
        "group flex w-full min-w-0 items-center justify-between gap-2 rounded-md px-2 py-1 text-left",
        active && "bg-inkblue-soft",
        needs && !active && "bg-carbon-soft",
        editable && "hover:ring-1 hover:ring-inkblue/40",
      )}
    >
      <span className={clsx("min-w-0 truncate", f.value === null ? "text-muted italic" : "font-hand text-xl leading-6")}>
        {f.value === null ? (f.status === "unreadable" ? "unreadable" : "—") : String(f.value)}
      </span>
      {editable && <span className="text-xs text-muted opacity-0 group-hover:opacity-100">edit</span>}
    </button>
  );
}

export function FieldPanel({
  documentId,
  fields,
  activeId,
  onSelect,
  editable,
  lowConfidence = 0.75,
}: {
  documentId: string;
  fields: FieldOut[];
  activeId: string | null;
  onSelect: (id: string) => void;
  editable: boolean;
  lowConfidence?: number;
}) {
  const byPath = new Map(fields.map((f) => [f.path, f]));
  const lineCount = Math.max(-1, ...fields.map((f) => Number(f.path.match(/^lines\[(\d+)\]/)?.[1] ?? -1))) + 1;
  const common = { documentId, onSelect, editable, low: lowConfidence };

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-x-2 gap-y-1">
        {HEADER.map((p) => {
          const f = byPath.get(p);
          if (!f) return null;
          return (
            <div key={p} className="contents">
              <dt className="text-xs text-muted">{HEADER_LABEL[p]}</dt>
              <dd className="min-w-0"><Value f={f} active={activeId === f.id} {...common} /></dd>
              <dd><Confidence f={f} low={lowConfidence} /></dd>
            </div>
          );
        })}
      </dl>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[30rem] text-sm">
          <thead>
            <tr className="text-left text-xs text-muted">
              <th className="pb-1 font-normal">Item as written</th>
              <th className="pb-1 font-normal">Qty</th>
              <th className="pb-1 font-normal">Price</th>
              <th className="pb-1 font-normal">Amount</th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: lineCount }, (_, i) => (
              <tr key={i} className="border-t border-line align-top">
                {LINE_COLS.map((c) => {
                  const f = byPath.get(`lines[${i}].${c}`);
                  return (
                    <td key={c} className={clsx("py-1 pr-1", c === "description" ? "w-1/2" : "w-1/6")}>
                      {f && <Value f={f} active={activeId === f.id} {...common} />}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
