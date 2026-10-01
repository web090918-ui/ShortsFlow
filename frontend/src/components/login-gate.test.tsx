import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const navigation = vi.hoisted(() => ({ query: "login=failed" }));
vi.mock("next/navigation", () => ({
  usePathname: () => "/video",
  useSearchParams: () => new URLSearchParams(navigation.query),
}));

import { AuthProvider } from "@/lib/auth-context";

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
    navigation.query = "login=failed";
  });

  it("shows the Google sign-in card when login is required and nobody is signed in", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      statusResponse({ auth_required: true, login_available: true, user: null }),
    );

    render(
      <AuthProvider>
        <LoginGate>
          <p>wizard</p>
        </LoginGate>
      </AuthProvider>,
    );

    const link = await screen.findByRole("link", { name: "Google로 로그인" });
    expect((await screen.findByRole("alert")).textContent).toContain("Google 로그인에 실패했습니다");
    expect(link.getAttribute("href")).toBe(
      "http://localhost:8000/auth/google/start?next=%2Fvideo",
    );
    expect(screen.queryByText("wizard")).toBeNull();
  });

  it("preserves the landing video URL through Google sign-in", async () => {
    const url = "https://youtu.be/M7lc1UVf-VE";
    navigation.query = new URLSearchParams({ url, login: "failed" }).toString();
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(statusResponse({ auth_required: true, login_available: true, user: null }));
    render(<AuthProvider><LoginGate><p>wizard</p></LoginGate></AuthProvider>);
    const link = await screen.findByRole("link", { name: "Google로 로그인" });
    const next = new URL(link.getAttribute("href")!).searchParams.get("next");
    expect(next).toBe(`/video?${new URLSearchParams({ url }).toString()}`);
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
      <AuthProvider>
        <LoginGate>
          <p>wizard</p>
        </LoginGate>
      </AuthProvider>,
    );

    expect(await screen.findByText("wizard")).toBeTruthy();
  });

  it("renders the wizard when the API does not require login", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      statusResponse({ auth_required: false, login_available: false, user: null }),
    );

    render(
      <AuthProvider>
        <LoginGate>
          <p>wizard</p>
        </LoginGate>
      </AuthProvider>,
    );

    expect(await screen.findByText("wizard")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Google로 로그인" })).toBeNull();
  });
});
