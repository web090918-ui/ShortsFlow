"use client";

import { useEffect, useState } from "react";

import { API_URL } from "@/config";

export type AuthUser = {
  id: string;
  email: string | null;
  name: string | null;
  picture: string | null;
};

export type AuthStatus = {
  auth_required: boolean;
  login_available: boolean;
  user: AuthUser | null;
};

const UNKNOWN: AuthStatus = { auth_required: false, login_available: false, user: null };

export function loginUrl(next: string) {
  return `${API_URL}/auth/google/start?next=${encodeURIComponent(next)}`;
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const response = await fetch(`${API_URL}/auth/status`, { credentials: "include" });
  if (!response.ok) return UNKNOWN;
  return (await response.json()) as AuthStatus;
}

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/auth/logout`, { method: "POST", credentials: "include" });
}

/** Current sign-in state; `loading` is true until the first status response. */
export function useAuthStatus() {
  const [status, setStatus] = useState<AuthStatus>(UNKNOWN);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchAuthStatus()
      .then((value) => {
        if (!cancelled) setStatus(value);
      })
      .catch(() => {
        if (!cancelled) setStatus(UNKNOWN);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { status, loading, setStatus };
}
