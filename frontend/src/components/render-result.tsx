"use client";

import { useEffect, useState } from "react";

import { API_URL } from "@/config";
import { formatTimecode } from "@/lib/timecode";

export type ArtifactState = "pending" | "ready" | "expired" | "unavailable" | "failed";

export type RenderJob = {
  id: string;
  status: "queued" | "downloading" | "processing" | "uploading" | "completed" | "failed";
  progress: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  template_id: "CLEAN_CAPTION" | "BOLD_HIGHLIGHT" | "MINIMAL";
  candidate_id: string | null;
  download_url: string | null;
  preview_url: string | null;
  download_expires_at: string | null;
  artifact_state: ArtifactState;
  captions_applied: number;
  error_message: string | null;
};

export const RENDER_STATUS_LABELS: Record<RenderJob["status"], string> = {
  queued: "대기 중",
  downloading: "원본 영상 확보 중",
  processing: "구간 자르기 · 자막 · 9:16 변환 중",
  uploading: "완성 파일 저장 중",
  completed: "완료",
  failed: "실패",
};

export function resolveApiUrl(url: string) {
  if (/^https:\/\//i.test(url)) return url;
  return `${API_URL}${url}`;
}

function formatExpiry(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/** The artifact state, re-evaluated client-side so an open page notices expiry. */
export function effectiveArtifactState(job: RenderJob, now: number): ArtifactState {
  if (job.artifact_state !== "ready") return job.artifact_state;
  if (job.download_expires_at && Date.parse(job.download_expires_at) <= now) {
    return "expired";
  }
  return "ready";
}

type Props = {
  job: RenderJob;
  onRetry: () => void;
  retryDisabled?: boolean;
};

export function RenderResult({ job, onRetry, retryDisabled = false }: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (job.status !== "completed") return;
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, [job.status]);

  const state = effectiveArtifactState(job, now);
  const expiry = job.download_expires_at ? formatExpiry(job.download_expires_at) : null;

  return (
    <div className="download-status" aria-live="polite">
      <div>
        <span>
          {state === "expired"
            ? "다운로드 링크 만료"
            : state === "unavailable"
              ? "파일 보관 기간 종료"
              : RENDER_STATUS_LABELS[job.status]}
        </span>
        <strong>{job.progress}%</strong>
      </div>
      <progress max={100} value={job.progress} />
      <p className="shorts-status-range">
        {formatTimecode(job.start_seconds)} – {formatTimecode(job.end_seconds)} ·{" "}
        {formatTimecode(job.duration_seconds)} · {job.template_id}
        {job.status === "completed" && job.captions_applied > 0
          ? ` · 자막 ${job.captions_applied}개`
          : ""}
      </p>

      {state === "failed" ? (
        <>
          <p className="range-error">{job.error_message ?? "쇼츠 생성에 실패했습니다."}</p>
          <button
            type="button"
            className="submit-button secondary-button"
            onClick={onRetry}
            disabled={retryDisabled}
          >
            다시 시도
          </button>
        </>
      ) : null}

      {state === "expired" || state === "unavailable" ? (
        <>
          <p className="range-help">
            {state === "expired"
              ? "다운로드 링크는 24시간 동안만 유효합니다. 같은 구간을 다시 만들면 새 링크가 발급됩니다."
              : "완성 파일은 하루 뒤 삭제됩니다. 같은 구간을 다시 만들면 새 파일이 생성됩니다."}
          </p>
          <button
            type="button"
            className="submit-button secondary-button"
            onClick={onRetry}
            disabled={retryDisabled}
          >
            다시 만들기
          </button>
        </>
      ) : null}

      {state === "ready" && job.preview_url ? (
        <video
          className="preview-video"
          controls
          playsInline
          preload="metadata"
          src={resolveApiUrl(job.preview_url)}
          aria-label="완성된 쇼츠 미리보기"
        />
      ) : null}
      {state === "ready" && job.download_url ? (
        <>
          <a className="download-button" href={resolveApiUrl(job.download_url)} download>
            쇼츠 다운로드 (MP4)
          </a>
          {expiry ? (
            <p className="range-help download-expiry">{expiry}까지 다운로드할 수 있습니다.</p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
