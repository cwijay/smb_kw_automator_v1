"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AuthFrame } from "@/components/shell/AuthFrame";
import { ErrorNote } from "@/components/ui";
import { magicVerify, unwrap } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token");
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (!token) return;
    unwrap(magicVerify({ body: { token } }))
      .then(() => router.replace("/"))
      .catch(setError);
  }, [token, router]);
  return error ? <ErrorNote error={error} /> : <p className="text-sm text-muted">Signing you in…</p>;
}

export default function MagicPage() {
  return (
    <AuthFrame title="Sign-in link">
      <Suspense>
        <Verify />
      </Suspense>
    </AuthFrame>
  );
}
