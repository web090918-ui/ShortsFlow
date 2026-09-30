import { SourceInput } from "@/components/source-input";

const steps = [
  "YouTube URL, 파일 업로드 또는 쿠팡 파트너스 링크",
  "구간과 자막 템플릿 선택",
  "AI Score Top 3 (또는 상품 앵글 3개) 중 하나 선택",
  "9:16 쇼츠 미리보기 · MP4 다운로드",
];

export default function Home() {
  return (
    <main>
      <div className="page-shell">
        <section className="hero">
          <p className="eyebrow">SHORTSFLOW</p>
          <h1>하나의 Source에서 Shorts를 시작하세요.</h1>
          <p className="intro">
            YouTube 영상이나 업로드한 파일에서 구간을 고르면 AI Score로 추천한 Top 3 중 하나를
            자막 템플릿을 얹은 1080x1920 쇼츠로 만들어 드립니다. 원하는 구간이 이미 정해져
            있다면 그 구간 그대로 만들 수도 있고, 쿠팡 파트너스 링크는 상품 쇼츠로 이어집니다.
          </p>

          <ol className="flow" aria-label="ShortsFlow 기본 흐름">
            {steps.map((step, index) => (
              <li key={step}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                {step}
              </li>
            ))}
          </ol>
        </section>

        <div className="panel-stack">
          <SourceInput />
        </div>
      </div>
    </main>
  );
}
