import { API_URL } from "@/config";

const steps = ["URL 또는 영상 업로드", "Shorts Candidate", "Top 3", "Render"];

export default function Home() {
  return (
    <main>
      <section className="hero">
        <p className="eyebrow">SHORTSFLOW</p>
        <h1>만들기 전에, 무엇을 만들지 결정하세요.</h1>
        <p className="intro">
          영상에서 Shorts 후보를 찾고 순위를 매겨 가장 가능성 높은 세 가지를 선택하는
          워크플로입니다.
        </p>

        <ol className="flow" aria-label="ShortsFlow 기본 흐름">
          {steps.map((step, index) => (
            <li key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              {step}
            </li>
          ))}
        </ol>

        <p className="status">
          API <code>{API_URL}</code>
        </p>
      </section>
    </main>
  );
}

