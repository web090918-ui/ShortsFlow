import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RenderResult, effectiveArtifactState } from "./render-result";
import type { RenderJob } from "./render-result";

const base: RenderJob = {
  id: "job-1",
  status: "completed",
  progress: 100,
  start_seconds: 135,
  end_seconds: 185,
  duration_seconds: 50,
  template_id: "BOLD_HIGHLIGHT",
  candidate_id: null,
  download_url: "https://storage.googleapis.com/bucket/shorts/job-1.mp4?sig=1",
  preview_url: "https://storage.googleapis.com/bucket/shorts/job-1.mp4?sig=2",
  download_expires_at: new Date(Date.now() + 3600_000).toISOString(),
  artifact_state: "ready",
  captions_applied: 12,
  error_message: null,
};

describe("RenderResult", () => {
  afterEach(cleanup);

  it("shows preview, download link, expiry, and caption count when ready", () => {
    render(<RenderResult job={base} onRetry={() => {}} />);

    expect(screen.getByLabelText("완성된 쇼츠 미리보기").getAttribute("src")).toBe(
      base.preview_url,
    );
    const link = screen.getByRole("link", { name: /쇼츠 다운로드/ });
    expect(link.getAttribute("href")).toBe(base.download_url);
    expect(link.hasAttribute("download")).toBe(true);
    expect(screen.getByText(/까지 다운로드할 수 있습니다/)).toBeTruthy();
    expect(screen.getByText(/자막 12개/)).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("offers to re-render when the link has expired", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <RenderResult
        job={{ ...base, artifact_state: "expired", download_url: null, preview_url: null }}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText("다운로드 링크 만료")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
    await user.click(screen.getByRole("button", { name: "다시 만들기" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("treats a ready job whose expiry already passed as expired on the client", () => {
    const expired = {
      ...base,
      download_expires_at: new Date(Date.now() - 60_000).toISOString(),
    };

    expect(effectiveArtifactState(expired, Date.now())).toBe("expired");

    render(<RenderResult job={expired} onRetry={() => {}} />);
    expect(screen.getByText("다운로드 링크 만료")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("explains a removed artifact and offers to re-render", () => {
    render(
      <RenderResult
        job={{ ...base, artifact_state: "unavailable", download_url: null, preview_url: null }}
        onRetry={() => {}}
      />,
    );

    expect(screen.getByText("파일 보관 기간 종료")).toBeTruthy();
    expect(screen.getByRole("button", { name: "다시 만들기" })).toBeTruthy();
  });

  it("shows the failure message with a retry button", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <RenderResult
        job={{
          ...base,
          status: "failed",
          progress: 20,
          artifact_state: "failed",
          download_url: null,
          preview_url: null,
          error_message: "원본 영상 확보가 너무 오래 걸려 중단했습니다.",
        }}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText("원본 영상 확보가 너무 오래 걸려 중단했습니다.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "다시 시도" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
