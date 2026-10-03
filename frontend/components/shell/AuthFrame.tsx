import type { ReactNode } from "react";

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`inline-flex items-baseline gap-1.5 font-semibold tracking-tight ${className}`}>
      <span aria-hidden className="inline-block h-3 w-3 translate-y-px rotate-45 rounded-[3px] bg-inkblue" />
      Keel
    </span>
  );
}

export function AuthFrame({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <main className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <aside className="relative hidden overflow-hidden bg-ink p-12 text-bg lg:flex lg:flex-col lg:justify-between">
        <Wordmark className="text-xl" />
        <div className="max-w-md">
          <p className="font-hand text-4xl leading-tight text-carbon">11 Malai Kulfi · 4.50 · 49.50</p>
          <p className="mt-6 text-3xl font-semibold leading-snug tracking-tight">
            Photograph the order pad.
            <br />
            Keel turns it into orders, invoices and records you can trust.
          </p>
          <p className="mt-4 text-sm opacity-70">
            Every number links back to where it was written. Nothing is created, sent or posted without your yes.
          </p>
        </div>
        <p className="text-xs opacity-50">The back office for small food producers</p>
      </aside>
      <section className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm">
          <Wordmark className="mb-8 text-xl lg:hidden" />
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {sub && <p className="mt-1 text-sm text-muted">{sub}</p>}
          <div className="mt-8">{children}</div>
        </div>
      </section>
    </main>
  );
}
