"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, useSyncExternalStore, type ReactNode } from "react";
import { useAuthStatus } from "@/lib/auth-context";
import { CREDIT_RULES, creditCost, loginUrl, logout, summarizeCreditBudget } from "@/lib/auth";
import { LandingSourceForm } from "@/components/landing-source-form";
import styles from "./member-workspace.module.css";

function preferenceKey(id: string) { return `cutpick:${id}:start-source`; }
function subscribePreference(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener("cutpick-preference", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("cutpick-preference", callback);
  };
}
function useStartSource() {
  const { status } = useAuthStatus();
  const [notice, setNotice] = useState("");
  const source = useSyncExternalStore(subscribePreference, () => {
    if (!status.user) return "video";
    try {
      const saved = localStorage.getItem(preferenceKey(status.user.id));
      return saved === "affiliate" ? "affiliate" : "video";
    } catch { return "video"; }
  }, () => "video");
  function save(value: string) {
    if (!status.user) return;
    try {
      localStorage.setItem(preferenceKey(status.user.id), value);
      window.dispatchEvent(new Event("cutpick-preference"));
      setNotice("이 브라우저에 저장했습니다.");
    } catch { setNotice("설정을 저장하지 못했습니다. 브라우저 저장 공간을 확인해 주세요."); }
  }
  return { source, save, notice };
}

export function MemberWorkspace({ children }: { children: ReactNode }) {
  const [showUpgradeNotice, setShowUpgradeNotice] = useState(false);
  const pathname = usePathname();
  const params = useSearchParams();
  const { status, loading } = useAuthStatus();
  const creditBalance = typeof status.credits === "number" ? status.credits : null;
  const signupCredits = status.costs?.signup_grant;
  const creditLimit = typeof signupCredits === "number" && signupCredits > 0 ? signupCredits : null;
  const creditPercent = creditBalance !== null && creditLimit !== null ? Math.min(100, Math.max(0, creditBalance / creditLimit * 100)) : null;
  const settings = pathname === "/my/settings";
  const section = pathname?.startsWith("/my/video")
    ? "video"
    : pathname?.startsWith("/my/affiliate")
      ? "affiliate"
      : settings
        ? "settings"
        : "projects";
  const topbarTitle = { projects: "내 작업실", video: "영상 쇼츠 만들기", affiliate: "상품 쇼츠 만들기", settings: "계정 · 제작 설정" }[section];
  return <div className={styles.workspace}>
    <aside className={styles.sidebar}>
      <Link href="/my" className={styles.brand} aria-label="Cutpick 회원 작업실"><span className={styles.symbol} aria-hidden="true"><i /><i /></span>cutpick.</Link>
      <span className={styles.label}>MY WORKSPACE</span>
      <nav aria-label="회원 메뉴">
        <Link href="/my" aria-current={section === "projects" ? "page" : undefined}><span aria-hidden="true">▦</span> 내 프로젝트</Link>
        <Link href="/my/video" aria-current={section === "video" ? "page" : undefined}><span aria-hidden="true">▷</span> 영상 쇼츠 만들기</Link>
        <Link href="/my/affiliate" aria-current={section === "affiliate" ? "page" : undefined}><span aria-hidden="true">◇</span> 상품 쇼츠 만들기</Link>
      </nav>
      <div className={styles.sidebarBottom}>
        <section className={styles.balance} aria-label="내 플랜과 크레딧">
          <strong className={styles.planName}>무료 플랜</strong>
          <Link className={styles.creditRow} href="/my#credit-heading" title={summarizeCreditBudget(status) ?? "크레딧 사용 내역"}>
            <span>잔여 크레딧</span><span><strong>{loading ? "…" : creditBalance ?? "—"}</strong>{creditLimit !== null ? `/${creditLimit}` : ""} C</span>
          </Link>
          <div className={styles.creditTrack} role="progressbar" aria-label="가입 제공량 대비 잔여 크레딧" aria-valuemin={0} aria-valuemax={100} aria-valuenow={creditPercent ?? undefined} aria-valuetext={creditPercent === null ? "크레딧 확인 중" : `잔여 ${creditBalance} C, 가입 제공량 ${creditLimit} C`}><span style={{ width: `${creditPercent ?? 0}%` }} /></div>
          <button className={styles.upgradeButton} type="button" aria-expanded={showUpgradeNotice} aria-controls="upgrade-notice" onClick={() => setShowUpgradeNotice(!showUpgradeNotice)}><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m13 2-9 12h7l-1 8 10-12h-7l1-8Z" /></svg>업그레이드</button>
          {showUpgradeNotice ? <p id="upgrade-notice" role="status" className={styles.upgradeNotice}>유료 플랜은 준비 중입니다.</p> : null}
        </section>
        <Link className={styles.settingsLink} href="/my/settings" aria-current={settings ? "page" : undefined}>⚙ 설정</Link>
        <Link className={styles.homeLink} href="/">서비스 소개 ↗</Link>
      </div>
    </aside>
    <div className={styles.body}>
      <header className={styles.topbar}>
        <span>{topbarTitle}</span>
        <Link href="/my#credit-heading" className={styles.topbarCredits} title={summarizeCreditBudget(status) ?? "남은 크레딧"}><span aria-hidden="true">◎</span> 크레딧 <strong>{status.credits ?? "—"}</strong></Link>
        <Link href="/my/settings" aria-label="계정 설정">계정 설정</Link>
      </header>
      <main className={styles.content} id="main-content">
        {loading ? <p role="status">로그인 상태를 확인하는 중...</p> : !status.user ? <section className={styles.panel}>
          <h1>나만의 쇼츠 작업실</h1><p>로그인하고 프로젝트와 크레딧, 제작 설정을 관리하세요.</p>
          {params.get("login") === "failed" ? <p role="alert">로그인하지 못했습니다. 다시 시도해 주세요.</p> : null}
          {params.get("login") === "cancelled" ? <p role="status">로그인이 취소되었습니다.</p> : null}
          {status.login_available ? <a className={styles.primary} href={loginUrl(pathname ?? "/my")}>Google로 로그인</a> : <p>현재 로그인을 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.</p>}
        </section> : children}
      </main>
    </div>
  </div>;
}

