"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { getProfile, unwrap } from "@/lib/api";

/** Setup checklist, computed from real records. One next step is highlighted; it disappears when done. */
export function Onboarding() {
  const q = useQuery({ queryKey: ["profile"], queryFn: () => unwrap(getProfile()) });
  const steps = q.data?.onboarding ?? [];
  const next = steps.find((s) => !s.done);
  if (!q.data || !next) return null;
  const done = steps.filter((s) => s.done).length;
  return (
    <section aria-label="Getting set up" className="rounded-2xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-semibold">Getting set up</h2>
        <span className="num text-sm text-muted">{done} of {steps.length} done</span>
      </div>
      <ol className="mt-3 grid gap-2 sm:grid-cols-5">
        {steps.map((s, i) => (
          <li key={s.key}>
            <Link
              href={s.href}
              className={clsx(
                "block h-full rounded-lg border px-3 py-2 text-sm",
                s.done && "border-ledger/40 bg-ledger-soft text-ledger",
                s.key === next.key && "border-ink bg-ink text-bg",
                !s.done && s.key !== next.key && "border-line text-muted hover:border-inkblue",
              )}
            >
              <span className="num mr-1 text-xs opacity-70">{s.done ? "✓" : i + 1}</span> {s.title}
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
