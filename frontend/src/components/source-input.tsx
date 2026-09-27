"use client";

import { useEffect, useState } from "react";
import type { CSSProperties, FormEvent } from "react";

import { API_URL } from "@/config";

type InputMode = "url" | "upload";
type TemplateId = "CLEAN_CAPTION" | "BOLD_HIGHLIGHT" | "MINIMAL";

type Source = {
  id: string;
  type: "YOUTUBE" | "PRODUCT" | "UPLOAD";
  status: "CREATED" | "PREPARING" | "READY" | "FAILED";
  metadata?: {
    youtube?: {
      title?: string | null;
      channel_title?: string | null;
      duration_seconds?: number | null;
      thumbnail_url?: string | null;
    };
  };
};

type DownloadJob = {
  id: string;
  source_id: string;
  status: "QUEUED" | "DOWNLOADING" | "READY" | "FAILED";
  progress: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  template_id: TemplateId;
  error_message: string | null;
  download_url: string | null;
};

const DEFAULT_RANGE_SECONDS = 4 * 60;
const MAX_RANGE_SECONDS = 60 * 60;
const TEMPLATES: Array<{
  id: TemplateId;
  name: string;
  description: string;
  previewClassName: string;
}> = [
  {
    id: "CLEAN_CAPTION",
    name: "Clean Caption",
    description: "읽기 쉬운 기본 자막",
    previewClassName: "template-clean",
  },
  {
    id: "BOLD_HIGHLIGHT",
    name: "Bold Highlight",
    description: "핵심 단어를 강하게 강조",
    previewClassName: "template-bold",
  },
  {
    id: "MINIMAL",
    name: "Minimal",
    description: "화면을 가리지 않는 최소 자막",
    previewClassName: "template-minimal",
  },
];

async function readJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail ?? "Source를 처리하지 못했습니다.");
  }
  return payload as T;
}

function formatDuration(seconds?: number | null) {
  if (typeof seconds !== "number") return null;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);
  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

