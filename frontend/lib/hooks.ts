"use client";

import { useQuery } from "@tanstack/react-query";
import { me, unwrap } from "@/lib/api";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => unwrap(me()), staleTime: 60_000 });
}

export function canEdit(role?: string) {
  return role === "owner" || role === "admin" || role === "member";
}

export function isAdmin(role?: string) {
  return role === "owner" || role === "admin";
}
