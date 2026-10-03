"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import Link from "next/link";
import { Dropzone } from "@/components/desk/Dropzone";
import { Card, Empty, Pill, STATUS_TEXT, statusTone } from "@/components/ui";
import { activity, dashboard, listDocuments, unwrap } from "@/lib/api";
import { ago, money } from "@/lib/format";
import { canEdit, useMe } from "@/lib/hooks";

function Stat({ label, value, tone, hint }: { label: string; value: string | number; tone?: "carbon"; hint?: string }) {
  return (
    <div className={`min-w-0 rounded-xl border px-4 py-3 ${tone === "carbon" && value !== 0 ? "border-carbon bg-carbon-soft" : "border-line bg-surface"}`}>
      <p className="text-xs text-muted">{label}</p>
      <p className="num mt-1 truncate text-xl font-medium">{value}</p>
      {hint && <p className="mt-0.5 truncate text-xs text-muted">{hint}</p>}
    </div>
  );
}

const KIND_TEXT: Record<string, string> = { order_pad: "Order", batch_sheet: "Batch sheet", haccp_log: "HACCP log" };

const ACTION_TEXT: Record<string, string> = {
  "document.uploaded": "Paper received",
  "document.extracted": "Keel read a document",
  "approval.approved": "You approved",
  "approval.rejected": "Rejected or revised",
  "order.created": "Order created",
  "invoice.issued": "Invoice issued",
  "batch.signed_off": "Batch signed off",
  "haccp.recorded": "HACCP log verified",
  "lot.allocated": "Lot shipped on an order",
  "ccp.created": "Control point added",
  "field.corrected": "Field corrected",
  "customer.created": "Customer added",
  "product.created": "Product added",
  "invite.created": "Teammate invited",
  "invite.accepted": "Teammate joined",
  "org.created": "Business created",
};

export default function DeskPage() {
  const me = useMe();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => unwrap(dashboard()), refetchInterval: 15_000 });
  const docs = useQuery({
    queryKey: ["documents"],
    queryFn: () => unwrap(listDocuments()),
    refetchInterval: (q) => (q.state.data?.some((d) => ["uploaded", "processing"].includes(d.status)) ? 1500 : 15_000),
  });
  const feed = useQuery({ queryKey: ["activity"], queryFn: () => unwrap(activity()), refetchInterval: 15_000 });
  // When documents finish reading, refresh the numbers and the tape straight away.
  const qc = useQueryClient();
  const busy = docs.data?.filter((x) => ["uploaded", "processing"].includes(x.status)).length ?? 0;
  const prevBusy = useRef(busy);
  useEffect(() => {
    if (busy < prevBusy.current) {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["activity"] });
    }
    prevBusy.current = busy;
  }, [busy, qc]);
  const d = dash.data;
  const cur = d?.currency ?? "USD";

  return (
    <div className="space-y-8">
      <div>
        <p className="text-sm text-muted">{new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}</p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Good to see you, {me.data?.name.split(" ")[0]}.</h1>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Waiting for your review" value={d?.to_review ?? "–"} tone="carbon" />
        <Stat label="Approvals pending" value={d?.pending_approvals ?? "–"} tone="carbon" />
        <Stat label="Ordered, not invoiced" value={d ? money(d.unbilled_value, cur) : "–"} hint={d ? `${d.unbilled_orders} order(s)` : undefined} />
        <Stat label="Invoiced, 30 days" value={d ? money(d.invoiced_30d, cur) : "–"} />
        <Stat label="AI cost this month" value={d ? `USD ${Number(d.ai_spend_month_usd).toFixed(4)}` : "–"} hint={d ? `${d.pages_month} pages read` : undefined} />
      </div>

      <Dropzone disabled={!canEdit(me.data?.role)} />

      <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <section>
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">Paper on your desk</h2>
          {docs.data?.length === 0 && <Empty title="Nothing here yet">Drop an order pad, batch sheet or HACCP log above, or run <code>keel seed</code> for demo documents.</Empty>}
          <ul className="space-y-2">
            {docs.data?.map((doc) => {
              const waiting = doc.run_status === "waiting_approval";
              const status = waiting ? "waiting_approval" : doc.status;
              return (
                <li key={doc.id}>
                  <Link
                    href={`/documents/${doc.id}`}
                    className={`flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-4 py-3 hover:border-inkblue ${doc.status === "processing" ? "processing" : ""} ${waiting ? "attention" : ""}`}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{doc.filename}</p>
                      <p className="text-xs text-muted">{KIND_TEXT[doc.kind] ?? "Paper"} · {doc.source === "camera" ? "photo" : "upload"} · {ago(doc.created_at)}{doc.page_count ? ` · ${doc.page_count} page(s)` : ""}</p>
                    </div>
                    <Pill tone={statusTone(status)}>{STATUS_TEXT[status] ?? status}</Pill>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
        <section>
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">Ledger tape</h2>
          <Card className="divide-y divide-line">
            {feed.data?.length === 0 && <p className="px-4 py-6 text-sm text-muted">Activity will appear here.</p>}
            {feed.data?.slice(0, 12).map((a, i) => (
              <div key={i} className="flex items-baseline justify-between gap-3 px-4 py-2.5 text-sm">
                <span className="truncate">{ACTION_TEXT[a.action] ?? a.action}{typeof a.data.number === "string" ? ` · ${a.data.number}` : ""}</span>
                <span className="num shrink-0 text-xs text-muted">{ago(a.at)}</span>
              </div>
            ))}
          </Card>
        </section>
      </div>
    </div>
  );
}
