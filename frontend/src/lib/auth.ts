import { API_URL } from "@/config";

export type AuthUser = {
  id: string;
  email: string | null;
  name: string | null;
  picture: string | null;
};

export type CreditCosts = {
  analysis_per_minute: number;
  manual_short_per_minute: number;
  candidate_render: number;
  product_short: number;
  signup_grant: number;
};

export type AuthStatus = {
  auth_required: boolean;
  login_available: boolean;
  user: AuthUser | null;
  credits?: number | null;
  costs?: Partial<CreditCosts>;
};

const UNKNOWN: AuthStatus = { auth_required: false, login_available: false, user: null };

/** Credits an action costs, or null when the API did not publish prices. */
export function creditCost(status: AuthStatus, key: keyof CreditCosts, minutes = 1): number | null {
  const value = status.costs?.[key];
  if (typeof value !== "number") return null;
  return key.endsWith("_per_minute") ? value * Math.max(1, minutes) : value;
}

export function minutesRoundedUp(seconds: number) {
  return Math.max(1, Math.ceil(Math.round(seconds) / 60));
}

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

