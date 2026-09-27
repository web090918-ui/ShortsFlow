import { SourceInput } from "@/components/source-input";

const steps = ["Source Input", "Shorts Candidate", "Top 3", "Render"];

export default function Home() {
  return (
    <main>
      <div className="page-shell">
        <section className="hero">
          <p className="eyebrow">SHORTSFLOW</p>
          <h1>하나의 Source에서 Shorts를 시작하세요.</h1>
          <p className="intro">
            YouTube 영상, 상품 URL 또는 영상 파일을 입력하면 공통 Source로 등록합니다.
            아직 영상 분석이나 AI 처리는 시작하지 않습니다.
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

        <SourceInput />
      </div>
    </main>
  );
}

