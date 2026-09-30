"use client";

import { useEffect, useState } from "react";
import type { CSSProperties, FormEvent } from "react";

import { API_URL } from "@/config";
import { formatTimecode } from "@/lib/timecode";

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

type RenderJob = {
  id: string;
  status: "queued" | "downloading" | "processing" | "uploading" | "completed" | "failed";
  progress: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  template_id: TemplateId;
  candidate_id: string | null;
  download_url: string | null;
  preview_url: string | null;
  captions_applied: number;
  error_message: string | null;
};

const DEFAULT_RANGE_SECONDS = 15 * 60;
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
const RENDER_STATUS_LABELS: Record<RenderJob["status"], string> = {
  queued: "대기 중",
  downloading: "원본 영상 확보 중",
  processing: "구간 자르기 · 자막 · 9:16 변환 중",
  uploading: "완성 파일 저장 중",
  completed: "완료",
  failed: "실패",
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

function resolveApiUrl(url: string) {
  if (/^https:\/\//i.test(url)) return url;
  return `${API_URL}${url}`;
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

  const sourceDuration = source?.metadata?.youtube?.duration_seconds ?? null;
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
          current ? { ...current, status: "failed", error_message: message } : current,
        );
      }
    }, POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [renderJob]);

  function resetForSource(createdSource: Source) {
    const duration = createdSource.metadata?.youtube?.duration_seconds;
    setSource(createdSource);
    setRangeStart(0);
    setRangeEnd(
      typeof duration === "number" && duration > 0
        ? Math.min(duration, DEFAULT_RANGE_SECONDS)
        : 0,
    );
    setAnalysisJob(null);
    setRenderJob(null);
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
    if (mode === "url") {
      const cachedSource = readCachedSource(requestedUrl);
      if (cachedSource) {
        resetForSource(cachedSource);
        return;
      }
    }

    setIsSubmitting(true);
    try {
      let response: Response;
      if (mode === "url") {
        response = await fetch(`${API_URL}/sources?prepare=true`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: requestedUrl }),
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
      if (mode === "url") cacheSource(requestedUrl, createdSource);
      resetForSource(createdSource);
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
          source_url: url.trim(),
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

  return (
    <section className="source-panel" aria-labelledby="source-heading">
      <div className="source-heading">
        <div>
          <p className="section-label">AI RECOMMENDED SHORTS</p>
          <h2 id="source-heading">AI가 추천하는 구간으로 만들기</h2>
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
          {source.type === "YOUTUBE" &&
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
                <div className="download-status" aria-live="polite">
                  <div>
                    <span>{RENDER_STATUS_LABELS[renderJob.status]}</span>
                    <strong>{renderJob.progress}%</strong>
                  </div>
                  <progress max={100} value={renderJob.progress} />
                  <p className="shorts-status-range">
                    {formatTimecode(renderJob.start_seconds)} –{" "}
                    {formatTimecode(renderJob.end_seconds)} · {renderJob.template_id}
                    {renderJob.status === "completed"
                      ? ` · 자막 ${renderJob.captions_applied}개`
                      : ""}
                  </p>
                  {renderJob.status === "failed" ? (
                    <p className="range-error">
                      {renderJob.error_message ?? "쇼츠 렌더에 실패했습니다."}
                    </p>
                  ) : null}
                  {renderJob.status === "completed" && renderJob.preview_url ? (
                    <video
                      className="preview-video"
                      controls
                      playsInline
                      preload="metadata"
                      src={resolveApiUrl(renderJob.preview_url)}
                      aria-label="완성된 쇼츠 미리보기"
                    />
                  ) : null}
                  {renderJob.status === "completed" && renderJob.download_url ? (
                    <a
                      className="download-button"
                      href={resolveApiUrl(renderJob.download_url)}
                    >
                      쇼츠 다운로드
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
