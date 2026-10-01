"use client";

import { useEffect, useState } from "react";
import type { CSSProperties, FormEvent } from "react";

import { API_URL } from "@/config";
import { formatTimecode } from "@/lib/timecode";
import { RenderResult } from "@/components/render-result";
import type { RenderJob } from "@/components/render-result";
import { creditCost, describeCreditBudget, minutesRoundedUp } from "@/lib/auth";
import { useAuthStatus } from "@/lib/auth-context";
import { currentDurationReader, putUpload } from "@/lib/upload";
import type { UploadTarget } from "@/lib/upload";

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
    upload?: {
      filename: string;
      content_type: string;
      size_bytes: number;
      duration_seconds: number | null;
    };
  };
};

type UploadSource = Source & { upload: UploadTarget };

type RankedCandidate = {
  candidate_id: string;
  index: number;
  rank: number;
  ai_score: number;
  reason: string;
  strengths: string[];
  concerns: string[];
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  hook_text: string;
};

type AnalysisJob = {
  id: string;
  status: "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
  step: "PIPELINE_BOOTSTRAP" | "TRANSCRIPT" | "CANDIDATE" | "RANKING" | "SHORT_RENDER";
  progress: number;
  error_message: string | null;
  result: {
    ranking?: { top_3: RankedCandidate[]; items: RankedCandidate[] };
    candidates?: { items: Array<{ id: string }> };
  } | null;
};

const DEFAULT_RANGE_SECONDS = 15 * 60;
const MAX_DIRECT_CLIP_SECONDS = 180;
const STEPS = ["소스", "구간·옵션", "추천", "결과"];
const MAX_RANGE_SECONDS = 60 * 60;
const POLL_INTERVAL_MS = 1500;
const SOURCE_CACHE_TTL_MS = 6 * 60 * 60 * 1000;
const SOURCE_CACHE_PREFIX = "shortsflow:source:";
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
const ANALYSIS_STEP_LABELS: Record<AnalysisJob["step"], string> = {
  PIPELINE_BOOTSTRAP: "준비 중",
  TRANSCRIPT: "자막·음성 분석 중",
  CANDIDATE: "후보 구간 만드는 중",
  RANKING: "AI Score 매기는 중",
  SHORT_RENDER: "렌더링 중",
};

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

function sourceCacheKey(url: string) {
  const trimmed = url.trim();
  try {
    const parsed = new URL(trimmed);
    const hostname = parsed.hostname.replace(/^(www\.|m\.)/, "");
    if (hostname === "youtu.be") {
      const videoId = parsed.pathname.split("/").filter(Boolean)[0];
      if (videoId) return `${SOURCE_CACHE_PREFIX}${videoId}`;
    }
    if (hostname === "youtube.com" || hostname.endsWith(".youtube.com")) {
      const videoId = parsed.searchParams.get("v");
      if (videoId) return `${SOURCE_CACHE_PREFIX}${videoId}`;
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (parts.length >= 2 && ["embed", "live", "shorts"].includes(parts[0])) {
        return `${SOURCE_CACHE_PREFIX}${parts[1]}`;
      }
    }
  } catch {
    // Invalid URLs are handled by the form and API validation.
  }
  return `${SOURCE_CACHE_PREFIX}${trimmed}`;
}

function readCachedSource(url: string): Source | null {
  try {
    const serialized = window.sessionStorage.getItem(sourceCacheKey(url));
    if (!serialized) return null;
    const cached = JSON.parse(serialized) as { cachedAt: number; source: Source };
    if (Date.now() - cached.cachedAt > SOURCE_CACHE_TTL_MS) {
      window.sessionStorage.removeItem(sourceCacheKey(url));
      return null;
    }
    return cached.source.status === "READY" ? cached.source : null;
  } catch {
    return null;
  }
}

function cacheSource(url: string, source: Source) {
  if (source.status !== "READY") return;
  try {
    window.sessionStorage.setItem(
      sourceCacheKey(url),
      JSON.stringify({ cachedAt: Date.now(), source }),
    );
  } catch {
    // Source caching is an optimization; storage denial must not block creation.
  }
}

const AFFILIATE_HOSTS = ["coupang.com", "agoda.com", "agoda.co.kr", "trip.com", "ctrip.com"];

function isAffiliateUrl(value: string) {
  try {
    const hostname = new URL(value).hostname.toLowerCase();
    return AFFILIATE_HOSTS.some((host) => hostname === host || hostname.endsWith(`.${host}`));
  } catch {
    return false;
  }
}

