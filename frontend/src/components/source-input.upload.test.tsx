import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setDurationReaderForTests } from "@/lib/upload";

import { SourceInput } from "./source-input";

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("SourceInput upload flow", () => {
  beforeEach(() => {
    setDurationReaderForTests(async () => 125);
  });

  afterEach(() => {
    cleanup();
    setDurationReaderForTests(null);
    vi.restoreAllMocks();
  });

  it("registers, uploads to the signed URL, confirms, and opens the range picker", async () => {
    const user = userEvent.setup();
    const sourceId = "8b5b2c0e-6b1a-4f0e-9a51-3c1a2d7e9f00";
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse(
          {
            id: sourceId,
            type: "UPLOAD",
            status: "CREATED",
            metadata: {
              upload: { filename: "clip.mp4", content_type: "video/mp4", size_bytes: 5, duration_seconds: 125 },
            },
            upload: {
              mode: "signed_put",
              url: "https://storage.googleapis.com/bucket/uploads/x.mp4?sig=1",
              headers: { "Content-Type": "video/mp4" },
            },
          },
          201,
        ),
      )
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(
        jsonResponse({
          id: sourceId,
          type: "UPLOAD",
          status: "READY",
          metadata: {
            upload: { filename: "clip.mp4", content_type: "video/mp4", size_bytes: 5, duration_seconds: 125 },
            media: { provider: "upload" },
          },
        }),
      );

    render(<SourceInput />);
    await user.click(screen.getByRole("button", { name: "Upload" }));
    const file = new File([new Uint8Array(5)], "clip.mp4", { type: "video/mp4" });
    await user.upload(screen.getByLabelText("영상 파일"), file);
    await user.click(screen.getByRole("button", { name: "Source 생성" }));

    expect(await screen.findByText("분석할 영상 구간")).toBeTruthy();
    expect(screen.getByText("clip.mp4")).toBeTruthy();
    expect(screen.getByText("선택 2:05")).toBeTruthy();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/sources/upload",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          filename: "clip.mp4",
          content_type: "video/mp4",
          size_bytes: 5,
          duration_seconds: 125,
        }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "https://storage.googleapis.com/bucket/uploads/x.mp4?sig=1",
      expect.objectContaining({ method: "PUT", headers: { "Content-Type": "video/mp4" } }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      `http://localhost:8000/sources/${sourceId}/uploaded`,
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("starts the analysis for an upload without a source_url", async () => {
    const user = userEvent.setup();
    const sourceId = "8b5b2c0e-6b1a-4f0e-9a51-3c1a2d7e9f01";
    const ready = {
      id: sourceId,
      type: "UPLOAD",
      status: "READY",
      metadata: {
        upload: { filename: "talk.mp4", content_type: "video/mp4", size_bytes: 5, duration_seconds: 600 },
      },
    };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({ ...ready, status: "CREATED", upload: { mode: "direct", url: `/sources/${sourceId}/content` } }, 201),
      )
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(jsonResponse(ready))
      .mockResolvedValueOnce(
        jsonResponse(
          { id: "analysis-u", status: "QUEUED", step: "TRANSCRIPT", progress: 0, error_message: null, result: null },
          202,
        ),
      );

    render(<SourceInput />);
    await user.click(screen.getByRole("button", { name: "Upload" }));
    await user.upload(
      screen.getByLabelText("영상 파일"),
      new File([new Uint8Array(5)], "talk.mp4", { type: "video/mp4" }),
    );
    await user.click(screen.getByRole("button", { name: "Source 생성" }));
    expect(await screen.findByText("분석할 영상 구간")).toBeTruthy();

    await user.click(screen.getByRole("checkbox", { name: /원본 영상 권리 확인/ }));
    await user.click(screen.getByRole("button", { name: "AI 추천 구간 찾기" }));

    expect(await screen.findByText("자막·음성 분석 중")).toBeTruthy();
    const analysisCall = fetchMock.mock.calls[3];
    expect(analysisCall[0]).toBe("http://localhost:8000/processing-jobs");
    const body = JSON.parse((analysisCall[1] as RequestInit).body as string);
    expect(body.source_id).toBe(sourceId);
    expect(body).not.toHaveProperty("source_url");
    expect(body.end_seconds).toBe(600);
    expect(fetchMock.mock.calls[1][0]).toBe(`http://localhost:8000/sources/${sourceId}/content`);
  });
});
