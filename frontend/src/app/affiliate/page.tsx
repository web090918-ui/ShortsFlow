import { AffiliateInput } from "@/components/affiliate-input";
import { SiteNav } from "@/components/site-nav";

const steps = [
  "쿠팡 파트너스 링크 붙이기",
  "상품 정보 확인 · 콘텐츠 앵글 3개 중 선택",
  "자막 템플릿 · CTA 링크 · 파트너스 고지 동의",
  "내레이션이 들어간 상품 쇼츠 미리보기 · 다운로드",
];

export default function AffiliatePage() {
  return (
    <main>
      <div className="page-shell">
        <section className="hero">
          <SiteNav current="affiliate" />
          <p className="eyebrow">AFFILIATE TO SHORTS</p>
          <h1>상품 링크 하나로 홍보 쇼츠를 만드세요.</h1>
          <p className="intro">
            쿠팡 파트너스 링크에서 상품명·가격·할인율·이미지를 읽고, AI가 셀링 포인트와 앵글
            3개를 제안합니다. 고른 앵글은 내레이션과 가격 카드, 파트너스 고지 문구가 들어간
            1080x1920 쇼츠로 합성됩니다. 아고다·트립닷컴은 준비 중입니다.
          </p>

          <ol className="flow" aria-label="상품 쇼츠 흐름">
            {steps.map((step, index) => (
              <li key={step}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                {step}
              </li>
            ))}
          </ol>
        </section>

        <div className="panel-stack">
          <AffiliateInput />
        </div>
      </div>
    </main>
  );
}
