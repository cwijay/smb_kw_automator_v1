"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, ErrorNote, Input, Label, PageTitle, Select } from "@/components/ui";
import { applyProfile, decideApproval, getProfile, stageProfile, unwrap, type ProfileIn } from "@/lib/api";
import { isAdmin, useMe } from "@/lib/hooks";

type Form = { fiscal_year_end: string; books_export: string; ledger: string; allergens: string; notes: string };

function toBody(f: Form): ProfileIn {
  return {
    fiscal_year_end: f.fiscal_year_end || null,
    books_export: (f.books_export || null) as ProfileIn["books_export"],
    ledger: (f.ledger || null) as ProfileIn["ledger"],
    allergens: f.allergens ? f.allergens.split(",").map((a) => a.trim()).filter(Boolean) : null,
    notes: f.notes || null,
  };
}

export default function SettingsPage() {
  const me = useMe();
  const q = useQuery({ queryKey: ["profile"], queryFn: () => unwrap(getProfile()) });
  if (!q.data) return <p className="text-sm text-muted">Loading…</p>;
  return (
    <>
      <PageTitle title="Business profile" sub="What Keel works from: your year end, where your books live, what you handle. Ask Keel reads this too." />
      <ProfileForm key={JSON.stringify(q.data.profile)} profile={q.data.profile} editable={isAdmin(me.data?.role)} />
    </>
  );
}

function ProfileForm({ profile, editable }: { profile: Record<string, unknown>; editable: boolean }) {
  const qc = useQueryClient();
  const str = (k: string) => (typeof profile[k] === "string" ? (profile[k] as string) : "");
  const [f, setF] = useState<Form>({
    fiscal_year_end: str("fiscal_year_end"),
    books_export: str("books_export"),
    ledger: str("ledger"),
    allergens: Array.isArray(profile.allergens) ? (profile.allergens as string[]).join(", ") : "",
    notes: str("notes"),
  });
  const [staged, setStaged] = useState<{ approval_id: string; changes: string[] } | null>(null);
  const stage = useMutation({ mutationFn: () => unwrap(stageProfile({ body: toBody(f) })), onSuccess: setStaged });
  const apply = useMutation({
    mutationFn: async () => {
      await unwrap(decideApproval({ path: { approval_id: staged!.approval_id }, body: { approve: true } }));
      return unwrap(applyProfile({ body: { ...toBody(f), approval_id: staged!.approval_id } }));
    },
    onSuccess: async () => {
      setStaged(null);
      await qc.invalidateQueries({ queryKey: ["profile"] });
    },
  });
  const set = (k: keyof Form, v: string) => {
    setStaged(null); // any edit needs a fresh approval
    setF({ ...f, [k]: v });
  };

  return (
    <div className="grid max-w-4xl gap-6 lg:grid-cols-[1.3fr_1fr]">
      <Card className="p-5">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            stage.mutate();
          }}
        >
          <fieldset disabled={!editable} className="space-y-4">
            <label className="block">
              <Label hint="MM-DD">Fiscal year ends</Label>
              <Input id="fiscal_year_end" value={f.fiscal_year_end} placeholder="12-31" onChange={(e) => set("fiscal_year_end", e.target.value)} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <Label>Books are kept in</Label>
                <Select id="ledger" value={f.ledger} onChange={(e) => set("ledger", e.target.value)}>
                  <option value="">Not set</option>
                  <option value="quickbooks">QuickBooks</option>
                  <option value="xero">Xero</option>
                  <option value="spreadsheet">A spreadsheet</option>
                  <option value="none">Nowhere yet</option>
                </Select>
              </label>
              <label className="block">
                <Label>Books export format</Label>
                <Select id="books_export" value={f.books_export} onChange={(e) => set("books_export", e.target.value)}>
                  <option value="">Not set</option>
                  <option value="qbo">QuickBooks CSV</option>
                  <option value="xero">Xero CSV</option>
                  <option value="none">No export</option>
                </Select>
              </label>
            </div>
            <label className="block">
              <Label hint="comma separated">Allergens you handle</Label>
              <Input value={f.allergens} placeholder="milk, pistachio, almond" onChange={(e) => set("allergens", e.target.value)} />
            </label>
            <label className="block">
              <Label hint="Ask Keel reads this">Notes for Keel</Label>
              <Input value={f.notes} maxLength={500} placeholder="e.g. we close on Mondays" onChange={(e) => set("notes", e.target.value)} />
            </label>
          </fieldset>
          <ErrorNote error={stage.error} />
          {editable ? <Button disabled={stage.isPending}>Review the changes</Button> : <p className="text-sm text-muted">Only owners and admins can change the profile.</p>}
        </form>
      </Card>
      {staged && (
        <div className="self-start overflow-hidden rounded-xl border-2 border-ink bg-surface">
          <div className="bg-ink px-5 py-3 text-bg">
            <p className="text-xs uppercase tracking-wider opacity-70">Approval needed · update profile</p>
            <p className="mt-1 font-medium">Keel will work from these from now on.</p>
          </div>
          <div className="space-y-3 p-5 text-sm">
            <ul className="space-y-1">{staged.changes.map((c) => <li key={c}>• {c}</li>)}</ul>
            <ErrorNote error={apply.error} />
            <Button variant="approve" id="approve_profile" disabled={apply.isPending} onClick={() => apply.mutate()}>Approve and save</Button>
          </div>
        </div>
      )}
    </div>
  );
}