function costHint(authStatus: ReturnType<typeof useAuthStatus>["status"], rangeDuration: number) {
  const minutes = minutesRoundedUp(rangeDuration);
  const analysis = creditCost(authStatus, "analysis_per_minute", minutes);
  if (analysis === null) return "";
  const direct = creditCost(authStatus, "manual_short_per_minute", minutes);
  const directText =
    direct !== null && rangeDuration <= MAX_DIRECT_CLIP_SECONDS ? `, 직접 만들기 ${direct}크레딧` : "";
  const balance = typeof authStatus.credits === "number" ? ` (보유 ${authStatus.credits})` : "";
  return ` · AI 분석 ${analysis}크레딧${directText}${balance}`;
}

function isTerminalAnalysis(job: AnalysisJob | null) {
  return !job || job.status === "COMPLETED" || job.status === "FAILED";
}

function isTerminalRender(job: RenderJob | null) {
  return !job || job.status === "completed" || job.status === "failed";
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
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [templateId, setTemplateId] = useState<TemplateId>("CLEAN_CAPTION");
  const [transcriptLanguage, setTranscriptLanguage] = useState("ko");
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null);
  const [isStartingAnalysis, setIsStartingAnalysis] = useState(false);
  const [renderJob, setRenderJob] = useState<RenderJob | null>(null);
  const [isStartingRender, setIsStartingRender] = useState(false);
  const [lastCandidate, setLastCandidate] = useState<RankedCandidate | null>(null);
  const [directJob, setDirectJob] = useState<RenderJob | null>(null);
  const [isStartingDirect, setIsStartingDirect] = useState(false);
  const { status: authStatus } = useAuthStatus();

  const sourceDuration =
    source?.metadata?.youtube?.duration_seconds ??
    source?.metadata?.upload?.duration_seconds ??
    null;
  const [uploadStep, setUploadStep] = useState<string | null>(null);
  const rangeDuration = Math.max(0, rangeEnd - rangeStart);
  const rangeTooLong = rangeDuration > MAX_RANGE_SECONDS;
  const topCandidates = analysisJob?.result?.ranking?.top_3 ?? [];

  useEffect(() => {
    if (isTerminalAnalysis(analysisJob)) return;
    const job = analysisJob as AnalysisJob;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_URL}/processing-jobs/${job.id}`, {
          signal: controller.signal,
        });
        setAnalysisJob(await readJsonResponse<AnalysisJob>(response));
      } catch (pollError) {
        if (controller.signal.aborted) return;
        const message =
          pollError instanceof Error ? pollError.message : "분석 상태를 확인하지 못했습니다.";
        setAnalysisJob((current) =>
          current ? { ...current, status: "FAILED", error_message: message } : current,
        );
      }
    }, POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [analysisJob]);

  useEffect(() => {
    if (isTerminalRender(renderJob)) return;
    const job = renderJob as RenderJob;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_URL}/shorts/${job.id}`, {
          signal: controller.signal,
        });
        setRenderJob(await readJsonResponse<RenderJob>(response));
      } catch (pollError) {
        if (controller.signal.aborted) return;
        const message =
          pollError instanceof Error ? pollError.message : "렌더 상태를 확인하지 못했습니다.";
        setRenderJob((current) =>
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
  }, [renderJob]);

  useEffect(() => {
    if (isTerminalRender(directJob)) return;
    const job = directJob as RenderJob;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_URL}/shorts/${job.id}`, { signal: controller.signal });
        setDirectJob(await readJsonResponse<RenderJob>(response));
      } catch (pollError) {
        if (controller.signal.aborted) return;
        const message =
          pollError instanceof Error ? pollError.message : "렌더 상태를 확인하지 못했습니다.";
        setDirectJob((current) =>
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
  }, [directJob]);

  async function handleDirectRender() {
    if (!source || rangeDuration <= 0 || rangeDuration > MAX_DIRECT_CLIP_SECONDS || !rightsConfirmed) {
      return;
    }
    setError(null);
    setDirectJob(null);
    setIsStartingDirect(true);
    try {
      const response = await fetch(`${API_URL}/shorts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          youtube_url: source.type === "UPLOAD" ? undefined : url.trim(),
          source_id: source.id,
          start_seconds: rangeStart,
          end_seconds: rangeEnd,
          template_id: templateId,
          rights_confirmed: true,
        }),
      });
      setDirectJob(await readJsonResponse<RenderJob>(response));
    } catch (renderError) {
      setError(
        renderError instanceof Error ? renderError.message : "쇼츠 생성을 시작하지 못했습니다.",
      );
    } finally {
      setIsStartingDirect(false);
    }
  }

  function resetForSource(createdSource: Source) {
    const duration =
      createdSource.metadata?.youtube?.duration_seconds ??
      createdSource.metadata?.upload?.duration_seconds;
    setSource(createdSource);
    setRangeStart(0);
    setRangeEnd(
      typeof duration === "number" && duration > 0
        ? Math.min(duration, DEFAULT_RANGE_SECONDS)
        : 0,
    );
    setAnalysisJob(null);
    setRenderJob(null);
    setDirectJob(null);
    setRightsConfirmed(false);
    setTemplateId("CLEAN_CAPTION");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSource(null);

    if (mode === "upload" && !file) {
      setError("업로드할 영상 파일을 선택해 주세요.");
      return;
    }

    const requestedUrl = url.trim();
    if (mode === "url" && isAffiliateUrl(requestedUrl)) {
      setError("상품·여행 링크는 \"상품·여행 링크로 만들기\" 페이지에서 처리합니다. 상단 메뉴에서 이동해 주세요.");
      return;
    }
    if (mode === "url") {
      const cachedSource = readCachedSource(requestedUrl);
      if (cachedSource) {
        resetForSource(cachedSource);
        return;
      }
    }

    setIsSubmitting(true);
    try {
      if (mode === "url") {
        const response = await fetch(`${API_URL}/sources?prepare=true`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: requestedUrl }),
        });
        const createdSource = await readJsonResponse<Source>(response);
        cacheSource(requestedUrl, createdSource);
        resetForSource(createdSource);
      } else {
        resetForSource(await uploadFile(file as File));
      }
    } catch (submissionError) {
      setUploadStep(null);
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Source를 생성하지 못했습니다.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function uploadFile(selected: File): Promise<Source> {
    setUploadStep("영상 길이 확인 중...");
    const duration = await currentDurationReader()(selected);
    setUploadStep("업로드 준비 중...");
    const registered = await readJsonResponse<UploadSource>(
      await fetch(`${API_URL}/sources/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: selected.name,
          content_type: selected.type || "video/mp4",
          size_bytes: selected.size,
          duration_seconds: duration,
        }),
      }),
    );
    setUploadStep(`업로드 중... (${Math.round(selected.size / 1024 / 1024)}MB)`);
    await putUpload(registered.upload, selected);
    setUploadStep("업로드 확인 중...");
    const ready = await readJsonResponse<Source>(
      await fetch(`${API_URL}/sources/${registered.id}/uploaded`, { method: "POST" }),
    );
    setUploadStep(null);
    return ready;
  }

  async function handleAnalyze() {
    if (!source || rangeDuration <= 0 || rangeTooLong || !rightsConfirmed) return;
    setError(null);
    setAnalysisJob(null);
    setRenderJob(null);
    setIsStartingAnalysis(true);
    try {
      const response = await fetch(`${API_URL}/processing-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: source.id,
          source_url: source.type === "UPLOAD" ? undefined : url.trim(),
          start_seconds: rangeStart,
          end_seconds: rangeEnd,
          rights_confirmed: true,
          template_id: templateId,
          transcript_language: transcriptLanguage,
        }),
      });
      setAnalysisJob(await readJsonResponse<AnalysisJob>(response));
    } catch (analysisError) {
      setError(
        analysisError instanceof Error
          ? analysisError.message
          : "AI 추천 분석을 시작하지 못했습니다.",
      );
    } finally {
      setIsStartingAnalysis(false);
    }
  }

  async function handleRender(candidate: RankedCandidate) {
    if (!analysisJob) return;
    setError(null);
    setRenderJob(null);
    setLastCandidate(candidate);
    setIsStartingRender(true);
    try {
      const response = await fetch(`${API_URL}/shorts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          processing_job_id: analysisJob.id,
          candidate_id: candidate.candidate_id,
          rights_confirmed: true,
        }),
      });
      setRenderJob(await readJsonResponse<RenderJob>(response));
    } catch (renderError) {
      setError(
        renderError instanceof Error ? renderError.message : "쇼츠 렌더를 시작하지 못했습니다.",
      );
    } finally {
      setIsStartingRender(false);
    }
  }

  function updateRangeStart(value: number) {
    setRangeStart(Math.max(0, Math.min(value, rangeEnd - 1)));
    setAnalysisJob(null);
    setRenderJob(null);
  }

  function updateRangeEnd(value: number) {
    if (typeof sourceDuration !== "number") return;
    setRangeEnd(Math.min(sourceDuration, Math.max(value, rangeStart + 1)));
    setAnalysisJob(null);
    setRenderJob(null);
  }

  const rangeStyle =
    typeof sourceDuration === "number" && sourceDuration > 0
      ? ({
          "--range-start": `${(rangeStart / sourceDuration) * 100}%`,
          "--range-end": `${(rangeEnd / sourceDuration) * 100}%`,
        } as CSSProperties)
      : undefined;

  const analysisActive = analysisJob !== null && !isTerminalAnalysis(analysisJob);
  const renderActive = renderJob !== null && !isTerminalRender(renderJob);
  const directActive = directJob !== null && !isTerminalRender(directJob);
  const currentStep =
    renderJob || directJob
      ? 4
      : analysisJob?.status === "COMPLETED"
        ? 3
        : source?.status === "READY"
          ? 2
          : 1;

  return (
    <section className="source-panel" aria-labelledby="source-heading">
      <div className="source-heading">
        <div>
          <p className="section-label">LET’S MAKE A SHORT</p>
          <h2 id="source-heading">어떤 영상으로 만들까요?</h2>
        </div>
        <div className="mode-switch" aria-label="영상 입력 방식">
          <button
            className={mode === "url" ? "active" : ""}
            type="button"
            aria-pressed={mode === "url"}
            onClick={() => setMode("url")}
          >
            YouTube
          </button>
          <button
            className={mode === "upload" ? "active" : ""}
            type="button"
            aria-pressed={mode === "upload"}
            onClick={() => setMode("upload")}
          >
            파일 업로드
          </button>
        </div>
      </div>

      <ol className="stepper" aria-label="진행 단계">
        {STEPS.map((label, index) => {
          const number = index + 1;
          const state = number < currentStep ? "done" : number === currentStep ? "current" : "";
          return (
            <li key={label} className={state} aria-current={number === currentStep ? "step" : undefined}>
              <span>{number}</span>
              {label}
            </li>
          );
        })}
      </ol>

      {typeof authStatus.credits === "number" ? (
        <p className="credit-summary">
          남은 크레딧 <strong>{authStatus.credits}</strong>
          {describeCreditBudget(authStatus) ? ` · ${describeCreditBudget(authStatus)}` : ""}
          {" · 추천 구간 렌더는 무료"}
        </p>
      ) : null}

      <form onSubmit={handleSubmit}>
        <p className="form-intro">{mode === "url" ? "쇼츠로 만들 YouTube 영상 링크를 붙여 넣으세요." : "내 기기에 있는 영상 파일로 쇼츠를 만들어보세요."}</p>
        {mode === "url" ? (
          <label className="field">
            <span>YouTube URL</span>
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
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
          {isSubmitting
            ? uploadStep ?? (mode === "upload" ? "업로드 중..." : "영상 정보 불러오는 중...")
            : "영상 불러오기"}
        </button>
        <p className="input-footnote">다음 단계에서 구간과 자막 스타일을 선택할 수 있어요.</p>
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
          {source.metadata?.upload ? (
            <div className="source-metadata upload-metadata">
              <div>
                <h3>{source.metadata.upload.filename}</h3>
                <p>
                  {[
                    `${Math.max(1, Math.round(source.metadata.upload.size_bytes / 1024 / 1024))}MB`,
                    formatDuration(source.metadata.upload.duration_seconds),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
            </div>
          ) : null}
          {source.metadata?.youtube ? (
            <div className="source-metadata">
              {source.metadata.youtube.thumbnail_url ? (
                // The remote host varies by video, so this stays a plain image.
                // eslint-disable-next-line @next/next/no-img-element
                <img src={source.metadata.youtube.thumbnail_url} alt="" />
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
          {(source.type === "YOUTUBE" || source.type === "UPLOAD") &&
          source.status === "READY" &&
          typeof sourceDuration === "number" ? (
            <section className="range-picker" aria-labelledby="range-heading">
              <div className="range-heading-row">
                <div>
                  <h3 id="range-heading">분석할 영상 구간</h3>
                  <p>
                    이 구간의 자막을 분석해 15~60초 후보를 만들고 AI Score로 Top 3를
                    추천합니다. 한 번에 최대 60분입니다.
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
                {costHint(authStatus, rangeDuration)}
              </p>

              <label className="field language-field">
                <span>영상 언어</span>
                <select
                  aria-label="영상 언어"
                  value={transcriptLanguage}
                  onChange={(event) => setTranscriptLanguage(event.target.value)}
                >
                  <option value="ko">한국어</option>
                  <option value="en">English</option>
                  <option value="ja">日本語</option>
                </select>
              </label>

              <fieldset className="template-picker">
                <legend>자막 템플릿</legend>
                <p>선택한 스타일로 자막을 얹어 렌더링합니다.</p>
                <div className="template-options">
                  {TEMPLATES.map((template) => (
                    <button
                      key={template.id}
                      type="button"
                      className="template-card"
                      aria-pressed={templateId === template.id}
                      onClick={() => setTemplateId(template.id)}
                    >
                      <span
                        className={`template-preview ${template.previewClassName}`}
                        aria-hidden="true"
                      >
                        <i>CUTPICK</i>
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
                onClick={handleAnalyze}
                disabled={
                  isStartingAnalysis ||
                  analysisActive ||
                  rangeDuration <= 0 ||
                  rangeTooLong ||
                  !rightsConfirmed
                }
              >
                {isStartingAnalysis
                  ? "분석 시작 중..."
                  : analysisActive
                    ? "분석 중..."
                    : "AI 추천 구간 찾기"}
              </button>

              <button
                className="submit-button secondary-button"
                type="button"
                onClick={handleDirectRender}
                disabled={
                  isStartingDirect ||
                  directActive ||
                  rangeDuration <= 0 ||
                  rangeDuration > MAX_DIRECT_CLIP_SECONDS ||
                  !rightsConfirmed
                }
                title={
                  rangeDuration > MAX_DIRECT_CLIP_SECONDS
                    ? `직접 만들기는 ${MAX_DIRECT_CLIP_SECONDS}초 이하 구간만 가능합니다`
                    : undefined
                }
              >
                {isStartingDirect
                  ? "작업 등록 중..."
                  : directActive
                    ? "렌더링 중..."
                    : rangeDuration > MAX_DIRECT_CLIP_SECONDS
                      ? `이 구간 그대로 만들기 (${MAX_DIRECT_CLIP_SECONDS}초 이하만)`
                      : "이 구간 그대로 만들기"}
              </button>

              {directJob ? (
                <RenderResult
                  job={directJob}
                  onRetry={() => void handleDirectRender()}
                  retryDisabled={isStartingDirect}
                />
              ) : null}

              {analysisJob ? (
                <div className="download-status" aria-live="polite">
                  <div>
                    <span>
                      {analysisJob.status === "COMPLETED"
                        ? "분석 완료"
                        : analysisJob.status === "FAILED"
                          ? "분석 실패"
                          : ANALYSIS_STEP_LABELS[analysisJob.step]}
                    </span>
                    <strong>{analysisJob.progress}%</strong>
                  </div>
                  <progress max={100} value={analysisJob.progress} />
                  {analysisJob.status === "FAILED" ? (
                    <p className="range-error">
                      {analysisJob.error_message ?? "AI 추천 분석에 실패했습니다."}
                    </p>
                  ) : null}
                </div>
              ) : null}

              {analysisJob?.status === "COMPLETED" ? (
                <section className="candidate-list" aria-labelledby="top3-heading">
                  <h3 id="top3-heading">AI 추천 Top 3</h3>
                  {topCandidates.length === 0 ? (
                    <p className="range-help">추천할 후보를 찾지 못했습니다.</p>
                  ) : null}
                  {topCandidates.map((candidate) => {
                    const isSelected = renderJob?.candidate_id === candidate.candidate_id;
                    return (
                      <article
                        key={candidate.candidate_id}
                        className={isSelected ? "candidate-card selected" : "candidate-card"}
                      >
                        <header>
                          <span className="candidate-rank">#{candidate.rank}</span>
                          <span className="ai-score">
                            AI Score <strong>{candidate.ai_score}</strong>
                          </span>
                          <span className="candidate-time">
                            {formatTimecode(candidate.start_seconds)} –{" "}
                            {formatTimecode(candidate.end_seconds)} ·{" "}
                            {Math.round(candidate.duration_seconds)}초
                          </span>
                        </header>
                        <p className="candidate-hook">“{candidate.hook_text}”</p>
                        <p className="candidate-reason">{candidate.reason}</p>
                        {candidate.strengths.length > 0 ? (
                          <ul className="candidate-tags">
                            {candidate.strengths.map((strength) => (
                              <li key={strength}>{strength}</li>
                            ))}
                          </ul>
                        ) : null}
                        <button
                          type="button"
                          className="submit-button"
                          onClick={() => handleRender(candidate)}
                          disabled={isStartingRender || renderActive}
                        >
                          {isSelected && renderActive
                            ? "렌더링 중..."
                            : "이 구간으로 쇼츠 만들기"}
                        </button>
                      </article>
                    );
                  })}
                </section>
              ) : null}

              {renderJob ? (
                <RenderResult
                  job={renderJob}
                  onRetry={() => {
                    if (lastCandidate) void handleRender(lastCandidate);
                  }}
                  retryDisabled={isStartingRender}
                />
              ) : null}
            </section>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
