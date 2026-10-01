"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { API_URL } from "@/config";
import { RenderResult } from "@/components/render-result";
import type { RenderJob } from "@/components/render-result";
import { formatTimecode } from "@/lib/timecode";
import { loginUrl, useAuthStatus } from "@/lib/auth";

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

type WorkItem =
  | { kind: "short"; created_at: string; short: RenderJob & { youtube_url: string } }
  | { kind: "analysis"; created_at: string; analysis: AnalysisSummary };

function formatDate(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
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

const ANALYSIS_LABELS: Record<AnalysisSummary["status"], string> = {
  QUEUED: "대기 중",
  PROCESSING: "분석 중",
  COMPLETED: "분석 완료",
  FAILED: "분석 실패",
};

export function MyWorks() {
  const router = useRouter();
  const { status, loading } = useAuthStatus();
  const [items, setItems] = useState<WorkItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading || !status.user) return;
    let cancelled = false;
    fetch(`${API_URL}/me/jobs`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error("작업 목록을 불러오지 못했습니다.");
        const payload = (await response.json()) as { items: WorkItem[] };
        if (!cancelled) setItems(payload.items);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "작업 목록을 불러오지 못했습니다.");
      });
    return () => {
      cancelled = true;
    };
  }, [loading, status.user]);

  if (loading) {
    return <section className="source-panel" aria-busy="true"><p className="range-help">불러오는 중...</p></section>;
  }
  if (!status.user) {
    return (
      <section className="source-panel login-gate">
        <h2>내 작업을 보려면 로그인하세요</h2>
        <a className="submit-button auth-login-button" href={loginUrl("/my")}>Google로 로그인</a>
      </section>
    );
  }
  if (error) {
    return <section className="source-panel"><p className="message error-message" role="alert">{error}</p></section>;
  }
  if (items === null) {
    return <section className="source-panel" aria-busy="true"><p className="range-help">작업 목록을 불러오는 중...</p></section>;
  }
  if (items.length === 0) {
    return (
      <section className="source-panel">
        <h2>아직 만든 작업이 없습니다</h2>
        <p className="range-help">영상이나 상품 링크로 첫 쇼츠를 만들어 보세요.</p>
        <div className="my-works-actions">
          <Link className="submit-button" href="/video">영상으로 만들기</Link>
          <Link className="submit-button secondary-button" href="/affiliate">상품 링크로 만들기</Link>
        </div>
      </section>
    );
  }

  return (
    <section className="my-works" aria-label="내 작업 목록">
      {items.map((item) =>
        item.kind === "short" ? (
          <article key={item.short.id} className="work-card">
            <header>
              <span className="work-kind">쇼츠</span>
              <span className="work-source">{describeSource(item.short.youtube_url)}</span>
              <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
            </header>
            <RenderResult job={item.short} onRetry={() => router.push("/video")} />
          </article>
        ) : (
          <article key={item.analysis.id} className="work-card">
            <header>
              <span className="work-kind">분석</span>
              <span className="work-source">{describeSource(item.analysis.source_url)}</span>
              <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
            </header>
            <div className="download-status">
              <div>
                <span>{ANALYSIS_LABELS[item.analysis.status]}</span>
                <strong>{item.analysis.progress}%</strong>
              </div>
              <p className="shorts-status-range">
                {formatTimecode(item.analysis.start_seconds)} – {formatTimecode(item.analysis.end_seconds)} ·{" "}
                후보 {item.analysis.candidate_count}개
              </p>
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
