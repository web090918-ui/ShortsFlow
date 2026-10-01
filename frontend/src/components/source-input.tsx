"use client";

import { useEffect, useState } from "react";
import type { CSSProperties, FormEvent } from "react";

import { API_URL } from "@/config";
import { formatTimecode } from "@/lib/timecode";
import { RenderResult } from "@/components/render-result";
import { SourcePlayer } from "@/components/source-player";
import type { RenderJob } from "@/components/render-result";
import { creditCost, describeCreditBudget, minutesRoundedUp } from "@/lib/auth";
import { useAuthStatus } from "@/lib/auth-context";
import {
  BrandColorPicker,
  CaptionPositionPicker,
  LayoutPicker,
  TemplatePicker,
} from "@/components/template-picker";
import { useRenderOptions } from "@/lib/render-options-context";
import {
  DEFAULT_BRAND_COLOR,
  DEFAULT_CAPTION_POSITION,
  DEFAULT_LAYOUT_ID,
  DEFAULT_TEMPLATE_ID,
  OUTPUT_LANGUAGES,
  SOURCE_LANGUAGES,
} from "@/lib/render-options";
import type { CaptionPosition, FrameLayout } from "@/lib/render-options";
import { currentDurationReader, currentFrameCapturer, putUpload } from "@/lib/upload";
import type { UploadTarget } from "@/lib/upload";

type InputMode = "url" | "upload";

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
  title?: string | null;
  description?: string | null;
};

type ShortMeta = { title: string; description: string };

