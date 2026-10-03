"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { AskPanel } from "@/components/ask/AskPanel";
import { Wordmark } from "@/components/shell/AuthFrame";
import { dashboard, logout, switchOrg, unwrap } from "@/lib/api";
import { useMe } from "@/lib/hooks";

const NAV = [
  { href: "/", label: "Desk" },
  { href: "/orders", label: "Orders" },
  { href: "/invoices", label: "Invoices" },
  { href: "/production", label: "Production" },
  { href: "/food-safety", label: "Food safety" },
  { href: "/trace", label: "Trace" },
  { href: "/catalog", label: "Catalog" },
  { href: "/team", label: "Team" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const meQ = useMe();
  const dash = useQuery({ queryKey: ["dashboard"], queryFn: () => unwrap(dashboard()), refetchInterval: 15_000 });
  const [askOpen, setAskOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setAskOpen((v) => !v);
      }
      if (e.key === "Escape") setAskOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (meQ.isLoading) return <div className="p-10 text-sm text-muted">Opening your desk…</div>;
  if (!meQ.data) return null;
  const user = meQ.data;
  const attention = (dash.data?.to_review ?? 0) + (dash.data?.pending_approvals ?? 0);

  async function change(orgId: string) {
    await unwrap(switchOrg({ path: { org_id: orgId } }));
    await qc.invalidateQueries();
    router.push("/");
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-surface px-3 py-5 md:flex">
        <Link href="/" className="px-2"><Wordmark className="text-lg" /></Link>
        <div className="mt-5 px-2">
          <p className="truncate text-sm font-medium">{user.org_name}</p>
          {user.orgs.length > 1 && (
            <select
              aria-label="Switch business"
              className="mt-1 w-full rounded-md border border-line bg-surface px-2 py-1 text-xs"
              value={user.org_id}
              onChange={(e) => change(e.target.value)}
            >
              {user.orgs.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
          )}
        </div>
        <nav className="mt-6 flex flex-col gap-0.5">
          {NAV.map((n) => {
            const active = n.href === "/" ? pathname === "/" || pathname.startsWith("/documents") : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={clsx(
                  "flex items-center justify-between rounded-lg px-3 py-2 text-sm",
                  active ? "bg-surface-2 font-medium text-ink" : "text-muted hover:bg-surface-2 hover:text-ink",
                )}
              >
                {n.label}
                {n.href === "/" && attention > 0 && (
                  <span className="num rounded-full bg-carbon px-1.5 text-xs font-medium text-ink">{attention}</span>
                )}
              </Link>
            );
          })}
        </nav>
        <button
          onClick={() => setAskOpen(true)}
          className="mt-6 flex items-center justify-between rounded-lg border border-line px-3 py-2 text-left text-sm hover:border-inkblue"
        >
          <span>Ask Keel</span>
          <kbd className="num text-xs text-muted">⌘K</kbd>
        </button>
        <div className="mt-auto px-2">
          <button className="w-full text-left" onClick={() => setMenuOpen((v) => !v)}>
            <p className="truncate text-sm">{user.name}</p>
            <p className="truncate text-xs text-muted">{user.role} · {user.email}</p>
          </button>
          {menuOpen && (
            <button
              className="mt-2 text-xs text-danger underline"
              onClick={async () => {
                await logout();
                qc.clear();
                router.push("/login");
              }}
            >
              Sign out
            </button>
          )}
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-surface/90 px-4 py-3 backdrop-blur md:hidden">
          <Wordmark />
          <div className="flex gap-3 text-sm">
            {NAV.slice(0, 3).map((n) => (
              <Link key={n.href} href={n.href} className={pathname === n.href ? "font-medium" : "text-muted"}>{n.label}</Link>
            ))}
            <button onClick={() => setAskOpen(true)} className="text-inkblue">Ask</button>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-8 sm:px-8">{children}</main>
      </div>

      <AskPanel open={askOpen} onClose={() => setAskOpen(false)} />
    </div>
  );
}