export function SourceInput() {
  const [mode, setMode] = useState<InputMode>("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rangeStart, setRangeStart] = useState(0);
  const [rangeEnd, setRangeEnd] = useState(0);
  const [downloadJob, setDownloadJob] = useState<DownloadJob | null>(null);
  const [isStartingDownload, setIsStartingDownload] = useState(false);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [templateId, setTemplateId] = useState<TemplateId>("CLEAN_CAPTION");

  const sourceDuration = source?.metadata?.youtube?.duration_seconds ?? null;
  const rangeDuration = Math.max(0, rangeEnd - rangeStart);
  const rangeTooLong = rangeDuration > MAX_RANGE_SECONDS;

  useEffect(() => {
    if (
      !downloadJob ||
      downloadJob.status === "READY" ||
      downloadJob.status === "FAILED"
    ) {
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_URL}/downloads/${downloadJob.id}`, {
          signal: controller.signal,
        });
        setDownloadJob(await readJsonResponse<DownloadJob>(response));
      } catch (pollError) {
        if (controller.signal.aborted) return;
        const message =
          pollError instanceof Error
            ? pollError.message
            : "다운로드 상태를 확인하지 못했습니다.";
        setDownloadJob((current) =>
          current
            ? { ...current, status: "FAILED", error_message: message }
            : current,
        );
      }
    }, 1500);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [downloadJob]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSource(null);

    if (mode === "upload" && !file) {
      setError("업로드할 영상 파일을 선택해 주세요.");
      return;
    }

    setIsSubmitting(true);

    try {
      let response: Response;
      if (mode === "url") {
        response = await fetch(`${API_URL}/sources?prepare=true`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        });
      } else {
        const formData = new FormData();
        formData.append("file", file as File);
        response = await fetch(`${API_URL}/sources/upload`, {
          method: "POST",
          body: formData,
        });
      }

      const createdSource = await readJsonResponse<Source>(response);
      const duration = createdSource.metadata?.youtube?.duration_seconds;

      setSource(createdSource);
      setRangeStart(0);
      setRangeEnd(
        typeof duration === "number" && duration > 0
          ? Math.min(duration, DEFAULT_RANGE_SECONDS)
          : 0,
      );
      setDownloadJob(null);
      setRightsConfirmed(false);
      setTemplateId("CLEAN_CAPTION");
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Source를 생성하지 못했습니다.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleRangeDownload() {
    if (!source || rangeDuration <= 0 || rangeTooLong || !rightsConfirmed) return;
    setError(null);
    setDownloadJob(null);
    setIsStartingDownload(true);
    try {
      const response = await fetch(`${API_URL}/sources/${source.id}/downloads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_seconds: rangeStart,
          end_seconds: rangeEnd,
          rights_confirmed: true,
          template_id: templateId,
        }),
      });
      setDownloadJob(await readJsonResponse<DownloadJob>(response));
    } catch (downloadError) {
      setError(
        downloadError instanceof Error
          ? downloadError.message
          : "선택 구간 다운로드를 시작하지 못했습니다.",
      );
    } finally {
      setIsStartingDownload(false);
    }
  }

  function updateRangeStart(value: number) {
    setRangeStart(Math.max(0, Math.min(value, rangeEnd - 1)));
    setDownloadJob(null);
  }

  function updateRangeEnd(value: number) {
    if (typeof sourceDuration !== "number") return;
    setRangeEnd(Math.min(sourceDuration, Math.max(value, rangeStart + 1)));
    setDownloadJob(null);
  }

  const rangeStyle =
    typeof sourceDuration === "number" && sourceDuration > 0
      ? ({
          "--range-start": `${(rangeStart / sourceDuration) * 100}%`,
          "--range-end": `${(rangeEnd / sourceDuration) * 100}%`,
        } as CSSProperties)
      : undefined;

  return (
    <section className="source-panel" aria-labelledby="source-heading">
      <div className="source-heading">
        <div>
          <p className="section-label">START WITH ONE SOURCE</p>
          <h2 id="source-heading">Shorts 원본을 입력하세요</h2>
        </div>
        <div className="mode-switch" aria-label="Source 입력 방식">
          <button
            className={mode === "url" ? "active" : ""}
            type="button"
            onClick={() => setMode("url")}
          >
            URL
          </button>
          <button
            className={mode === "upload" ? "active" : ""}
            type="button"
            onClick={() => setMode("upload")}
          >
            Upload
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        {mode === "url" ? (
          <label className="field">
            <span>YouTube 또는 상품 URL</span>
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://"
              required
            />
          </label>
        ) : (
          <label className="field file-field">
            <span>영상 파일</span>
            <input
              type="file"
              accept="video/*,.mkv"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
        )}

        <button className="submit-button" type="submit" disabled={isSubmitting}>
          {isSubmitting ? "YouTube Source 처리 중..." : "Source 생성"}
        </button>
      </form>

      {error ? (
        <p className="message error-message" role="alert">
          {error}
        </p>
      ) : null}

      {source ? (
        <div className="source-result" aria-live="polite">
          <div className="source-result-header">
            <span>{source.type}</span>
            <strong>{source.status}</strong>
          </div>
          {source.metadata?.youtube ? (
            <div className="source-metadata">
              {source.metadata.youtube.thumbnail_url ? (
                // The remote host varies by video, so this stays a plain image.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={source.metadata.youtube.thumbnail_url}
                  alt=""
                />
              ) : null}
              <div>
                <h3>{source.metadata.youtube.title ?? "제목 없음"}</h3>
                <p>
                  {[
                    source.metadata.youtube.channel_title,
                    formatDuration(source.metadata.youtube.duration_seconds),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </div>
          ) : null}
          <code>{source.id}</code>
          {source.type === "YOUTUBE" &&
          source.status === "READY" &&
          typeof sourceDuration === "number" ? (
            <section className="range-picker" aria-labelledby="range-heading">
              <div className="range-heading-row">
                <div>
                  <h3 id="range-heading">사용할 영상 구간</h3>
                  <p>
                    시작과 종료 시간을 선택하세요. 분석용 480p로 준비하며 한 번에
                    최대 60분입니다.
                  </p>
                </div>
                <strong>
                  {formatDuration(rangeStart)} – {formatDuration(rangeEnd)}
                </strong>
              </div>

              <div className="range-slider" style={rangeStyle}>
                <span className="range-slider-track" aria-hidden="true" />
                <span className="range-slider-selection" aria-hidden="true" />
                <input
                  aria-label="구간 시작"
                  type="range"
                  min={0}
                  max={Math.max(1, Math.floor(sourceDuration))}
                  step={1}
                  value={rangeStart}
                  onChange={(event) => updateRangeStart(Number(event.target.value))}
                />
                <input
                  aria-label="구간 종료"
                  type="range"
                  min={0}
                  max={Math.max(1, Math.floor(sourceDuration))}
                  step={1}
                  value={rangeEnd}
                  onChange={(event) => updateRangeEnd(Number(event.target.value))}
                />
              </div>

              <div className="range-time-fields">
                <label>
                  <span>시작 시간(초)</span>
                  <input
                    type="number"
                    min={0}
                    max={Math.max(0, rangeEnd - 1)}
                    value={rangeStart}
                    onChange={(event) => updateRangeStart(Number(event.target.value))}
                  />
                </label>
                <label>
                  <span>종료 시간(초)</span>
                  <input
                    type="number"
                    min={rangeStart + 1}
                    max={sourceDuration}
                    value={rangeEnd}
                    onChange={(event) => updateRangeEnd(Number(event.target.value))}
                  />
                </label>
              </div>

              <p className={rangeTooLong ? "range-help range-error" : "range-help"}>
                선택 {formatDuration(rangeDuration)}
                {rangeTooLong ? " · 최대 60분을 초과했습니다." : ""}
              </p>

              <fieldset className="template-picker">
                <legend>쇼츠 템플릿</legend>
                <p>선택한 스타일은 Task 08 렌더링에서 적용됩니다.</p>
                <div className="template-options">
                  {TEMPLATES.map((template) => (
                    <button
                      key={template.id}
                      type="button"
                      className="template-card"
                      aria-pressed={templateId === template.id}
                      onClick={() => {
                        setTemplateId(template.id);
                        setDownloadJob(null);
                      }}
                    >
                      <span
                        className={`template-preview ${template.previewClassName}`}
                        aria-hidden="true"
                      >
                        <i>SHORTSFLOW</i>
                        <b>핵심 장면을 한눈에</b>
                      </span>
                      <strong>{template.name}</strong>
                      <small>{template.description}</small>
                    </button>
                  ))}
                </div>
              </fieldset>

              <label className="rights-confirmation">
                <input
                  type="checkbox"
                  checked={rightsConfirmed}
                  onChange={(event) => setRightsConfirmed(event.target.checked)}
                />
                <span>
                  <strong>원본 영상 권리 확인</strong>
                  <small>
                    이 영상은 내가 소유하고 있거나, 권리자로부터 쇼츠 제작·편집 및
                    이용에 필요한 허가를 받은 영상임을 확인합니다.
                  </small>
                </span>
              </label>

              <button
                className="submit-button"
                type="button"
                onClick={handleRangeDownload}
                disabled={
                  isStartingDownload ||
                  rangeDuration <= 0 ||
                  rangeTooLong ||
                  !rightsConfirmed
                }
              >
                {isStartingDownload ? "작업 생성 중..." : "480p 분석 구간 준비"}
              </button>

              {downloadJob ? (
                <div className="download-status" aria-live="polite">
                  <div>
                    <span>{downloadJob.status}</span>
                    <strong>{downloadJob.progress}%</strong>
                  </div>
                  <progress max={100} value={downloadJob.progress} />
                  {downloadJob.status === "FAILED" ? (
                    <p className="range-error">
                      {downloadJob.error_message ?? "선택 구간 처리에 실패했습니다."}
                    </p>
                  ) : null}
                  {downloadJob.status === "READY" && downloadJob.download_url ? (
                    <a
                      className="download-button"
                      href={`${API_URL}${downloadJob.download_url}`}
                    >
                      분석용 MP4 다운로드
                    </a>
                  ) : null}
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
