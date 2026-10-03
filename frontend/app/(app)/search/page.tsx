"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, Suspense, useState } from "react";
import { Button, Card, Empty, ErrorNote, Input, PageTitle, Pill } from "@/components/ui";
import { search, unwrap } from "@/lib/api";

const MATCH: Record<string, { text: string; tone: "blue" | "carbon" | "ledger" }> = {
  words: { text: "exact words", tone: "blue" },
  spelling: { text: "close spelling", tone: "carbon" },
  meaning: { text: "similar meaning", tone: "ledger" },
};
const KIND: Record<string, string> = { order_pad: "Order", batch_sheet: "Batch sheet", haccp_log: "HACCP log" };

export default function SearchPage() {
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading…</p>}>
      <Search />
    </Suspense>
  );
}

/** ts_headline marks hits with <b>…</b>; render those as highlights without trusting any other markup. */
function Snippet({ text }: { text: string }) {
  return (
    <>
      {text.split(/(<b>.*?<\/b>)/g).map((part, i) =>
        part.startsWith("<b>") ? (
          <mark key={i} className="rounded bg-carbon-soft px-0.5 text-ink">{part.slice(3, -4)}</mark>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

function Search() {
  const router = useRouter();
  const q = useSearchParams().get("q") ?? "";
  const [draft, setDraft] = useState(q);
  const [shown, setShown] = useState(q);
  if (shown !== q) {
    setShown(q);
    setDraft(q);
  }
  const r = useQuery({ queryKey: ["search", q], queryFn: () => unwrap(search({ query: { q } })), enabled: q.length >= 2 });

  return (
    <>
      <PageTitle title="Search your paper" sub="Every page Keel has read: orders, batch sheets, HACCP logs. Matches exact words, misspellings and shorthand, and (with an AI key) similar meaning." />
      <form
        className="mb-6 flex max-w-xl gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim().length >= 2) router.push(`/search?q=${encodeURIComponent(draft.trim())}`);
        }}
      >
        <Input id="search_q" autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. pasteurization, Rasoi, rose water" />
        <Button>Search</Button>
      </form>
      <ErrorNote error={r.error} />
      {r.isFetching && <div className="processing h-2 max-w-xl rounded-full" aria-label="Searching" />}
      {r.data?.length === 0 && <Empty title="Nothing matches">Try fewer words, or a name as it was written on the paper.</Empty>}
      {!!r.data?.length && (
        <ol className="max-w-3xl space-y-2">
          {r.data.map((h, i) => (
            <li key={`${h.document_id}-${h.page}-${i}`}>
              <Card className="p-4 hover:border-inkblue">
                <Link href={`/documents/${h.document_id}`} className="block">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-medium">
                      {h.file} <span className="text-sm font-normal text-muted">· {KIND[h.kind] ?? h.kind} · page {h.page}</span>
                    </p>
                    <div className="flex gap-1">
                      {h.matched.map((m) => <Pill key={m} tone={MATCH[m]?.tone ?? "neutral"}>{MATCH[m]?.text ?? m}</Pill>)}
                    </div>
                  </div>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted">
                    <Snippet text={h.snippet} />
                  </p>
                </Link>
              </Card>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
