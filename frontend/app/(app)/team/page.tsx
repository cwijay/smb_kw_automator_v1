"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button, Card, ErrorNote, Input, Label, PageTitle, Pill, Select } from "@/components/ui";
import { invite, members, remove, setRole, unwrap } from "@/lib/api";
import { isAdmin, useMe } from "@/lib/hooks";

const ROLE_HELP: Record<string, string> = {
  owner: "Everything, including billing and owners",
  admin: "Manage team, settings and approve",
  member: "Upload, review and approve",
  viewer: "Look only",
};

export default function TeamPage() {
  const qc = useQueryClient();
  const me = useMe();
  const admin = isAdmin(me.data?.role);
  const q = useQuery({ queryKey: ["members"], queryFn: () => unwrap(members()) });
  const [email, setEmail] = useState("");
  const [role, setInviteRole] = useState<"admin" | "member" | "viewer">("member");
  const [link, setLink] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["members"] });

  const send = useMutation({
    mutationFn: () => unwrap(invite({ body: { email, role } })),
    onSuccess: (r) => { setLink(r.dev_link ?? null); setEmail(""); refresh(); },
  });
  const change = useMutation({
    mutationFn: (v: { user_id: string; role: "owner" | "admin" | "member" | "viewer" }) => unwrap(setRole({ path: { user_id: v.user_id }, body: { role: v.role } })),
    onSettled: refresh,
  });
  const drop = useMutation({ mutationFn: (user_id: string) => unwrap(remove({ path: { user_id } })), onSettled: refresh });

  return (
    <>
      <PageTitle title="Team" sub={`${me.data?.org_name ?? ""} · each person sees only this business's records.`} />
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <Card className="divide-y divide-line">
          {q.data?.map((m) => {
            const invited = m.role.startsWith("invited:");
            return (
              <div key={m.user_id || m.email} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm">
                <div className="min-w-0">
                  <p className="font-medium">{m.name || m.email}{m.user_id === me.data?.user_id && <span className="text-muted"> (you)</span>}</p>
                  <p className="text-xs text-muted">{m.email}</p>
                </div>
                {invited ? (
                  <Pill tone="carbon">invited as {m.role.split(":")[1]}</Pill>
                ) : admin && m.user_id !== me.data?.user_id ? (
                  <div className="flex items-center gap-2">
                    <Select aria-label={`Role for ${m.email}`} className="w-28" value={m.role} onChange={(e) => change.mutate({ user_id: m.user_id, role: e.target.value as "owner" })}>
                      {Object.keys(ROLE_HELP).map((r) => <option key={r} value={r}>{r}</option>)}
                    </Select>
                    <Button variant="quiet" onClick={() => drop.mutate(m.user_id)}>Remove</Button>
                  </div>
                ) : (
                  <Pill>{m.role}</Pill>
                )}
              </div>
            );
          })}
          <div className="px-4 py-2"><ErrorNote error={change.error ?? drop.error} /></div>
        </Card>
        <div className="space-y-4">
          {admin && (
            <Card className="p-5">
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
                <p className="font-medium">Invite someone</p>
                <label className="block"><Label>Email</Label><Input id="invite_email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
                <label className="block">
                  <Label>Role</Label>
                  <Select id="invite_role" value={role} onChange={(e) => setInviteRole(e.target.value as "member")}>
                    <option value="member">member</option>
                    <option value="viewer">viewer</option>
                    {me.data?.role === "owner" && <option value="admin">admin</option>}
                  </Select>
                </label>
                <ErrorNote error={send.error} />
                <Button disabled={send.isPending}>Send invite</Button>
                {link && (
                  <p className="break-all rounded-lg bg-ledger-soft px-3 py-2 text-xs text-ledger">
                    Invite created. Dev mode link (would be emailed): <span className="select-all font-mono">{link}</span>
                  </p>
                )}
              </form>
            </Card>
          )}
          <Card className="p-5 text-sm">
            <p className="mb-2 font-medium">What each role can do</p>
            <dl className="space-y-1.5">
              {Object.entries(ROLE_HELP).map(([r, h]) => (
                <div key={r} className="flex gap-2"><dt className="w-16 shrink-0 font-medium">{r}</dt><dd className="text-muted">{h}</dd></div>
              ))}
            </dl>
          </Card>
        </div>
      </div>
    </>
  );
}
