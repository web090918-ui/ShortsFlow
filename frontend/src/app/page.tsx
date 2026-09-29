import { ShortsCreator } from "@/components/shorts-creator";
import { SourceInput } from "@/components/source-input";

const steps = ["YouTube URL", "Start / End 입력", "Shorts 생성", "9:16 MP4 다운로드"];

export default function Home() {
  return (
    <main>
      <div className="page-shell">
        <section className="hero">
          <p className="eyebrow">SHORTSFLOW</p>
          <h1>하나의 Source에서 Shorts를 시작하세요.</h1>
          <p className="intro">
            YouTube URL과 원하는 시작·끝 시간을 입력하면 해당 구간만 잘라 1080x1920 세로
            쇼츠 MP4로 만들어 드립니다. 구간은 사용자가 직접 정하며, AI 하이라이트 추천은
            다음 단계에서 이어집니다.
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
          <details className="secondary-panel">
            <summary>Source 분석 도구 (480p 분석 구간 준비)</summary>
            <SourceInput />
          </details>
        </div>
      </div>
    </main>
  );
}
