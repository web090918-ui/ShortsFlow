import Link from "next/link";
import { SiteNav } from "@/components/site-nav";
import { ShortPreview } from "@/components/short-preview";

const steps = [
  { title: "링크 하나, 또는 내 영상", body: "YouTube 영상과 내 파일, 쿠팡 파트너스 상품 링크 중 원하는 소스로 시작하세요.", detail: "01 / IMPORT" },
  { title: "AI가 추천하고, 내가 선택", body: "영상의 추천 구간 Top 3 또는 상품의 콘텐츠 앵글을 확인하고 마음에 드는 것을 고르세요.", detail: "02 / PICK" },
  { title: "세로 쇼츠로 완성", body: "스타일을 정하고 완성된 쇼츠를 확인하세요. 미리보기부터 MP4 다운로드까지 한곳에서.", detail: "03 / EXPORT" },
];

export default function Home() {
  return (
    <>
      <SiteNav current="home" />
      <main className="landing" id="main-content">
        <div className="landing-shell">
          <section className="landing-hero">
            <div className="hero-copy">
              <p className="eyebrow"><span className="status-dot" /> YOUR NEXT SHORT STARTS HERE</p>
              <h1>좋은 순간을 골라,<br /><span>쇼츠로 완성.</span></h1>
              <p className="intro">긴 영상도, 상품 링크도.<br />AI의 추천에 내 선택을 더해 세로 쇼츠로 만드세요.</p>
              <div className="hero-actions"><a className="primary-link" href="#start">내 쇼츠 만들기 <span aria-hidden="true">↗</span></a><a className="text-link" href="#how-it-works">어떻게 만드나요 <span aria-hidden="true">↓</span></a></div>
              <div className="hero-facts"><span>AI 추천 구간</span><span>자막 스타일 3종</span><span>MP4 다운로드</span></div>
            </div>
            <div className="hero-showcase" aria-label="영상과 상품 쇼츠의 디자인 예시. 실제 생성 결과와 다를 수 있습니다.">
              <div className="showcase-grid" />
              <div className="showcase-label"><span className="status-dot" /> FROM SOURCE TO SHORT</div>
              <div className="showcase-video"><ShortPreview /></div>
              <div className="showcase-product"><ShortPreview variant="product" /></div>
              <div className="showcase-note"><span aria-hidden="true">✦</span><div><strong>가능성을 고르는 건 AI,<br />마지막 선택은 나.</strong><small>화면 구성 예시 · 실제 결과와 다를 수 있어요</small></div></div>
            </div>
          </section>
          <section className="start-section" id="start" aria-labelledby="start-heading">
            <div className="section-heading"><div><p className="eyebrow">MAKE YOUR PICK</p><h2 id="start-heading">무엇으로 시작할까요?</h2></div><p>소스에 맞는 작업 공간으로 바로 시작하세요.</p></div>
            <div className="entry-cards">
              <Link href="/video" className="entry-card video-entry">
                <div className="entry-top"><span className="entry-icon" aria-hidden="true">▷</span><span className="entry-number">01 / VIDEO</span></div>
                <h3>영상에서 쇼츠로</h3><p>긴 영상 속 놓치기 아까운 장면.<br />AI 추천으로 찾거나 직접 구간을 골라보세요.</p>
                <div className="source-chips"><span>YouTube</span><span>영상 업로드</span></div>
                <div className="entry-cta">영상으로 시작하기 <span aria-hidden="true">↗</span></div>
              </Link>
              <Link href="/affiliate" className="entry-card affiliate-entry">
                <div className="entry-top"><span className="entry-icon" aria-hidden="true">↗</span><span className="entry-number">02 / AFFILIATE</span></div>
                <h3>상품 링크에서 쇼츠로</h3><p>소개하고 싶은 상품의 매력을 짧게.<br />콘텐츠 앵글부터 내레이션까지 한 흐름으로.</p>
                <div className="source-chips"><span>쿠팡 파트너스</span><span className="planned-chip">여행 링크 · 준비 중</span></div>
                <div className="entry-cta">상품 링크로 시작하기 <span aria-hidden="true">↗</span></div>
              </Link>
            </div>
          </section>
          <section className="how-it-works" id="how-it-works" aria-labelledby="how-heading">
            <div className="section-heading"><div><p className="eyebrow">LESS EDITING. MORE CREATING.</p><h2 id="how-heading">복잡한 편집 대신, 세 번의 선택.</h2></div><span className="section-aside">소스 → 선택 → 완성</span></div>
            <ol>{steps.map((step) => <li key={step.detail}><span>{step.detail}</span><h3>{step.title}</h3><p>{step.body}</p></li>)}</ol>
          </section>
          <section className="sources-section" aria-labelledby="sources-heading">
            <div><p className="eyebrow">YOUR SOURCE, YOUR STORY</p><h2 id="sources-heading">시작은 다양하게.<br />결과는 하나의 쇼츠로.</h2><p>이용 권한이 있는 영상과 상품 정보로 시작하세요.</p></div>
            <ul className="source-directory">
              <li><span className="source-letter youtube-letter" aria-hidden="true">▶</span><div><strong>YouTube</strong><small>공개 영상 링크</small></div><span className="availability">지원</span></li>
              <li><span className="source-letter" aria-hidden="true">↑</span><div><strong>내 영상 파일</strong><small>MP4 · MOV · MKV 등</small></div><span className="availability">지원</span></li>
              <li><span className="source-letter coupang-letter" aria-hidden="true">C</span><div><strong>쿠팡 파트너스</strong><small>상품 링크로 시작</small></div><span className="availability">지원</span></li>
              <li className="planned-source"><span className="source-letter" aria-hidden="true">↗</span><div><strong>아고다 · 트립닷컴</strong><small>여행 어필리에이트 링크</small></div><span className="availability planned">준비 중</span></li>
            </ul>
          </section>
          <footer className="site-footer"><Link href="/" className="footer-brand">cutpick.</Link><p>좋은 소스에서, 나다운 쇼츠로.</p><span>영상 이용 권한을 확인해 주세요.<br />상품 쇼츠에는 파트너스 활동 고지가 포함됩니다.</span></footer>
        </div>
      </main>
    </>
  );
}
