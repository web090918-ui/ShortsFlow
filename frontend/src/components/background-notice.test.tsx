import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { BackgroundNotice } from "./background-notice";

describe("BackgroundNotice", () => {
  afterEach(cleanup);

  it("opens once per started job, links to the project, and closes", async () => {
    const user = userEvent.setup();
    const view = render(<BackgroundNotice jobId={null} projectHref="/my/source-1" />);
    expect(screen.queryByRole("dialog")).toBeNull();

    view.rerender(<BackgroundNotice jobId="job-1" projectHref="/my/source-1" />);
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("페이지를 떠나도 계속 만들어져요");
    expect(dialog.textContent).toContain("내 프로젝트에서 받을 수 있어요");
    expect(screen.getByRole("link", { name: "내 프로젝트 보기" }).getAttribute("href")).toBe("/my/source-1");

    await user.click(screen.getByRole("button", { name: "여기서 기다리기" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    // The same job does not reopen it; a new job does.
    view.rerender(<BackgroundNotice jobId="job-1" projectHref="/my/source-1" />);
    expect(screen.queryByRole("dialog")).toBeNull();
    view.rerender(<BackgroundNotice jobId="job-2" projectHref="/my/source-1" />);
    expect(screen.getByRole("dialog")).toBeTruthy();
  });
});
