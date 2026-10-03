import clsx from "clsx";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "approve" | "danger" | "quiet" }) {
  return (
    <button
      {...props}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-ink text-bg hover:opacity-90",
        variant === "approve" && "bg-ledger text-white hover:opacity-90",
        variant === "danger" && "bg-danger-soft text-danger hover:bg-danger hover:text-white",
        variant === "ghost" && "border border-line bg-surface hover:bg-surface-2",
        variant === "quiet" && "text-muted hover:bg-surface-2 hover:text-ink",
        className,
      )}
    />
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={clsx(
        "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm placeholder:text-muted focus:border-inkblue focus:outline-none",
        props.className,
      )}
    />
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={clsx("w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm focus:border-inkblue", props.className)}
    />
  );
}

export function Label({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted">
      {children}
      {hint && <span className="ml-1 normal-case tracking-normal">· {hint}</span>}
    </span>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={clsx("rounded-xl border border-line bg-surface", className)}>{children}</section>;
}

export function Pill({ tone = "neutral", children }: { tone?: "neutral" | "blue" | "carbon" | "ledger" | "danger"; children: ReactNode }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        tone === "neutral" && "bg-surface-2 text-muted",
        tone === "blue" && "bg-inkblue-soft text-inkblue",
        tone === "carbon" && "bg-carbon-soft text-ink",
        tone === "ledger" && "bg-ledger-soft text-ledger",
        tone === "danger" && "bg-danger-soft text-danger",
      )}
    >
      {children}
    </span>
  );
}

export function PageTitle({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-sm text-muted">{sub}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-2 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="rounded-lg bg-danger-soft px-3 py-2 text-sm text-danger">{(error as Error).message}</p>;
}

export function statusTone(status: string): "neutral" | "blue" | "carbon" | "ledger" | "danger" {
  if (["needs_review", "waiting_approval", "pending", "approved_unbilled"].includes(status)) return "carbon";
  if (["processing", "uploaded", "running"].includes(status)) return "blue";
  if (["processed", "done", "issued", "invoiced", "approved"].includes(status)) return "ledger";
  if (["failed", "cancelled", "rejected"].includes(status)) return "danger";
  return "neutral";
}

export const STATUS_TEXT: Record<string, string> = {
  uploaded: "Queued",
  processing: "Reading…",
  needs_review: "Needs review",
  processed: "Done",
  failed: "Could not read",
  approved: "Not invoiced",
  invoiced: "Invoiced",
  issued: "Issued",
  waiting_approval: "Waiting for you",
};
