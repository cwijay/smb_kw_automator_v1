"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthFrame } from "@/components/shell/AuthFrame";
import { Button, ErrorNote, Input, Label } from "@/components/ui";
import { login, magicLink, unwrap } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<{ devLink?: string | null } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await unwrap(login({ body: { email, password } }));
      router.push("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function sendLink() {
    setError(null);
    try {
      const r = await unwrap(magicLink({ body: { email } }));
      setSent({ devLink: r.dev_link });
    } catch (err) {
      setError(err);
    }
  }

  return (
    <AuthFrame title="Sign in" sub="Welcome back to your desk.">
      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <Label>Email</Label>
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block">
          <Label>Password</Label>
          <Input id="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <ErrorNote error={error} />
        <Button type="submit" className="w-full" disabled={busy || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
        <Button type="button" variant="ghost" className="w-full" disabled={!email} onClick={sendLink}>
          Email me a sign-in link
        </Button>
        {sent && (
          <p className="rounded-lg bg-ledger-soft px-3 py-2 text-sm text-ledger">
            If that email has an account, a link is on its way.
            {sent.devLink && (
              <>
                {" "}
                Dev mode: <a className="underline" href={sent.devLink}>open the link</a>.
              </>
            )}
          </p>
        )}
      </form>
      <p className="mt-8 text-sm text-muted">
        New to Keel? <Link href="/signup" className="font-medium text-ink underline underline-offset-4">Create your business</Link>
      </p>
    </AuthFrame>
  );
}
