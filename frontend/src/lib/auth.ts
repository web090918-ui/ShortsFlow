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

export type CreditBudget = {
  balance: number;
  /** How many 10-minute AI analyses the balance covers. */
  analyses10min: number;
  /** How many 2-minute manual-range Shorts the balance covers. */
  manualShorts: number;
  /** How many product Shorts the balance covers. */
  productShorts: number;
};

/** Rough "what can I still make" numbers for a balance, or null without prices. */
export function creditBudget(status: AuthStatus): CreditBudget | null {
  const balance = status.credits;
  const analysis = status.costs?.analysis_per_minute;
  const manual = status.costs?.manual_short_per_minute;
  const product = status.costs?.product_short;
  if (typeof balance !== "number" || typeof analysis !== "number") return null;
  const safe = (cost: number) => (cost > 0 ? Math.floor(balance / cost) : Infinity);
  return {
    balance,
    analyses10min: safe(analysis * 10),
    manualShorts: typeof manual === "number" ? safe(manual * 2) : 0,
    productShorts: typeof product === "number" ? safe(product) : 0,
  };
}

/** One-line Korean summary such as "10분 영상 분석 3회 · 상품 쇼츠 6편". */
export function describeCreditBudget(status: AuthStatus): string | null {
  const budget = creditBudget(status);
  if (!budget) return null;
  const parts = [`10분 영상 AI 분석 약 ${budget.analyses10min}회`];
  if (budget.manualShorts !== Infinity) parts.push(`2분 직접 지정 쇼츠 약 ${budget.manualShorts}편`);
  if (budget.productShorts !== Infinity && budget.productShorts > 0) {
    parts.push(`상품 쇼츠 약 ${budget.productShorts}편`);
  }
  return parts.join(" · ");
}

export function loginUrl(next: string) {
  return `${API_URL}/auth/google/start?next=${encodeURIComponent(next === "/" ? "/my" : next)}`;
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const response = await fetch(`${API_URL}/auth/status`, { credentials: "include" });
  if (!response.ok) return UNKNOWN;
  return (await response.json()) as AuthStatus;
}

export async function logout(): Promise<void> {
  const response = await fetch(`${API_URL}/auth/logout`, { method: "POST", credentials: "include" });
  if (!response.ok) throw new Error("로그아웃하지 못했습니다. 다시 시도해 주세요.");
}

