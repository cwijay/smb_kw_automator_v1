"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthFrame } from "@/components/shell/AuthFrame";
import { Button, ErrorNote, Input, Label, Select } from "@/components/ui";
import { signup, unwrap } from "@/lib/api";

const REGIONS = [
  { label: "United States · USD", country: "US", currency: "USD", timezone: "America/New_York" },
  { label: "United Kingdom · GBP", country: "GB", currency: "GBP", timezone: "Europe/London" },
  { label: "Sri Lanka · LKR", country: "LK", currency: "LKR", timezone: "Asia/Colombo" },
];

export default function SignupPage() {
  const router = useRouter();
  const [form, setForm] = useState({ org_name: "", name: "", email: "", password: "", region: 0 });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: k === "region" ? Number(e.target.value) : e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r = REGIONS[form.region];
    try {
      await unwrap(
        signup({
          body: { org_name: form.org_name, name: form.name, email: form.email, password: form.password, country: r.country, currency: r.currency, timezone: r.timezone },
        }),
      );
      router.push("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame title="Create your business" sub="You'll be the owner. Invite your team afterwards.">
      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <Label>Business name</Label>
          <Input id="org_name" required value={form.org_name} onChange={set("org_name")} placeholder="Sweet Spoon Kulfi" />
        </label>
        <label className="block">
          <Label>Your name</Label>
          <Input id="name" required value={form.name} onChange={set("name")} />
        </label>
        <label className="block">
          <Label>Email</Label>
          <Input id="signup_email" type="email" required value={form.email} onChange={set("email")} />
        </label>
        <label className="block">
          <Label hint="at least 10 characters">Password</Label>
          <Input id="signup_password" type="password" minLength={10} required value={form.password} onChange={set("password")} />
        </label>
        <label className="block">
          <Label>Country and currency</Label>
          <Select id="region" value={form.region} onChange={set("region")}>
            {REGIONS.map((r, i) => (
              <option key={r.country} value={i}>{r.label}</option>
            ))}
          </Select>
        </label>
        <ErrorNote error={error} />
        <Button type="submit" className="w-full" disabled={busy}>
          {busy ? "Creating…" : "Create business"}
        </Button>
      </form>
      <p className="mt-8 text-sm text-muted">
        Already have an account? <Link href="/login" className="font-medium text-ink underline underline-offset-4">Sign in</Link>
      </p>
    </AuthFrame>
  );
}
