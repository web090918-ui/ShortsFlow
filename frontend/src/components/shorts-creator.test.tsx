import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShortsCreator, validateRange } from "./shorts-creator";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const baseJob = {
  id: "5c1a1a8e-3f2e-4a7f-9a6f-2b0a2e7d1c11",
  youtube_url: "https://youtube.com/watch?v=abc123",
  start_seconds: 135,
  end_seconds: 185,
  duration_seconds: 50,
  download_url: null,
  preview_url: null,
  download_expires_at: null,
  artifact_state: "pending" as const,
  template_id: "CLEAN_CAPTION" as const,
  candidate_id: null,
  captions_applied: 0,
  error_message: null,
};

describe("validateRange", () => {
  it("accepts a valid range and rejects invalid ones", () => {
    expect(validateRange("00:02:15", "00:03:05")).toEqual({
      start: 135,
      end: 185,
      error: null,
    });
    expect(validateRange("10", "5").error).toContain("종료 시간");
    expect(validateRange("0", "181").error).toContain("최대 180초");
    expect(validateRange("abc", "10").error).toContain("형식");
  });
});

describe("ShortsCreator", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("submits parsed seconds, polls the job and shows the download link", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ...baseJob, status: "queued", progress: 0 }, 202))
      .mockResolvedValueOnce(
        jsonResponse({
          ...baseJob,
          status: "completed",
          progress: 100,
          artifact_state: "ready",
          download_url: `/shorts/${baseJob.id}/file`,
        }),
      );

    render(<ShortsCreator />);

    await user.type(screen.getByLabelText("YouTube URL"), "https://youtube.com/watch?v=abc123");
    await user.clear(screen.getByLabelText("시작 시간"));
    await user.type(screen.getByLabelText("시작 시간"), "00:02:15");
    await user.clear(screen.getByLabelText("끝 시간"));
    await user.type(screen.getByLabelText("끝 시간"), "00:03:05");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "쇼츠 생성" }));

    expect(await screen.findByText("대기 중")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/shorts",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          youtube_url: "https://youtube.com/watch?v=abc123",
          start_seconds: 135,
          end_seconds: 185,
          rights_confirmed: true,
        }),
      }),
    );

    const link = await screen.findByRole("link", { name: /쇼츠 다운로드/ }, { timeout: 4000 });
    expect(link.getAttribute("href")).toBe(`http://localhost:8000/shorts/${baseJob.id}/file`);
    expect(screen.getByText("완료")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("blocks submission until the range is valid and rights are confirmed", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.spyOn(globalThis, "fetch");

    render(<ShortsCreator />);

    const button = screen.getByRole("button", { name: "쇼츠 생성" });
    expect(button).toHaveProperty("disabled", true);

    await user.clear(screen.getByLabelText("끝 시간"));
    await user.type(screen.getByLabelText("끝 시간"), "00:05:00");
    expect(screen.getByText("쇼츠 길이는 최대 180초까지 가능합니다.")).toBeTruthy();

    await user.clear(screen.getByLabelText("끝 시간"));
    await user.type(screen.getByLabelText("끝 시간"), "00:01:00");
    await user.click(screen.getByRole("checkbox"));
    expect(button).toHaveProperty("disabled", false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server error when the job fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ ...baseJob, status: "queued", progress: 0 }, 202))
      .mockResolvedValueOnce(
        jsonResponse({
          ...baseJob,
          status: "failed",
          progress: 10,
          artifact_state: "failed",
          error_message: "선택한 종료 시간이 원본 영상 길이를 초과합니다.",
        }),
      );

    render(<ShortsCreator />);

    await user.type(screen.getByLabelText("YouTube URL"), "https://youtu.be/abc123");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "쇼츠 생성" }));

    expect(
      await screen.findByText(
        "선택한 종료 시간이 원본 영상 길이를 초과합니다.",
        {},
        { timeout: 4000 },
      ),
    ).toBeTruthy();
    expect(screen.getByText("실패")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /쇼츠 다운로드/ })).toBeNull();
  });
});
