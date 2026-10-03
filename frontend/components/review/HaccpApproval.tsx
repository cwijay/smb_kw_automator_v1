"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { GateFrame, useDecide, Warnings, type Summary } from "@/components/review/Gate";
import { Button, Input, Pill, Select } from "@/components/ui";
import { listCcps, unwrap, type ApprovalOut } from "@/lib/api";

type Reading = {
  path: string;
  ccp_as_written: string | null;
  ccp_id: string | null;
  ccp_name: string | null;
  limit: string | null;
  value: string | null;
  unit: string | null;
  time: string | null;
  initials: string | null;
  status: "read" | "missing" | "out_of_range";
  corrective_action: string | null;
};
type Proposal = { batch_number: string | null; log_date: string | null; operator: string | null; readings: Reading[]; warnings: string[] };

const STATUS: Record<Reading["status"], { tone: "ledger" | "carbon" | "danger"; text: string }> = {
  read: { tone: "ledger", text: "within limit" },
  missing: { tone: "carbon", text: "missing" },
  out_of_range: { tone: "danger", text: "out of range" },
};

/** HACCP verification: a blank reading is missing, never passed; every miss needs a written corrective action. */
export function HaccpApproval({ approval, runId, editable }: { approval: ApprovalOut; runId: string; editable: boolean }) {
  const p = approval.proposal as unknown as Proposal;
  const s = approval.summary as unknown as Summary;
  const act = useDecide(runId);
  const unmatched = p.readings.some((r) => !r.ccp_id);
  const ccps = useQuery({ queryKey: ["ccps"], queryFn: () => unwrap(listCcps()), enabled: unmatched });
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [actions, setActions] = useState<Record<string, string>>({});
  const idx = (r: Reading) => r.path.match(/\d+/)?.[0] ?? "";
  const needsInput = p.readings.some((r) => !r.ccp_id || (r.status !== "read" && !r.corrective_action));

  return (
    <GateFrame label="verify HACCP log" summary={s} approveLabel="Verify and record readings" editable={editable} act={act}>
      <ol className="space-y-2">
        {p.readings.map((r) => {
          const i = idx(r);
          const st = STATUS[r.status];
          return (
            <li key={r.path} className={`rounded-lg border p-3 text-sm ${r.status === "read" ? "border-line" : "border-carbon bg-carbon-soft/50"}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-medium">{r.ccp_name ?? `“${r.ccp_as_written ?? "unreadable"}”`}</span>
                  {r.limit && <span className="ml-2 text-xs text-muted">limit {r.limit}</span>}
                </div>
                <div className="flex items-center gap-2">
                  <span className="num font-hand text-xl">{r.value !== null ? `${Number(r.value)} ${r.unit ?? ""}` : "blank"}</span>
                  <Pill tone={st.tone}>{st.text}</Pill>
                </div>
              </div>
              <p className="mt-0.5 text-xs text-muted">
                {r.time ?? "no time"} · {r.initials ?? p.operator ?? "no initials"}
              </p>
              {r.corrective_action && <p className="mt-1 text-sm">Corrective action: {r.corrective_action}</p>}
              {editable && !r.ccp_id && (
                <Select id={`ccp_${i}`} className="mt-2" value={picks[i] ?? ""} onChange={(e) => setPicks({ ...picks, [i]: e.target.value })}>
                  <option value="">Which control point is this?</option>
                  {ccps.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </Select>
              )}
              {editable && r.status !== "read" && !r.corrective_action && (
                <Input
                  id={`action_${i}`}
                  className="mt-2"
                  placeholder="What was done about it? e.g. held the batch and re-checked at 169 F"
                  value={actions[i] ?? ""}
                  onChange={(e) => setActions({ ...actions, [i]: e.target.value })}
                />
              )}
            </li>
          );
        })}
      </ol>
      <Warnings items={p.warnings} />
      {editable && needsInput && (
        <Button
          variant="ghost"
          disabled={act.isPending}
          onClick={() =>
            act.mutate({
              action: "revise",
              line_ccps: Object.fromEntries(Object.entries(picks).filter(([, v]) => v)),
              corrective_actions: Object.fromEntries(Object.entries(actions).filter(([, v]) => v.trim())),
            })
          }
        >
          Update the log
        </Button>
      )}
    </GateFrame>
  );
}
