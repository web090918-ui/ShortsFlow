"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { fetchAuthStatus } from "@/lib/auth";
import type { AuthStatus } from "@/lib/auth";

type AuthContextValue = {
  status: AuthStatus;
  loading: boolean;
  setStatus: (status: AuthStatus) => void;
};

const UNKNOWN: AuthStatus = { auth_required: false, login_available: false, user: null };
const AuthContext = createContext<AuthContextValue | null>(null);

/** Fetches /auth/status once per page so every component shares the same answer. */
export function AuthProvider({ children }: { children: ReactNode }) {
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

  return <AuthContext.Provider value={{ status, loading, setStatus }}>{children}</AuthContext.Provider>;
}

/**
 * Current sign-in state. Without a provider (component tests) it reports an
 * unknown, not-loading status and never touches the network.
 */
export function useAuthStatus(): AuthContextValue {
  const value = useContext(AuthContext);
  return value ?? { status: UNKNOWN, loading: false, setStatus: () => undefined };
}
