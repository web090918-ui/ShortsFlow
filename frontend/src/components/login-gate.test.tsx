import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ usePathname: () => "/video" }));

import { LoginGate } from "./login-gate";

function statusResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("LoginGate", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows the Google sign-in card when login is required and nobody is signed in", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      statusResponse({ auth_required: true, login_available: true, user: null }),
    );

    render(
      <LoginGate>
        <p>wizard</p>
      </LoginGate>,
    );

    const link = await screen.findByRole("link", { name: "Google로 로그인" });
    expect(link.getAttribute("href")).toBe(
      "http://localhost:8000/auth/google/start?next=%2Fvideo",
    );
    expect(screen.queryByText("wizard")).toBeNull();
  });

  it("renders the wizard for a signed-in user", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      statusResponse({
        auth_required: true,
        login_available: true,
        user: { id: "u1", email: "me@example.com", name: "Me", picture: null },
      }),
    );

    render(
      <LoginGate>
        <p>wizard</p>
      </LoginGate>,
    );

    expect(await screen.findByText("wizard")).toBeTruthy();
  });

  it("renders the wizard when the API does not require login", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      statusResponse({ auth_required: false, login_available: false, user: null }),
    );

    render(
      <LoginGate>
        <p>wizard</p>
      </LoginGate>,
    );

    expect(await screen.findByText("wizard")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Google로 로그인" })).toBeNull();
  });
});
