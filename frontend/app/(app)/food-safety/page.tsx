"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Button, Card, Empty, ErrorNote, Input, Label, PageTitle, Pill } from "@/components/ui";
import { createCcp, listCcps, listReadings, unwrap, type CcpOut } from "@/lib/api";
import { day } from "@/lib/format";
import { isAdmin, useMe } from "@/lib/hooks";

const TONE = { read: "ledger", missing: "carbon", out_of_range: "danger" } as const;
const TEXT: Record<string, string> = { read: "within limit", missing: "missing", out_of_range: "out of range" };

function limit(c: CcpOut) {
  const lo = c.min_value != null ? `≥ ${Number(c.min_value)}` : "";
  const hi = c.max_value != null ? `≤ ${Number(c.max_value)}` : "";
  return `${[lo, hi].filter(Boolean).join(" and ")} ${c.unit}`;
}

export default function FoodSafetyPage() {
  const me = useMe();
  const ccps = useQuery({ queryKey: ["ccps"], queryFn: () => unwrap(listCcps()) });
  const readings = useQuery({ queryKey: ["readings"], queryFn: () => unwrap(listReadings()) });
  const flagged = readings.data?.filter((r) => r.status !== "read").length ?? 0;

  return (
    <>
      <PageTitle title="Food safety" sub="Critical control points and every verified HACCP reading. A blank reading is recorded as missing, never as passed.">
        <a href="/api/haccp/binder.pdf" target="_blank" rel="noreferrer" className="rounded-lg border border-line bg-surface px-3.5 py-2 text-sm font-medium hover:bg-surface-2">
          Inspection binder (PDF)
        </a>
      </PageTitle>
      <div className="grid gap-6 lg:grid-cols-[1fr_1.6fr]">
        <div className="space-y-4">
          <Card className="p-5">
            <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">Critical control points</h2>
            {ccps.data?.length === 0 && <p className="text-sm text-muted">None yet. HACCP logs can&apos;t be verified until these are set.</p>}
            <ul className="divide-y divide-line text-sm">
              {ccps.data?.map((c) => (
                <li key={c.id} className="flex items-baseline justify-between gap-3 py-2">
                  <span>
                    {c.name}
                    {!!c.aliases?.length && <span className="block text-xs text-muted">also “{c.aliases.join("”, “")}”</span>}
                  </span>
                  <span className="num shrink-0 text-muted">{limit(c)}</span>
                </li>
              ))}
            </ul>
          </Card>
          {isAdmin(me.data?.role) && <NewCcp />}
        </div>
        <Card className="overflow-x-auto">
          <div className="flex items-center justify-between px-4 pt-4">
            <h2 className="text-sm font-medium uppercase tracking-wide text-muted">Readings · last 90 days</h2>
            {flagged > 0 && <Pill tone="carbon">{flagged} needed a corrective action</Pill>}
          </div>
          {readings.data?.length === 0 && (
            <div className="p-4"><Empty title="No verified readings yet">Choose “HACCP logs” on the Desk and drop a log sheet.</Empty></div>
          )}
          {!!readings.data?.length && (
            <table className="mt-2 w-full min-w-[40rem] text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 font-normal">When</th>
                  <th className="px-4 py-2 font-normal">Control point</th>
                  <th className="px-4 py-2 text-right font-normal">Value</th>
                  <th className="px-4 py-2 font-normal">Status</th>
                  <th className="px-4 py-2 font-normal">Corrective action</th>
                </tr>
              </thead>
              <tbody>
                {readings.data.map((r) => (
                  <tr key={r.id} className="border-t border-line align-top">
                    <td className="px-4 py-2 whitespace-nowrap">
                      {day(r.recorded_on)} <span className="text-muted">{r.time}</span>
                      {r.batch_number && <span className="block text-xs text-muted">batch {r.batch_number}</span>}
                    </td>
                    <td className="px-4 py-2">{r.ccp}</td>
                    <td className="num whitespace-nowrap px-4 py-2 text-right">{r.value !== null ? `${Number(r.value)} ${r.unit ?? ""}` : "—"}</td>
                    <td className="px-4 py-2"><Pill tone={TONE[r.status as keyof typeof TONE] ?? "neutral"}>{TEXT[r.status] ?? r.status}</Pill></td>
                    <td className="px-4 py-2">
                      {r.corrective_action ?? ""}
                      {r.source_document_id && (
                        <Link href={`/documents/${r.source_document_id}`} className="block text-xs text-muted underline-offset-2 hover:underline">original log</Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>
    </>
  );
}

function NewCcp() {
  const qc = useQueryClient();
  const [f, setF] = useState({ name: "", min: "", max: "", unit: "F", aliases: "" });
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        createCcp({
          body: {
            name: f.name.trim(),
            min_value: f.min || null,
            max_value: f.max || null,
            unit: f.unit.trim(),
            aliases: f.aliases.split(",").map((a) => a.trim()).filter(Boolean),
          },
        }),
      ),
    onSuccess: async () => {
      setF({ name: "", min: "", max: "", unit: "F", aliases: "" });
      await qc.invalidateQueries({ queryKey: ["ccps"] });
    },
  });
  return (
    <Card className="p-5">
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">Add a control point</h2>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <label className="block"><Label>Name</Label><Input id="ccp_name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Fill temperature" /></label>
        <div className="grid grid-cols-3 gap-2">
          <label><Label>Min</Label><Input id="ccp_min" inputMode="decimal" value={f.min} onChange={(e) => setF({ ...f, min: e.target.value })} /></label>
          <label><Label>Max</Label><Input id="ccp_max" inputMode="decimal" value={f.max} onChange={(e) => setF({ ...f, max: e.target.value })} /></label>
          <label><Label>Unit</Label><Input id="ccp_unit" required value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} /></label>
        </div>
        <label className="block"><Label hint="comma separated">Also written as</Label><Input value={f.aliases} onChange={(e) => setF({ ...f, aliases: e.target.value })} placeholder="fill temp, FT" /></label>
        <ErrorNote error={save.error} />
        <Button disabled={save.isPending}>Add control point</Button>
      </form>
    </Card>
  );
}
