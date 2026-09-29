import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourceInput } from "./source-input";


describe("SourceInput", () => {
  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("creates a URL source and displays its status", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "3d81a939-9f07-4a2a-864f-d027b55caec1",
          type: "YOUTUBE",
          status: "READY",
          metadata: {
            youtube: {
              title: "Test video",
              channel_title: "ShortsFlow",
              duration_seconds: 125,
            },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(<SourceInput />);

    await user.type(
      screen.getByLabelText("YouTube 또는 상품 URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "Source 생성" }));

    expect(await screen.findByText("YOUTUBE")).toBeTruthy();
    expect(screen.getByText("READY")).toBeTruthy();
    expect(screen.getByText("Test video")).toBeTruthy();
    expect(screen.getByText("ShortsFlow · 2:05")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/sources?prepare=true",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ url: "https://youtube.com/watch?v=source123" }),
      }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
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

  it("reuses ready metadata from the browser session", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "3d81a939-9f07-4a2a-864f-d027b55caec1",
          type: "YOUTUBE",
          status: "READY",
          metadata: { youtube: { title: "Cached video", duration_seconds: 120 } },
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    const firstRender = render(<SourceInput />);
    await user.type(
      screen.getByLabelText("YouTube 또는 상품 URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "Source 생성" }));
    expect(await screen.findByText("Cached video")).toBeTruthy();
    firstRender.unmount();

    render(<SourceInput />);
    await user.type(
      screen.getByLabelText("YouTube 또는 상품 URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "Source 생성" }));

    expect(await screen.findByText("Cached video")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("creates a selected-range download job and shows the MP4 link", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "3d81a939-9f07-4a2a-864f-d027b55caec1",
            type: "YOUTUBE",
            status: "READY",
            metadata: {
              youtube: {
                title: "Long video",
                duration_seconds: 600,
              },
            },
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "download-job-1",
            source_id: "3d81a939-9f07-4a2a-864f-d027b55caec1",
            status: "READY",
            progress: 100,
            start_seconds: 0,
            end_seconds: 240,
            duration_seconds: 240,
            template_id: "BOLD_HIGHLIGHT",
            error_message: null,
            download_url: "/downloads/download-job-1/file",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
      );

    render(<SourceInput />);
    await user.type(
      screen.getByLabelText("YouTube 또는 상품 URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "Source 생성" }));

    expect(await screen.findByText("사용할 영상 구간")).toBeTruthy();
    expect(screen.getByText("선택 4:00")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /Bold Highlight/ }));
    const prepareButton = screen.getByRole("button", {
      name: "480p 분석 구간 준비",
    });
    expect((prepareButton as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("checkbox", { name: /원본 영상 권리 확인/ }));
    expect((prepareButton as HTMLButtonElement).disabled).toBe(false);
    await user.click(prepareButton);

    const downloadLink = await screen.findByRole("link", {
      name: "분석용 MP4 다운로드",
    });
    expect(downloadLink.getAttribute("href")).toBe(
      "http://localhost:8000/downloads/download-job-1/file",
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/sources/3d81a939-9f07-4a2a-864f-d027b55caec1/downloads",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          start_seconds: 0,
          end_seconds: 240,
          rights_confirmed: true,
          template_id: "BOLD_HIGHLIGHT",
        }),
      }),
    );
  });

});
