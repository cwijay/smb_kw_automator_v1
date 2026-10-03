"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Button, ErrorNote } from "@/components/ui";
import { decide, unwrap, type DecisionIn } from "@/lib/api";

export type Summary = { text: string; can_approve: boolean; blocks: string[] };
type Overrides = Omit<DecisionIn, "action">;

/** One decision call for every kind of gate; refreshes everything the commit may have touched. */
export function useDecide(runId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ action, ...overrides }: { action: DecisionIn["action"] } & Overrides) =>
      unwrap(decide({ path: { run_id: runId }, body: { action, ...overrides } })),
    onSuccess: async () => {
      await qc.invalidateQueries();
    },
  });
}

/** The gate frame: says exactly what will be written, lists what blocks it, and holds the two buttons. */
export function GateFrame({
  label,
  summary,
  approveLabel,
  editable,
  act,
  children,
}: {
  label: string;
  summary: Summary;
  approveLabel: string;
  editable: boolean;
  act: ReturnType<typeof useDecide>;
  children: ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-xl border-2 border-ink bg-surface">
      <div className="bg-ink px-5 py-3 text-bg">
        <p className="text-xs uppercase tracking-wider opacity-70">Approval needed · {label}</p>
        <p className="mt-1 font-medium leading-snug">{summary.text}</p>
      </div>
      <div className="space-y-4 p-5">
        {children}
        {summary.blocks.length > 0 && (
          <ul className="space-y-1 text-sm text-danger">
            {summary.blocks.map((b) => <li key={b}>• {b}</li>)}
          </ul>
        )}
        <ErrorNote error={act.error} />
        {editable ? (
          <div className="flex flex-wrap gap-2 pt-1">
            <Button variant="approve" disabled={!summary.can_approve || act.isPending} onClick={() => act.mutate({ action: "approve" })}>
              {approveLabel}
            </Button>
            <Button variant="danger" disabled={act.isPending} onClick={() => act.mutate({ action: "reject" })}>Reject</Button>
          </div>
        ) : (
          <p className="text-sm text-muted">Viewers can see this, but only members can approve.</p>
        )}
        <p className="text-xs text-muted">Approving records exactly this. If anything changes afterwards, Keel asks again.</p>
      </div>
    </div>
  );
}

export function Warnings({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <ul className="space-y-1 rounded-lg bg-carbon-soft px-3 py-2 text-sm">
      {items.map((w) => <li key={w}>• {w}</li>)}
    </ul>
  );
}
