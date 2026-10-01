import { describe, expect, it } from "vitest";

import { creditBudget, creditCost, describeCreditBudget, minutesRoundedUp, loginUrl } from "./auth";
import type { AuthStatus } from "./auth";

const status: AuthStatus = {
  auth_required: true,
  login_available: true,
  user: { id: "u", email: null, name: null, picture: null },
  credits: 30,
  costs: {
    analysis_per_minute: 1,
    manual_short_per_minute: 1,
    candidate_render: 0,
    product_short: 5,
    signup_grant: 30,
  },
};

describe("credit helpers", () => {
  it("opens the member workspace after homepage login and preserves active work", () => {
    expect(new URL(loginUrl("/")).searchParams.get("next")).toBe("/my");
    const activeWork = "/video?url=https%3A%2F%2Fyoutu.be%2FM7lc1UVf-VE";
    expect(new URL(loginUrl(activeWork)).searchParams.get("next")).toBe(activeWork);
    expect(new URL(loginUrl("/my/settings")).searchParams.get("next")).toBe("/my/settings");
  });
  it("rounds source seconds up to minutes", () => {
    expect(minutesRoundedUp(1)).toBe(1);
    expect(minutesRoundedUp(60)).toBe(1);
    expect(minutesRoundedUp(61)).toBe(2);
    expect(minutesRoundedUp(900)).toBe(15);
  });

  it("prices actions from the published costs", () => {
    expect(creditCost(status, "analysis_per_minute", 15)).toBe(15);
    expect(creditCost(status, "manual_short_per_minute", 3)).toBe(3);
    expect(creditCost(status, "product_short")).toBe(5);
    expect(creditCost(status, "candidate_render")).toBe(0);
    expect(creditCost({ ...status, costs: undefined }, "product_short")).toBeNull();
  });

  it("turns a balance into rough counts and a readable sentence", () => {
    expect(creditBudget(status)).toEqual({
      balance: 30,
      analyses10min: 3,
      manualShorts: 15,
      productShorts: 6,
    });
    expect(describeCreditBudget(status)).toBe(
      "10분 영상 AI 분석 약 3회 · 2분 직접 지정 쇼츠 약 15편 · 상품 쇼츠 약 6편",
    );
    expect(describeCreditBudget({ ...status, credits: null })).toBeNull();
    expect(creditBudget({ ...status, credits: 4 })?.productShorts).toBe(0);
  });
});
