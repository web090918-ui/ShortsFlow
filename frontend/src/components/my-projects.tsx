"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { API_URL } from "@/config";
import { RenderResult } from "@/components/render-result";
import type { RenderJob } from "@/components/render-result";
import { formatTimecode } from "@/lib/timecode";
import { describeCreditBudget, loginUrl } from "@/lib/auth";
import { useAuthStatus } from "@/lib/auth-context";

export type ProjectSummary = {
  source_id: string;
  title: string;
  source_type: string;
  source_url: string;
  thumbnail_url: string | null;
  channel_title: string | null;
  duration_seconds: number | null;
  status: "completed" | "processing" | "failed";
  shorts_count: number;
  analyses_count: number;
  created_at: string;
  updated_at: string;
};

type AnalysisSummary = {
  id: string;
  status: "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
  step: string;
  progress: number;
  source_url: string;
  start_seconds: number;
  end_seconds: number;
  transcript_language: string;
  top_hooks: string[];
  candidate_count: number;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
};

type CreditEntry = {
  id: string;
  delta: number;
  reason: "signup" | "analysis" | "short" | "product_short" | "refund" | "purchase" | "adjustment";
  note: string | null;
  balance_after: number;
  created_at: string;
};

type CreditSummary = { balance: number; entries: CreditEntry[] };

const CREDIT_REASONS: Record<CreditEntry["reason"], string> = {
  signup: "가입 보너스",
  analysis: "AI 분석",
  short: "쇼츠 렌더",
  product_short: "상품 쇼츠",
  refund: "환불",
  purchase: "구매",
  adjustment: "조정",
};

export type WorkItem =
  | { kind: "short"; created_at: string; short: RenderJob & { youtube_url: string } }
  | { kind: "analysis"; created_at: string; analysis: AnalysisSummary };

const PROJECT_STATUS: Record<ProjectSummary["status"], string> = {
  completed: "완료됨",
  processing: "진행 중",
  failed: "실패",
};

const ANALYSIS_LABELS: Record<AnalysisSummary["status"], string> = {
  QUEUED: "차례를 기다리는 중",
  PROCESSING: "분석 중",
  COMPLETED: "추천 준비 완료!",
  FAILED: "앗, 분석에 문제가 생겼어요",
};

function formatDate(iso: string, withTime = true) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(
    "ko-KR",
    withTime
      ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
      : { year: "numeric", month: "numeric", day: "numeric" },
  ).format(date);
}

