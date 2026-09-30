"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { API_URL } from "@/config";
import { formatTimecode, parseTimecode } from "@/lib/timecode";
import { RenderResult } from "@/components/render-result";
import type { RenderJob } from "@/components/render-result";

export const MAX_CLIP_SECONDS = 180;
const POLL_INTERVAL_MS = 1500;

export type ShortJob = RenderJob;

async function readJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail ?? "요청을 처리하지 못했습니다.");
  }
  return payload as T;
}

function isYouTubeUrl(value: string) {
  try {
    const hostname = new URL(value).hostname.replace(/^(www\.|m\.)/, "");
    return hostname === "youtu.be" || hostname === "youtube.com" || hostname.endsWith(".youtube.com");
  } catch {
    return false;
  }
}

export function validateRange(startText: string, endText: string) {
  const start = parseTimecode(startText);
  const end = parseTimecode(endText);
  if (start === null || end === null) {
    return { start, end, error: "시간은 HH:MM:SS 또는 MM:SS 형식으로 입력해 주세요." };
  }
  if (end <= start) {
    return { start, end, error: "종료 시간은 시작 시간보다 커야 합니다." };
  }
  if (end - start > MAX_CLIP_SECONDS) {
    return { start, end, error: `쇼츠 길이는 최대 ${MAX_CLIP_SECONDS}초까지 가능합니다.` };
  }
  return { start, end, error: null };
}

type RenderRequest = {
  youtube_url: string;
  start_seconds: number;
  end_seconds: number;
  rights_confirmed: true;
};

export function ShortsCreator() {
  const [url, setUrl] = useState("");
  const [startText, setStartText] = useState("00:00:00");
  const [endText, setEndText] = useState("00:00:30");
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<ShortJob | null>(null);
  const [lastRequest, setLastRequest] = useState<RenderRequest | null>(null);

  const range = validateRange(startText, endText);
  const rangeDuration =
    range.start !== null && range.end !== null ? Math.max(0, range.end - range.start) : 0;
  const isActive = job !== null && job.status !== "completed" && job.status !== "failed";

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_URL}/shorts/${job.id}`, {
          signal: controller.signal,
        });
        setJob(await readJsonResponse<ShortJob>(response));
      } catch (pollError) {
        if (controller.signal.aborted) return;
        const message =
          pollError instanceof Error ? pollError.message : "작업 상태를 확인하지 못했습니다.";
        setJob((current) =>
          current
            ? { ...current, status: "failed", artifact_state: "failed", error_message: message }
            : current,
        );
      }
    }, POLL_INTERVAL_MS);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [job]);

  async function submitRender(request: RenderRequest) {
    setError(null);
    setIsSubmitting(true);
    setJob(null);
    setLastRequest(request);
    try {
      const response = await fetch(`${API_URL}/shorts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      setJob(await readJsonResponse<ShortJob>(response));
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "쇼츠 생성을 시작하지 못했습니다.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const requestedUrl = url.trim();
    if (!isYouTubeUrl(requestedUrl)) {
      setError("YouTube 영상 URL을 입력해 주세요.");
      return;
    }
    if (range.error || range.start === null || range.end === null) {
      setError(range.error ?? "구간을 확인해 주세요.");
      return;
    }
    if (!rightsConfirmed) {
      setError("원본 영상에 대한 권리 확인이 필요합니다.");
      return;
    }

    await submitRender({
      youtube_url: requestedUrl,
      start_seconds: range.start,
      end_seconds: range.end,
      rights_confirmed: true,
    });
  }

  function handleRetry() {
    if (lastRequest) void submitRender(lastRequest);
  }

  return (
    <section className="source-panel shorts-panel" aria-labelledby="shorts-heading">
      <div className="source-heading">
        <div>
          <p className="section-label">URL + START + END</p>
          <h2 id="shorts-heading">구간을 정해 쇼츠를 만드세요</h2>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <label className="field">
          <span>YouTube URL</span>
          <input
            type="url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://youtube.com/watch?v=..."
            required
          />
        </label>

        <div className="time-fields">
          <label className="field">
            <span>시작 시간</span>
            <input
              type="text"
              inputMode="numeric"
              value={startText}
              onChange={(event) => setStartText(event.target.value)}
              placeholder="00:02:15"
              aria-label="시작 시간"
            />
          </label>
          <label className="field">
            <span>끝 시간</span>
            <input
              type="text"
              inputMode="numeric"
              value={endText}
              onChange={(event) => setEndText(event.target.value)}
              placeholder="00:03:05"
              aria-label="끝 시간"
            />
          </label>
        </div>

        <p className={range.error ? "range-help range-error" : "range-help"}>
          {range.error
            ? range.error
            : `선택 구간 ${formatTimecode(rangeDuration)} · 최대 ${MAX_CLIP_SECONDS}초 · 1080x1920 세로 영상으로 출력`}
        </p>

        <label className="rights-confirmation">
          <input
            type="checkbox"
            checked={rightsConfirmed}
            onChange={(event) => setRightsConfirmed(event.target.checked)}
          />
          <span>
            <strong>원본 영상 권리 확인</strong>
            <small>
              이 영상은 내가 소유하고 있거나, 권리자로부터 쇼츠 제작·편집 및 이용에 필요한
              허가를 받은 영상임을 확인합니다.
            </small>
          </span>
        </label>

        <button
          className="submit-button"
          type="submit"
          disabled={isSubmitting || isActive || Boolean(range.error) || !rightsConfirmed}
        >
          {isSubmitting ? "작업 등록 중..." : isActive ? "처리 중..." : "쇼츠 생성"}
        </button>
      </form>

      {error ? (
        <p className="message error-message" role="alert">
          {error}
        </p>
      ) : null}

      {job ? (
        <RenderResult job={job} onRetry={handleRetry} retryDisabled={isSubmitting} />
      ) : null}
    </section>
  );
}
