import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { LandingSourceForm } from "./landing-source-form";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
afterEach(() => { cleanup(); push.mockClear(); });

it("validates the source and carries the complete URL to the video studio", async () => {
  const user = userEvent.setup();
  render(<LandingSourceForm />);
  await user.click(screen.getByRole("button", { name: /시작/ }));
  expect(screen.getByRole("alert").textContent).toContain("YouTube");
  expect(push).not.toHaveBeenCalled();
  const url = "https://www.youtube.com/watch?v=M7lc1UVf-VE&t=42";
  await user.type(screen.getByLabelText("YouTube 영상 링크"), url);
  await user.click(screen.getByRole("button", { name: /시작/ }));
  expect(push).toHaveBeenCalledWith(`/video?url=${encodeURIComponent(url)}`);
});
