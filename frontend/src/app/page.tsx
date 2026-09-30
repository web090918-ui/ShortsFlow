import Link from "next/link";

import { SiteNav } from "@/components/site-nav";

const howItWorks = [
  {
    title: "소스 하나만 주세요",
    body: "YouTube 링크, 내 영상 파일, 또는 쿠팡 파트너스 상품 링크. 어디서 시작하든 결과는 같은 9:16 쇼츠입니다.",
  },
  {
    title: "AI가 고르고, 내가 결정합니다",
    body: "자막을 분석해 15~60초 후보를 만들고 AI Score로 Top 3를 추천합니다. 상품 링크는 셀링 포인트와 앵글 3개를 제안합니다. 최종 선택은 항상 사용자에게 있습니다.",
  },
  {
    title: "자막까지 얹어 바로 다운로드",
    body: "선택한 구간을 1080x1920으로 잘라 자막 템플릿을 얹고, 미리보기 후 MP4로 내려받습니다. 상품 쇼츠는 내레이션과 가격 카드가 자동으로 들어갑니다.",
  },
];

export default function Home() {
  return (
    <main className="landing">
      <div className="landing-shell">
        <SiteNav current="home" />

        <section className="landing-hero">
          <p className="eyebrow">SHORTSFLOW</p>
          <h1>하나의 Source에서 Shorts를 시작하세요.</h1>
          <p className="intro">
            긴 영상에서 어떤 구간을 쇼츠로 만들지 고민하는 시간, 상품 링크 하나로 홍보 영상을
            만드는 수고를 줄입니다. ShortsFlow는 소스를 받아 후보를 추천하고, 선택한 구간을
            세로 쇼츠로 렌더링해 다운로드까지 이어 주는 크리에이터용 도구입니다.
          </p>
        </section>

        <section className="entry-cards" aria-label="시작하기">
          <Link href="/video" className="entry-card">
            <p className="section-label">VIDEO</p>
            <h2>영상으로 만들기</h2>
            <p>
              YouTube URL 또는 영상 파일 → 구간 선택 → AI Score Top 3 → 자막 템플릿 렌더 →
              다운로드. 원하는 구간이 정해져 있으면 그 구간 그대로 만들 수도 있습니다.
            </p>
            <span className="entry-cta">영상으로 시작 →</span>
          </Link>
          <Link href="/affiliate" className="entry-card">
            <p className="section-label">AFFILIATE</p>
            <h2>상품·여행 링크로 만들기</h2>
            <p>
              쿠팡 파트너스 링크 → 상품 정보 확인 → 콘텐츠 앵글 3개 → 내레이션·가격 카드·고지
              문구가 들어간 상품 쇼츠. 아고다와 트립닷컴은 준비 중입니다.
            </p>
            <span className="entry-cta">링크로 시작 →</span>
          </Link>
        </section>

        <section className="how-it-works" aria-labelledby="how-heading">
          <h2 id="how-heading">어떻게 동작하나요</h2>
          <ol>
            {howItWorks.map((item, index) => (
              <li key={item.title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-notes" aria-label="이용 안내">
          <div>
            <h3>지원 소스</h3>
            <p>YouTube 공개 영상, MP4·MOV·MKV 등 영상 파일, 쿠팡 파트너스 링크. 아고다·트립닷컴 예정.</p>
          </div>
          <div>
            <h3>권리와 고지</h3>
            <p>
              영상은 본인이 소유했거나 이용 허가를 받은 것만 처리합니다. 상품 쇼츠에는 쿠팡 파트너스
              활동 고지 문구가 자동으로 들어갑니다.
            </p>
          </div>
          <div>
            <h3>출력</h3>
            <p>1080x1920 MP4, 자막 템플릿 3종(Clean Caption, Bold Highlight, Minimal), 다운로드 링크는 24시간 유효.</p>
          </div>
        </section>
      </div>
    </main>
  );
}
