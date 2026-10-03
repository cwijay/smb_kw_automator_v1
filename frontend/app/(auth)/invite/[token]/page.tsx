"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { AuthFrame } from "@/components/shell/AuthFrame";
import { Button, ErrorNote, Input, Label } from "@/components/ui";
import { inviteAccept, invitePreview, unwrap } from "@/lib/api";

export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const preview = useQuery({ queryKey: ["invite", token], queryFn: () => unwrap(invitePreview({ path: { token } })) });
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function accept(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await unwrap(inviteAccept({ path: { token }, body: { name, password } }));
      router.push("/");
    } catch (err) {
      setError(err);
    }
  }

  if (preview.error) return <AuthFrame title="Invite"><ErrorNote error={preview.error} /></AuthFrame>;
  if (!preview.data) return <AuthFrame title="Invite"><p className="text-sm text-muted">Checking the invite…</p></AuthFrame>;
  return (
    <AuthFrame title={`Join ${preview.data.org_name}`} sub={`Invited as ${preview.data.role} · ${preview.data.email}`}>
      <form onSubmit={accept} className="space-y-4">
        <label className="block">
          <Label>Your name</Label>
          <Input id="invite_name" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="block">
          <Label hint="new accounts only, 10+ characters">Password</Label>
          <Input id="invite_password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <ErrorNote error={error} />
        <Button type="submit" className="w-full">Accept invite</Button>
        <p className="text-xs text-muted">Already have an account with this email? Sign in first, then open this link again.</p>
      </form>
    </AuthFrame>
  );
}
