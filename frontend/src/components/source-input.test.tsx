import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourceInput } from "./source-input";


describe("SourceInput", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("creates a URL source and displays its status", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "3d81a939-9f07-4a2a-864f-d027b55caec1",
          type: "YOUTUBE",
          status: "CREATED",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(<SourceInput />);

    await user.type(
      screen.getByLabelText("YouTube 또는 상품 URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "Source 생성" }));

    expect(await screen.findByText("YOUTUBE")).toBeTruthy();
    expect(screen.getByText("CREATED")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/sources",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ url: "https://youtube.com/watch?v=source123" }),
      }),
    );
  });

  it("requires a file in upload mode", async () => {
    const user = userEvent.setup();

    render(<SourceInput />);
    await user.click(screen.getByRole("button", { name: "Upload" }));
    await user.click(screen.getByRole("button", { name: "Source 생성" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "업로드할 영상 파일을 선택해 주세요.",
    );
  });
});
