import { ShortsCreator } from "@/components/shorts-creator";
import { SourceInput } from "@/components/source-input";

const steps = [
  "YouTube URL",
  "직접 구간 지정 또는 AI 추천 Top 3",
  "자막 템플릿으로 9:16 렌더",
  "미리보기 · MP4 다운로드",
];

export default function Home() {
  return (
    <main>
      <div className="page-shell">
        <section className="hero">
          <p className="eyebrow">SHORTSFLOW</p>
          <h1>하나의 Source에서 Shorts를 시작하세요.</h1>
          <p className="intro">
            YouTube URL을 입력하고 원하는 구간을 직접 지정하거나, 자막을 분석해 AI Score로
            추천한 Top 3 중 하나를 고르세요. 선택한 구간은 자막 템플릿을 얹은 1080x1920 세로
            쇼츠 MP4로 렌더링되어 바로 미리보고 다운로드할 수 있습니다.
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
          <ShortsCreator />
          <SourceInput />
        </div>
      </div>
    </main>
  );
}