export function MemberWelcome() {
  const { source } = useStartSource();
  return <section className={styles.welcome}>
    <span className={styles.label}>LET’S MAKE A SHORT</span><h1>오늘은 어떤 쇼츠를 만들까요?</h1>
    <p>영상이나 상품 링크로 시작하고, 완성한 쇼츠는 아래에서 다시 확인하세요.</p>
    <LandingSourceForm target="/my/video" />
    <div className={styles.quickLinks}><Link href="/my/video">YouTube · 영상 업로드 →</Link><Link href="/my/affiliate">상품 링크로 만들기 →</Link></div>
    <Link className={styles.preferred} href={`/my/${source}`}>내 기본 제작 방식으로 시작 →</Link>
  </section>;
}

/** Heading for a studio opened inside the workspace (/my/video, /my/affiliate). */
export function MemberStudio({ kind, children }: { kind: "video" | "affiliate"; children: ReactNode }) {
  const video = kind === "video";
  return <div className={styles.studio}>
    <div className={styles.studioHeading}>
      <span className={styles.label}>{video ? "VIDEO STUDIO" : "AFFILIATE STUDIO"}</span>
      <h1>{video ? "영상 쇼츠 만들기" : "상품 쇼츠 만들기"}</h1>
      <p>{video ? "YouTube 링크나 내 영상 파일에서 구간을 고르고, AI 추천 Top 3로 세로 쇼츠를 만드세요." : "쿠팡 파트너스 상품 링크에서 콘텐츠 앵글을 고르고, 내레이션이 들어간 상품 쇼츠를 만드세요."}</p>
      <span className={styles.studioFormat}>9:16 · MP4</span>
    </div>
    {children}
  </div>;
}

export function MemberSettings() {
  const { status, setStatus } = useAuthStatus();
  const { source, save, notice } = useStartSource();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();
  if (!status.user) return null;
  async function signOut() {
    setBusy(true); setError("");
    try {
      await logout(); setStatus({ ...status, user: null, credits: null });
      router.replace("/"); router.refresh();
    } catch (failure) { setError(failure instanceof Error ? failure.message : "다시 시도해 주세요."); setBusy(false); }
  }
  const prices = [
    ["AI 구간 분석", creditCost(status, "analysis_per_minute"), " / 원본 1분"],
    ["직접 지정 쇼츠", creditCost(status, "manual_short_per_minute"), " / 클립 1분"],
    ["추천 구간 렌더", creditCost(status, "candidate_render"), " / 편"],
    ["상품 쇼츠", creditCost(status, "product_short"), " / 편"],
  ] as const;
  return <div className={styles.settings}>
    <div><span className={styles.label}>YOUR WORKSPACE</span><h1>계정 · 제작 설정</h1><p>연결된 계정과 크레딧을 확인하고, 자주 쓰는 제작 방식을 설정하세요.</p></div>
    <section className={styles.panel}><h2>내 계정</h2><dl className={styles.info}><div><dt>로그인 방식</dt><dd>Google 계정</dd></div><div><dt>이메일</dt><dd>{status.user.email ?? "등록된 이메일 없음"}</dd></div></dl><p>계정 정보는 Google 로그인 정보를 기준으로 표시됩니다.</p></section>
    <section className={styles.panel}><h2>제작 시작 설정</h2><label htmlFor="default-source">기본 제작 방식</label><select id="default-source" value={source} onChange={event => save(event.target.value)}><option value="video">영상 쇼츠 (YouTube · 업로드)</option><option value="affiliate">상품 쇼츠 (어필리에이트)</option></select><p>작업실의 ‘내 기본 제작 방식으로 시작’에 적용됩니다. 이 브라우저에 계정별로 저장됩니다.</p><p role="status">{notice}</p></section>
    <section className={styles.panel} id="credit-rules"><h2>크레딧</h2><strong className={styles.creditNumber} title={summarizeCreditBudget(status) ?? undefined}>{status.credits ?? "—"} C</strong><dl className={styles.info}>{prices.map(([label, cost, unit]) => <div key={label}><dt>{label}</dt><dd>{cost === null ? "확인 중" : cost === 0 ? "무료" : `${cost} C${unit}`}</dd></div>)}</dl><h3 className={styles.subheading}>차감 기준</h3><ul className={styles.rules}>{CREDIT_RULES.map(rule => <li key={rule}>{rule}</li>)}</ul><Link href="/my#credit-heading">크레딧 사용 내역 보기 →</Link></section>
    <section className={styles.panel}><h2>계정 관리</h2><div className={styles.accountAction}><div><strong>로그아웃</strong><p>이 기기의 로그인 세션을 종료합니다.</p></div><button onClick={signOut} disabled={busy}>{busy ? "처리 중..." : "Logout"}</button></div>{error ? <p role="alert">{error}</p> : null}</section>
  </div>;
}
