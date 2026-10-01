import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), setStatus: vi.fn(), logout: vi.fn(), user: { id: "member-1", email: "member@example.com", name: "Member", picture: null } as { id: string; email: string; name: string; picture: null } | null }));
vi.mock("next/navigation", () => ({ usePathname: () => "/my/settings", useSearchParams: () => new URLSearchParams(), useRouter: () => ({ replace: mocks.replace, refresh: mocks.refresh, push: vi.fn() }) }));
vi.mock("@/lib/auth-context", () => ({ useAuthStatus: () => ({ loading: false, status: { user: mocks.user, login_available: true, credits: 28 }, setStatus: mocks.setStatus }) }));
vi.mock("@/lib/auth", async (original) => ({ ...await original<object>(), logout: mocks.logout }));
import { MemberSettings, MemberWelcome, MemberWorkspace } from "./member-workspace";
afterEach(() => { cleanup(); localStorage.clear(); vi.clearAllMocks(); mocks.user = { id: "member-1", email: "member@example.com", name: "Member", picture: null }; });
it("keeps member content hidden until signed in", () => {
  mocks.user = null;
  render(<MemberWorkspace><p>Private projects</p></MemberWorkspace>);
  expect(screen.queryByText("Private projects")).toBeNull();
  expect(new URL(screen.getByRole("link", { name: "Google로 로그인" }).getAttribute("href")!).searchParams.get("next")).toBe("/my/settings");
});
it("persists the preferred creation flow and uses it on the dashboard", () => {
  const view = render(<MemberSettings />);
  fireEvent.change(screen.getByLabelText("기본 제작 방식"), { target: { value: "affiliate" } });
  expect(localStorage.getItem("cutpick:member-1:start-source")).toBe("affiliate");
  view.unmount();
  render(<MemberWelcome />);
  expect(screen.getByRole("link", { name: "내 기본 제작 방식으로 시작 →" }).getAttribute("href")).toBe("/affiliate");
});
it("does not use another member's saved preference", () => {
  localStorage.setItem("cutpick:another-member:start-source", "affiliate");
  render(<MemberWelcome />);
  expect(screen.getByRole("link", { name: "내 기본 제작 방식으로 시작 →" }).getAttribute("href")).toBe("/video");
});
it("keeps the session visible when logout fails and allows retry", async () => {
  mocks.logout.mockRejectedValueOnce(new Error("로그아웃 실패")).mockResolvedValueOnce(undefined);
  render(<MemberSettings />);
  fireEvent.click(screen.getByRole("button", { name: "Logout" }));
  expect((await screen.findByRole("alert")).textContent).toBe("로그아웃 실패");
  expect(mocks.replace).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Logout" }));
  await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/"));
  expect(mocks.setStatus).toHaveBeenCalledWith(expect.objectContaining({ user: null, credits: null }));
});
