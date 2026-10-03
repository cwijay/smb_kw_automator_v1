"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ApprovalCard } from "@/components/review/ApprovalCard";
import { FieldPanel } from "@/components/review/FieldPanel";
import { PageViewer } from "@/components/review/PageViewer";
import { Card, ErrorNote, Pill, STATUS_TEXT, statusTone } from "@/components/ui";
import { detail, unwrap, type DocumentOut } from "@/lib/api";
import { canEdit, useMe } from "@/lib/hooks";

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const me = useMe();
  const [active, setActive] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["document", id],
    queryFn: () => unwrap(detail({ path: { document_id: id } })),
    refetchInterval: (query) => (["uploaded", "processing"].includes(query.state.data?.document.status ?? "") ? 1200 : false),
  });

  if (q.error) return <ErrorNote error={q.error} />;
  if (!q.data) return <p className="text-sm text-muted">Loading…</p>;
  const { document: doc, pages, fields, checks, approval, engine, cost_usd } = q.data;
  const reading = ["uploaded", "processing"].includes(doc.status);
  const flagged = fields.filter((f) => f.status === "unreadable" || (f.status === "read" && f.confidence < 0.75)).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href="/" className="text-sm text-muted hover:text-ink">← Desk</Link>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{doc.filename}</h1>
          <p className="mt-1 text-sm text-muted">
            {engine ? `Read by ${engine}` : "Reading"} · {pages.length} page(s) · AI cost USD {cost_usd.toFixed(4)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {flagged > 0 && <Pill tone="carbon">{flagged} field(s) to check</Pill>}
          <Pill tone={statusTone(doc.run_status === "waiting_approval" ? "waiting_approval" : doc.status)}>
            {STATUS_TEXT[doc.run_status === "waiting_approval" ? "waiting_approval" : doc.status] ?? doc.status}
          </Pill>
        </div>
      </div>

      {doc.error && <ErrorNote error={new Error(`Keel could not read this document: ${doc.error}`)} />}
      {reading && <div className="processing h-2 rounded-full" aria-label="Reading the document" />}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <div className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          {pages.map((p) => (
            <PageViewer key={p.id} documentId={doc.id} page={p} fields={fields} activeId={active} onSelect={setActive} />
          ))}
          <p className="text-xs text-muted">
            <span className="mr-3 inline-block h-2.5 w-2.5 rounded-sm border-2 border-inkblue align-middle" /> read
            <span className="ml-4 mr-1 inline-block h-2.5 w-2.5 rounded-sm border-2 border-carbon bg-carbon/30 align-middle" /> check this
            <span className="ml-4 mr-1 inline-block h-2.5 w-2.5 rounded-sm border-2 border-ledger align-middle" /> fixed by you
          </p>
        </div>
        <div className="space-y-5">
          {fields.length > 0 && (
            <Card className="p-5">
              <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">What Keel read</h2>
              <FieldPanel kind={doc.kind} documentId={doc.id} fields={fields} activeId={active} onSelect={setActive} editable={canEdit(me.data?.role)} />
            </Card>
          )}
          {checks.length > 0 && (
            <Card className="p-5">
              <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-muted">Checks</h2>
              <ul className="space-y-1.5 text-sm">
                {checks.map((c, i) => (
                  <li key={i} className="flex gap-2">
                    <Pill tone={c.severity === "block" ? "danger" : "carbon"}>{c.severity === "block" ? "must fix" : "check"}</Pill>
                    <span>{String(c.message)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {approval && doc.run_id && approval.status === "pending" && (
            <ApprovalCard key={approval.id} approval={approval} runId={doc.run_id} editable={canEdit(me.data?.role)} />
          )}
          <Recorded doc={doc} />
          {doc.run_status === "cancelled" && (
            <p className="rounded-lg bg-surface-2 px-4 py-3 text-sm text-muted">This document is closed. It was rejected, so nothing was recorded from it.</p>
          )}
        </div>
      </div>
    </div>
  );
}

/** What approving this document wrote, with a link to it. Stays after refetches, unlike a toast. */
function Recorded({ doc }: { doc: DocumentOut }) {
  const r = (doc.result ?? {}) as { batch_id?: string; reading_ids?: string[] };
  const done = doc.order_id
    ? { title: "Order created.", href: `/orders/${doc.order_id}`, link: "Open the order" }
    : r.batch_id
      ? { title: "Batch signed off.", href: `/production/${r.batch_id}`, link: "Open the batch record" }
      : r.reading_ids
        ? { title: `${r.reading_ids.length} HACCP reading(s) verified.`, href: "/food-safety", link: "Open food safety" }
        : null;
  if (!done) return null;
  return (
    <div className="rounded-xl border border-ledger bg-ledger-soft p-5">
      <p className="font-semibold text-ledger">{done.title}</p>
      <p className="mt-1 text-sm">It is recorded with your approval and links back to this page.</p>
      <Link href={done.href} className="mt-3 inline-block text-sm font-medium underline underline-offset-4">
        {done.link} →
      </Link>
    </div>
  );
}
