// Single entry to the generated client. Same-origin `/api` (Next rewrites to the backend), cookie auth.
import { client } from "./gen/client.gen";

client.setConfig({ baseUrl: "", credentials: "include" });

export * from "./gen/sdk.gen";
export type * from "./gen/types.gen";

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) {
    super(message);
  }
}

type Result<T> = { data?: T; error?: unknown; response?: Response };

/** Await a generated call; return data or throw a readable ApiError. */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  const r = await call;
  const status = r.response?.status ?? 0;
  if (r.error !== undefined || !r.response?.ok) {
    const e = (r.error ?? {}) as { message?: string; error?: string; detail?: { msg: string }[] | string };
    const detail = Array.isArray(e.detail) ? e.detail.map((d) => d.msg).join("; ") : e.detail;
    if (status === 401 && typeof window !== "undefined" && !/^\/(login|signup|invite|auth)/.test(location.pathname)) {
      window.location.replace("/login");
    }
    throw new ApiError(e.message ?? detail ?? `Request failed (${status})`, status, e.error);
  }
  return r.data as T;
}
