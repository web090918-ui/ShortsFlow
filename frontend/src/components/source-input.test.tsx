import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
      screen.getByLabelText("YouTube URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "영상 불러오기" }));

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
    await user.click(screen.getByRole("button", { name: "파일 업로드" }));
    await user.click(screen.getByRole("button", { name: "영상 불러오기" }));

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
      screen.getByLabelText("YouTube URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "영상 불러오기" }));
    expect(await screen.findByText("Cached video")).toBeTruthy();
    firstRender.unmount();

    render(<SourceInput />);
    await user.type(
      screen.getByLabelText("YouTube URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "영상 불러오기" }));

    expect(await screen.findByText("Cached video")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("runs the AI analysis, shows Top 3 with AI Score, and renders the chosen clip", async () => {
    const user = userEvent.setup();
    const candidate = {
      candidate_id: "cand-1",
      index: 3,
      rank: 1,
      ai_score: 78,
      reason: "훅이 강하고 완결된 이야기입니다.",
      strengths: ["명확한 주제", "구체적 설명"],
      concerns: [],
      start_seconds: 136,
      end_seconds: 195,
      duration_seconds: 59,
      hook_text: "호텔 바우처 이런 거 처음 받아보네.",
    };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "3d81a939-9f07-4a2a-864f-d027b55caec1",
            type: "YOUTUBE",
            status: "READY",
            metadata: { youtube: { title: "Long video", duration_seconds: 1663 } },
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "analysis-1",
            status: "COMPLETED",
            step: "RANKING",
            progress: 100,
            error_message: null,
            result: {
              ranking: {
                top_3: [candidate, { ...candidate, candidate_id: "cand-2", rank: 2, ai_score: 72, reason: "두 번째 이유" }],
                items: [],
              },
            },
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "render-1",
            status: "queued",
            progress: 0,
            start_seconds: 136,
            end_seconds: 195,
            duration_seconds: 59,
            template_id: "BOLD_HIGHLIGHT",
            candidate_id: "cand-1",
            download_url: null,
            preview_url: null,
            download_expires_at: null,
            artifact_state: "pending",
            captions_applied: 0,
            error_message: null,
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "render-1",
            status: "completed",
            progress: 100,
            start_seconds: 136,
            end_seconds: 195,
            duration_seconds: 59,
            template_id: "BOLD_HIGHLIGHT",
            candidate_id: "cand-1",
            download_url: "/shorts/render-1/file",
            preview_url: "/shorts/render-1/file?inline=true",
            download_expires_at: null,
            artifact_state: "ready",
            captions_applied: 12,
            error_message: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    render(<SourceInput />);
    await user.type(
      screen.getByLabelText("YouTube URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "영상 불러오기" }));

    expect(await screen.findByText("분석할 영상 구간")).toBeTruthy();
    expect(screen.getByText("선택 15:00")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /Bold Highlight/ }));
    const analyzeButton = screen.getByRole("button", { name: "AI 추천 구간 찾기" });
    expect((analyzeButton as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("checkbox", { name: /원본 영상 권리 확인/ }));
    expect((analyzeButton as HTMLButtonElement).disabled).toBe(false);
    await user.click(analyzeButton);

    expect(await screen.findByText("AI 추천 Top 3")).toBeTruthy();
    expect(screen.getAllByText("AI Score")).toHaveLength(2);
    expect(screen.getByText("78")).toBeTruthy();
    expect(screen.getByText("훅이 강하고 완결된 이야기입니다.")).toBeTruthy();
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/processing-jobs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          source_id: "3d81a939-9f07-4a2a-864f-d027b55caec1",
          source_url: "https://youtube.com/watch?v=source123",
          start_seconds: 0,
          end_seconds: 900,
          rights_confirmed: true,
          template_id: "BOLD_HIGHLIGHT",
          layout_id: "FILL",
          transcript_language: "ko",
        }),
      }),
    );

    await user.click(screen.getAllByRole("button", { name: "이 구간으로 쇼츠 만들기" })[0]);

    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/shorts",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          processing_job_id: "analysis-1",
          candidate_id: "cand-1",
          rights_confirmed: true,
        }),
      }),
    );
    const downloadLink = await screen.findByRole("link", { name: /쇼츠 다운로드/ }, { timeout: 4000 });
    expect(downloadLink.getAttribute("href")).toBe("http://localhost:8000/shorts/render-1/file");
    const video = screen.getByLabelText("완성된 쇼츠 미리보기") as HTMLVideoElement;
    expect(video.getAttribute("src")).toBe(
      "http://localhost:8000/shorts/render-1/file?inline=true",
    );
    expect(screen.getByText(/자막 12개/)).toBeTruthy();
  });

  it("renders the selected range directly when it is 180 seconds or shorter", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "3d81a939-9f07-4a2a-864f-d027b55caec1",
            type: "YOUTUBE",
            status: "READY",
            metadata: { youtube: { title: "Long video", duration_seconds: 1663 } },
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "direct-1",
            status: "queued",
            progress: 0,
            start_seconds: 0,
            end_seconds: 120,
            duration_seconds: 120,
            template_id: "CLEAN_CAPTION",
            candidate_id: null,
            download_url: null,
            preview_url: null,
            download_expires_at: null,
            artifact_state: "pending",
            captions_applied: 0,
            error_message: null,
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
      );

    render(<SourceInput />);
    await user.type(
      screen.getByLabelText("YouTube URL"),
      "https://youtube.com/watch?v=source123",
    );
    await user.click(screen.getByRole("button", { name: "영상 불러오기" }));
    expect(await screen.findByText("분석할 영상 구간")).toBeTruthy();

    // 15 minutes is too long for a direct Short; the button says so until the range shrinks.
    expect(screen.getByRole("button", { name: /180초 이하만/ })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("구간 종료"), { target: { value: "120" } });
    await user.click(screen.getByRole("checkbox", { name: /원본 영상 권리 확인/ }));
    await user.click(screen.getByRole("button", { name: "이 구간 그대로 만들기" }));

    expect(await screen.findByText("차례를 기다리는 중")).toBeTruthy();
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/shorts",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          youtube_url: "https://youtube.com/watch?v=source123",
          source_id: "3d81a939-9f07-4a2a-864f-d027b55caec1",
          start_seconds: 0,
          end_seconds: 120,
          template_id: "CLEAN_CAPTION",
          layout_id: "FILL",
          rights_confirmed: true,
        }),
      }),
    );
  });
});
