import Link from "next/link";
import { AuthMenu } from "@/components/auth-menu";
import { LandingSourceForm } from "@/components/landing-source-form";
import { ShortPreview } from "@/components/short-preview";
import styles from "./home.module.css";

const audiences = [
  { title: "크리에이터", body: "라이브와 긴 영상에서 다시 보고 싶은 장면을. AI 추천 Top 3를 확인하고 나만의 쇼츠로 만드세요.", href: "/video", action: "영상으로 시작하기" },
  { title: "쇼핑몰", body: "소개하고 싶은 상품의 매력을 짧게. 쿠팡 파트너스 링크에서 콘텐츠 앵글과 내레이션을 준비하세요.", href: "/affiliate", action: "상품 링크로 시작하기" },
  { title: "교육", body: "긴 강의에서 꼭 전달할 개념만 골라보세요. 원하는 구간을 직접 정해 짧은 학습 콘텐츠로 만드세요.", href: "/video", action: "강의 영상 가져오기" },
  { title: "기업", body: "웨비나와 인터뷰를 브랜드의 이야기로. 제목·자막 스타일을 고르고 세로 영상으로 내려받으세요.", href: "/video", action: "브랜드 영상 가져오기" },
];

export default function Home() {
  return (
    <div className={styles.home}>
      <div className={styles.shell}>
        <header className={styles.header}>
          <a className={styles.skip} href="#main-content">본문으로 이동</a>
          <Link href="/" className={styles.logo} aria-label="Cutpick 홈"><span className={styles.logoSymbol} aria-hidden="true"><i /><i /></span>cutpick.</Link>
          <nav aria-label="주요 메뉴"><Link href="/video">영상 쇼츠</Link><Link href="/affiliate">상품 쇼츠</Link><a href="#use-cases">활용 방법</a><a href="#how-it-works">만드는 과정</a></nav>
          <AuthMenu />
        </header>
        <main className={styles.main} id="main-content">
          <section className={styles.hero} aria-labelledby="hero-title">
            <div className={styles.copy}>
              <h1 id="hero-title">붙이기.<br />고르기.<br />끝.</h1>
              <p className={styles.lead}>링크 하나로 시작해,<br />AI 추천에서 나만의 쇼츠를 고르세요.</p>
              <div id="start"><LandingSourceForm /></div>
              <div className={styles.quickLinks}><Link href="/video">내 영상 업로드 →</Link><Link href="/affiliate">상품 링크로 만들기 →</Link></div>
            </div>
            <div className={styles.examples} aria-label="쇼츠 디자인 예시. 실제 생성 결과가 아닙니다.">
              <div className={styles.filmstrip}>
                {["핵심 장면", "상품 소개", "나만의 이야기"].map((label, index) => <div className={styles.sample} key={label}><span className={styles.sampleLabel}>0{index + 1} / {label}</span><ShortPreview variant={index === 1 ? "product" : "video"} /></div>)}
              </div>
              <div className={styles.exampleCaption}><span>하나의 소스 → 새로운 쇼츠</span><span>디자인 예시</span></div>
            </div>
          </section>
          <section className={styles.audiences} id="use-cases" aria-label="이런 콘텐츠에 활용하세요">
            {audiences.map((item, index) => <article key={item.title}><span className={styles.index}>0{index + 1}</span><h2>{item.title}</h2><p>{item.body}</p><Link href={item.href}>{item.action} →</Link></article>)}
          </section>
          <section className={styles.facts} aria-label="컷픽의 제작 방식">
            <div><strong>Top 3</strong><span>AI가 추천한 구간에서 직접 선택</span></div>
            <div><strong>9:16</strong><span>쇼츠에 맞춘 세로 영상</span></div>
            <div><strong>MP4</strong><span>완성된 영상 미리보기와 다운로드</span></div>
          </section>
          <section className={styles.details} id="how-it-works" aria-labelledby="how-title">
            <div><span className={styles.kicker}>FROM SOURCE TO SHORT</span><h2 id="how-title">복잡한 편집 대신,<br />세 번의 선택.</h2><ol><li>영상이나 상품 링크를 가져오세요.</li><li>추천 구간 또는 콘텐츠 앵글을 고르세요.</li><li>스타일을 정하고 MP4로 내려받으세요.</li></ol></div>
            <dl className={styles.info}>
              <div><dt>지원 소스</dt><dd>YouTube 링크, 내 영상 파일, 쿠팡 파트너스 상품 링크로 시작할 수 있습니다. 아고다·트립닷컴은 준비 중입니다.</dd></div>
              <div><dt>원본 권한</dt><dd>직접 소유하거나 편집·이용 허가를 받은 영상으로 제작하세요. 영상 생성 전에 원본 이용 권한을 확인합니다.</dd></div>
              <div><dt>크레딧</dt><dd>선택한 영상 구간에 따라 분석 크레딧이 계산됩니다. 제작 화면에서 예상 사용량을 확인한 뒤 진행하세요.</dd></div>
            </dl>
          </section>
          <section className={styles.cta} aria-labelledby="cta-title"><h2 id="cta-title">지금 붙이고,<br />나만의 쇼츠로.</h2><div><a href="#start">첫 쇼츠 시작하기 <span aria-hidden="true">→</span></a><p>YouTube · 영상 업로드 · 상품 링크</p></div></section>
        </main>
        <footer className={styles.footer}><span>© cutpick. 좋은 소스에서, 나다운 쇼츠로.</span><nav aria-label="하단 메뉴"><Link href="/video">영상 쇼츠</Link><Link href="/affiliate">상품 쇼츠</Link><Link href="/my">내 프로젝트</Link></nav></footer>
      </div>
    </div>
  );
}