const MAX_SHORT_TITLE = 100;
const MAX_SHORT_DESCRIPTION = 500;

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
const ANALYSIS_STEP_LABELS: Record<AnalysisJob["step"], string> = {
  PIPELINE_BOOTSTRAP: "준비 중",
  TRANSCRIPT: "영상을 듣고 받아 적는 중",
  CANDIDATE: "눈에 띄는 장면을 찾는 중",
  RANKING: "AI가 베스트를 고르는 중",
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
  const [playbackSource, setPlaybackSource] = useState<{ youtubeUrl?: string; file?: File }>({});
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rangeStart, setRangeStart] = useState(0);
  const [rangeEnd, setRangeEnd] = useState(0);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [templateId, setTemplateId] = useState(DEFAULT_TEMPLATE_ID);
  const [layoutId, setLayoutId] = useState<FrameLayout["id"]>(DEFAULT_LAYOUT_ID);
  const [brandColor, setBrandColor] = useState(DEFAULT_BRAND_COLOR);
  const [captionPosition, setCaptionPosition] = useState<CaptionPosition["id"]>(DEFAULT_CAPTION_POSITION);
  const [outputLanguage, setOutputLanguage] = useState("ko");
  // Headline drawn on top of the Short; [brackets] mark the coloured keyword.
  const [title, setTitle] = useState("");
  // One frame of the chosen file, shown inside the template previews.
  const [sampleFrame, setSampleFrame] = useState<string | null>(null);
  const renderOptions = useRenderOptions();
  const [transcriptLanguage, setTranscriptLanguage] = useState("ko");
  const [analysisJob, setAnalysisJob] = useState<AnalysisJob | null>(null);
  const [isStartingAnalysis, setIsStartingAnalysis] = useState(false);
  const [renderJob, setRenderJob] = useState<RenderJob | null>(null);
  const [isStartingRender, setIsStartingRender] = useState(false);
  const [lastCandidate, setLastCandidate] = useState<RankedCandidate | null>(null);
  // Candidate chosen from the Top 3, with the AI-suggested title/description to edit.
  const [pickedCandidate, setPickedCandidate] = useState<RankedCandidate | null>(null);
  const [shortMeta, setShortMeta] = useState<ShortMeta>({ title: "", description: "" });
  const [directJob, setDirectJob] = useState<RenderJob | null>(null);
  const [isStartingDirect, setIsStartingDirect] = useState(false);
  const { status: authStatus } = useAuthStatus();

  const sourceDuration =
    source?.metadata?.youtube?.duration_seconds ??
    source?.metadata?.upload?.duration_seconds ??
    null;
  const sampleImageUrl = source?.metadata?.youtube?.thumbnail_url ?? sampleFrame;
  const channelName = source?.metadata?.youtube?.channel_title ?? authStatus.user?.name ?? null;
  const selectedTemplate = renderOptions.templates.find((template) => template.id === templateId);
  const supportsCaptionPosition = selectedTemplate?.preview.positionable === "true"
    && selectedTemplate.preview.caption !== "none";
  const effectiveCaptionPosition = supportsCaptionPosition ? captionPosition : "BOTTOM";
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
          layout_id: layoutId,
          ...(title.trim() ? { title: title.trim() } : {}),
          brand_color: brandColor,
          caption_position: effectiveCaptionPosition,
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

  function resetForSource(createdSource: Source, playback: { youtubeUrl?: string; file?: File }) {
    const duration =
      createdSource.metadata?.youtube?.duration_seconds ??
      createdSource.metadata?.upload?.duration_seconds;
    setSource(createdSource);
    setPlaybackSource(playback);
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
    setTemplateId(DEFAULT_TEMPLATE_ID);
    setPickedCandidate(null);
    setShortMeta({ title: "", description: "" });
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
        resetForSource(cachedSource, { youtubeUrl: requestedUrl });
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
        resetForSource(createdSource, { youtubeUrl: requestedUrl });
      } else {
        resetForSource(await uploadFile(file as File), { file: file as File });
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

  function handleFileChange(selected: File | null) {
    setFile(selected);
    setSampleFrame(null);
    if (!selected) return;
    currentFrameCapturer()(selected)
      .then((frame) => setSampleFrame(frame))
      .catch(() => setSampleFrame(null));
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
          layout_id: layoutId,
          ...(title.trim() ? { title: title.trim() } : {}),
          brand_color: brandColor,
          caption_position: effectiveCaptionPosition,
          transcript_language: transcriptLanguage,
          output_language: outputLanguage,
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

  function pickCandidate(candidate: RankedCandidate) {
    setPickedCandidate(candidate);
    setShortMeta({
      title: (candidate.title ?? title).slice(0, MAX_SHORT_TITLE),
      description: (candidate.description ?? "").slice(0, MAX_SHORT_DESCRIPTION),
    });
  }

  async function handleRender(candidate: RankedCandidate, meta: ShortMeta = shortMeta) {
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
          template_id: templateId,
          layout_id: layoutId,
          brand_color: brandColor,
          caption_position: effectiveCaptionPosition,
          ...(meta.title.trim() ? { title: meta.title.trim() } : {}),
          ...(meta.description.trim() ? { description: meta.description.trim() } : {}),
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
              onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
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
              <SourcePlayer
                key={source.id}
                {...playbackSource}
                start={rangeStart}
                end={rangeEnd}
                onStart={updateRangeStart}
                onEnd={updateRangeEnd}
              />
              <div className="range-heading-row">
                <div>
                  <h3 id="range-heading">분석할 영상 구간</h3>
                  <p>
                    AI 추천은 <strong>이 구간 안에서만</strong> 15~60초 후보를 찾아 AI Score로
                    Top 3를 고릅니다. 넓게 잡을수록 선택지가 많아지고, 크레딧은 구간의 분 수만큼
                    차감됩니다 (최대 60분). 원하는 장면을 이미 알면 좁게 잡고 ‘이 구간 그대로
                    만들기’를 쓰세요.
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

              <section className="language-card" aria-labelledby="language-heading">
                <h4 id="language-heading">언어 선택</h4>
                <div className="language-grid">
                  <label className="field language-field">
                    <span>
                      영상 언어
                      <small>원본 영상에서 사용하는 음성 언어</small>
                    </span>
                    <select
                      aria-label="영상 언어"
                      value={transcriptLanguage}
                      onChange={(event) => setTranscriptLanguage(event.target.value)}
                    >
                      {SOURCE_LANGUAGES.map((language) => (
                        <option key={language.id} value={language.id}>
                          {language.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field language-field">
                    <span>
                      제작 언어
                      <small>제목·설명·AI 추천 이유에 사용할 언어</small>
                    </span>
                    <select
                      aria-label="제작 언어"
                      value={outputLanguage}
                      onChange={(event) => setOutputLanguage(event.target.value)}
                    >
                      {OUTPUT_LANGUAGES.map((language) => (
                        <option key={language.id} value={language.id}>
                          {language.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <p className="range-help">원본 음성과 영상에 이미 들어간 글자는 유지됩니다.</p>
              </section>

              <section className="video-design-options" aria-labelledby="video-design-heading">
                <div className="video-design-heading">
                  <div>
                    <h4 id="video-design-heading">영상 디자인</h4>
                    <p>화면 배치를 먼저 고르고, 아래에서 템플릿을 비교하세요.</p>
                  </div>
                  <span className="output-ratio-label">9:16 쇼츠</span>
                </div>
                <LayoutPicker
                  layouts={renderOptions.layouts}
                  value={layoutId}
                  onChange={setLayoutId}
                  imageUrl={sampleImageUrl}
                  stageColor={selectedTemplate?.preview.stage ?? "#000000"}
                  compact
                />

              <label className="field title-field">
                <span>쇼츠 제목 (선택)</span>
                <textarea
                  aria-label="쇼츠 제목"
                  value={title}
                  maxLength={80}
                  rows={2}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder={"한 줄 또는 두 줄로 쓰고, 강조할 단어는 [대괄호]로 감싸세요\n비우면 AI 추천 구간의 짧은 훅 문장을 제목으로 씁니다"}
                />
              </label>

              <TemplatePicker
                templates={renderOptions.templates}
                value={templateId}
                onChange={setTemplateId}
                layout={layoutId}
                imageUrl={sampleImageUrl}
                title={title}
                brandColor={brandColor}
                captionPosition={captionPosition}
                channelName={channelName}
              />

              <div className="render-options-row">
                <BrandColorPicker
                  swatches={renderOptions.brand_colors}
                  value={brandColor}
                  onChange={setBrandColor}
                />
              </div>

              {supportsCaptionPosition ? (
                <CaptionPositionPicker
                  positions={renderOptions.caption_positions}
                  value={captionPosition}
                  onChange={setCaptionPosition}
                />
              ) : null}

              </section>

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
                  ? "AI를 깨우는 중..."
                  : analysisActive
                    ? "AI가 고르는 중..."
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
                  ? "시작하는 중..."
                  : directActive
                    ? "재미나게 만드는 중..."
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
                        ? "추천 준비 완료!"
                        : analysisJob.status === "FAILED"
                          ? "앗, 분석에 문제가 생겼어요"
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
                    const isSelected =
                      renderJob?.candidate_id === candidate.candidate_id ||
                      (!renderJob && pickedCandidate?.candidate_id === candidate.candidate_id);
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
                          onClick={() => pickCandidate(candidate)}
                          disabled={isStartingRender || renderActive}
                          aria-pressed={pickedCandidate?.candidate_id === candidate.candidate_id}
                        >
                          {isSelected && renderActive
                            ? "재미나게 만드는 중..."
                            : pickedCandidate?.candidate_id === candidate.candidate_id
                              ? "선택됨 · 아래에서 제목 확인"
                              : "이 구간 선택"}
                        </button>
                      </article>
                    );
                  })}
                </section>
              ) : null}

              {analysisJob?.status === "COMPLETED" && pickedCandidate ? (
                <section className="short-meta" aria-labelledby="short-meta-heading">
                  <h3 id="short-meta-heading">제목과 설명</h3>
                  <p className="range-help">
                    AI가 추천한 문구예요. 자유롭게 고쳐 쓰세요. 제목은 영상 위 헤드라인으로도
                    들어가고, [대괄호]로 감싼 단어가 강조색이 됩니다. 설명은 나중에 업로드할 때
                    씁니다.
                  </p>
                  <label className="field">
                    <span>
                      제목
                      <small className="field-counter">
                        {shortMeta.title.length} / {MAX_SHORT_TITLE}
                      </small>
                    </span>
                    <textarea
                      aria-label="쇼츠 제목 추천"
                      rows={2}
                      maxLength={MAX_SHORT_TITLE}
                      value={shortMeta.title}
                      onChange={(event) =>
                        setShortMeta((current) => ({ ...current, title: event.target.value }))
                      }
                      placeholder="예: 독립을 위해 [목숨]을 건 여자"
                    />
                  </label>
                  <label className="field">
                    <span>
                      설명
                      <small className="field-counter">
                        {shortMeta.description.length} / {MAX_SHORT_DESCRIPTION}
                      </small>
                    </span>
                    <textarea
                      aria-label="쇼츠 설명 추천"
                      rows={4}
                      maxLength={MAX_SHORT_DESCRIPTION}
                      value={shortMeta.description}
                      onChange={(event) =>
                        setShortMeta((current) => ({ ...current, description: event.target.value }))
                      }
                      placeholder="영상 설명과 해시태그를 적어 두면 업로드할 때 그대로 씁니다."
                    />
                  </label>
                  <button
                    type="button"
                    className="submit-button"
                    onClick={() => handleRender(pickedCandidate)}
                    disabled={isStartingRender || renderActive}
                  >
                    {renderActive ? "재미나게 만드는 중..." : "이 제목으로 쇼츠 만들기"}
                  </button>
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