function formatDuration(seconds: number | null) {
  if (typeof seconds !== "number" || seconds <= 0) return null;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}시간 ${minutes}분`;
  return `${Math.max(1, minutes)}분`;
}

function describeSource(url: string) {
  if (url.startsWith("upload://")) return "업로드한 영상";
  try {
    const parsed = new URL(url);
    if (parsed.hostname.includes("coupang")) return "쿠팡 파트너스 상품";
    const id = parsed.searchParams.get("v") ?? parsed.pathname.split("/").filter(Boolean).pop();
    return id ? `YouTube · ${id}` : "YouTube";
  } catch {
    return url;
  }
}

async function fetchJson<T>(path: string, failure: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { credentials: "include" });
  if (!response.ok) throw new Error(failure);
  return (await response.json()) as T;
}

function CreditCard({ credits }: { credits: CreditSummary }) {
  const { status } = useAuthStatus();
  return (
    <section className="source-panel credit-card" aria-labelledby="credit-heading">
      <div className="source-heading">
        <div>
          <p className="section-label">CREDITS</p>
          <h2 id="credit-heading">남은 크레딧 {credits.balance}</h2>
        </div>
      </div>
      <p className="credit-summary">
        지금 잔액으로 {describeCreditBudget({ ...status, credits: credits.balance }) ?? "작업"}을 만들 수
        있어요.
      </p>
      <ul className="credit-rules">
        <li>1크레딧 = 원본 영상 1분 분석 (올림). 15분 구간이면 15크레딧.</li>
        <li>추천 Top 3 중 하나를 렌더하는 것은 무료. 직접 지정 쇼츠는 클립 1분당 1크레딧.</li>
        <li>상품 쇼츠는 1편 5크레딧. 콘텐츠 앵글 만들기는 무료.</li>
        <li>작업 생성 시 차감되고, 최종 실패하면 자동으로 되돌려 드립니다.</li>
      </ul>
      {credits.entries.length > 0 ? (
        <ul className="credit-entries">
          {credits.entries.slice(0, 10).map((entry) => (
            <li key={entry.id}>
              <span>
                {CREDIT_REASONS[entry.reason] ?? entry.reason}
                {entry.note ? ` · ${entry.note}` : ""}
              </span>
              <strong className={entry.delta < 0 ? "debit" : "credit"}>
                {entry.delta > 0 ? `+${entry.delta}` : entry.delta}
              </strong>
              <time dateTime={entry.created_at}>{formatDate(entry.created_at)}</time>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** Project card like a video thumbnail: status badge, duration, title, counts, date. */
export function ProjectCard({ project }: { project: ProjectSummary }) {
  const duration = formatDuration(project.duration_seconds);
  return (
    <Link href={`/my/${project.source_id}`} className="project-card" aria-label={`${project.title} 프로젝트 열기`}>
      <span className="project-thumb">
        {project.thumbnail_url ? (
          // Thumbnail hosts vary (YouTube, Coupang CDN); a plain image avoids remote-pattern config.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={project.thumbnail_url} alt="" />
        ) : (
          <span className="project-thumb-empty">{describeSource(project.source_url)}</span>
        )}
        <span className={`project-status project-status-${project.status}`}>{PROJECT_STATUS[project.status]}</span>
        {duration ? <span className="project-duration">{duration}</span> : null}
      </span>
      <strong className="project-title">{project.title}</strong>
      <span className="project-meta">
        <span className={`project-dot project-dot-${project.status}`}>{PROJECT_STATUS[project.status]}</span>
        <span>쇼츠 {project.shorts_count}개</span>
        <time dateTime={project.created_at}>{formatDate(project.created_at, false)}</time>
      </span>
    </Link>
  );
}

function WorkItems({ items, emptyText }: { items: WorkItem[]; emptyText: string }) {
  const router = useRouter();
  if (items.length === 0) return <p className="range-help">{emptyText}</p>;
  return (
    <section className="my-works" aria-label="생성된 작업 목록">
      {items.map((item) =>
        item.kind === "short" ? (
          <article key={item.short.id} className="work-card">
            <header>
              <span className="work-kind">쇼츠</span>
              <span className="work-source">{item.short.title ?? describeSource(item.short.youtube_url)}</span>
              <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
            </header>
            <RenderResult job={item.short} onRetry={() => router.push("/video")} />
          </article>
        ) : (
          <article key={item.analysis.id} className="work-card">
            <header>
              <span className="work-kind">AI 분석</span>
              <span className="work-source">
                {formatTimecode(item.analysis.start_seconds)} – {formatTimecode(item.analysis.end_seconds)}
              </span>
              <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
            </header>
            <div className="download-status">
              <div>
                <span>{ANALYSIS_LABELS[item.analysis.status]}</span>
                <strong>{item.analysis.progress}%</strong>
              </div>
              <p className="shorts-status-range">후보 {item.analysis.candidate_count}개</p>
              {item.analysis.top_hooks.length > 0 ? (
                <ol className="angle-script">
                  {item.analysis.top_hooks.map((hook, index) => (
                    <li key={`${item.analysis.id}-${index}`}>{hook}</li>
                  ))}
                </ol>
              ) : null}
              {item.analysis.error_message ? <p className="range-error">{item.analysis.error_message}</p> : null}
            </div>
          </article>
        ),
      )}
    </section>
  );
}

function LoginNeeded({ next }: { next: string }) {
  return (
    <section className="source-panel login-gate">
      <h2>내 프로젝트를 보려면 로그인하세요</h2>
      <a className="submit-button auth-login-button" href={loginUrl(next)}>
        Google로 로그인
      </a>
    </section>
  );
}

/** /my: one card per source video the signed-in user worked on. */
export function MyProjects({ onCount }: { onCount?: (count: number) => void }) {
  const { status, loading } = useAuthStatus();
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [credits, setCredits] = useState<CreditSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !status.user) return;
    let cancelled = false;
    fetchJson<CreditSummary>("/me/credits", "크레딧을 불러오지 못했습니다.")
      .then((summary) => {
        if (!cancelled) setCredits(summary);
      })
      .catch(() => undefined);
    fetchJson<{ items: ProjectSummary[] }>("/me/projects", "프로젝트 목록을 불러오지 못했습니다.")
      .then((payload) => {
        if (cancelled) return;
        setProjects(payload.items);
        onCount?.(payload.items.length);
      })
      .catch((loadError: unknown) => {
        if (!cancelled)
          setError(loadError instanceof Error ? loadError.message : "프로젝트 목록을 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [loading, status.user, onCount]);

  useEffect(() => {
    if (credits && projects && window.location.hash === "#credit-heading") {
      document.getElementById("credit-heading")?.scrollIntoView();
    }
  }, [credits, projects]);

  if (loading) {
    return (
      <section className="source-panel" aria-busy="true">
        <p className="range-help">불러오는 중...</p>
      </section>
    );
  }
  if (!status.user) return <LoginNeeded next="/my" />;
  if (error) {
    return (
      <section className="source-panel">
        <p className="message error-message" role="alert">
          {error}
        </p>
      </section>
    );
  }
  if (projects === null) {
    return (
      <section className="source-panel" aria-busy="true">
        <p className="range-help">프로젝트를 불러오는 중...</p>
      </section>
    );
  }

  return (
    <>
      {projects.length === 0 ? (
        <section className="source-panel">
          <h2>아직 프로젝트가 없습니다</h2>
          <p className="range-help">영상이나 상품 링크로 첫 쇼츠를 만들어 보세요. 원본 영상 하나가 프로젝트 하나가 됩니다.</p>
          <div className="my-works-actions">
            <Link className="submit-button" href="/video">
              영상으로 만들기
            </Link>
            <Link className="submit-button secondary-button" href="/affiliate">
              상품 링크로 만들기
            </Link>
          </div>
        </section>
      ) : (
        <section className="project-grid" aria-label="내 프로젝트 목록">
          {projects.map((project) => (
            <ProjectCard key={project.source_id} project={project} />
          ))}
        </section>
      )}
      {credits ? <CreditCard credits={credits} /> : null}
    </>
  );
}

/** /my/[sourceId]: everything made from one source video. */
export function ProjectDetail({ sourceId }: { sourceId: string }) {
  const { status, loading } = useAuthStatus();
  const [detail, setDetail] = useState<{ project: ProjectSummary; items: WorkItem[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !status.user) return;
    let cancelled = false;
    fetchJson<{ project: ProjectSummary; items: WorkItem[] }>(
      `/me/projects/${sourceId}`,
      "프로젝트를 불러오지 못했습니다.",
    )
      .then((payload) => {
        if (!cancelled) setDetail(payload);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "프로젝트를 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [loading, status.user, sourceId]);

  if (loading) {
    return (
      <section className="source-panel" aria-busy="true">
        <p className="range-help">불러오는 중...</p>
      </section>
    );
  }
  if (!status.user) return <LoginNeeded next={`/my/${sourceId}`} />;
  if (error) {
    return (
      <section className="source-panel">
        <p className="message error-message" role="alert">
          {error}
        </p>
        <Link href="/my" className="back-link">
          ← 내 프로젝트
        </Link>
      </section>
    );
  }
  if (detail === null) {
    return (
      <section className="source-panel" aria-busy="true">
        <p className="range-help">프로젝트를 불러오는 중...</p>
      </section>
    );
  }
  const { project, items } = detail;
  const shorts = items.filter((item) => item.kind === "short");
  const analyses = items.filter((item) => item.kind === "analysis");
  return (
    <>
      <section className="project-hero">
        <span className="project-thumb">
          {project.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={project.thumbnail_url} alt="" />
          ) : (
            <span className="project-thumb-empty">{describeSource(project.source_url)}</span>
          )}
        </span>
        <div>
          <Link href="/my" className="back-link">
            ← 내 프로젝트
          </Link>
          <h2>{project.title}</h2>
          <p className="project-meta">
            <span className={`project-dot project-dot-${project.status}`}>{PROJECT_STATUS[project.status]}</span>
            {project.channel_title ? <span>{project.channel_title}</span> : null}
            {formatDuration(project.duration_seconds) ? <span>{formatDuration(project.duration_seconds)}</span> : null}
            <span>쇼츠 {project.shorts_count}개</span>
            <span>AI 분석 {project.analyses_count}회</span>
          </p>
          <Link className="submit-button project-new" href="/video">
            이 영상으로 쇼츠 더 만들기 →
          </Link>
        </div>
      </section>
      <section className="project-section" aria-labelledby="project-shorts-heading">
        <h3 id="project-shorts-heading">생성된 쇼츠 {shorts.length}개</h3>
        <WorkItems items={shorts} emptyText="아직 이 영상으로 만든 쇼츠가 없어요." />
      </section>
      <section className="project-section" aria-labelledby="project-analyses-heading">
        <h3 id="project-analyses-heading">AI 분석 {analyses.length}회</h3>
        <WorkItems items={analyses} emptyText="AI 추천 분석 기록이 없어요." />
      </section>
    </>
  );
}
