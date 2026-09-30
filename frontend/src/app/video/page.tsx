import { SiteNav } from "@/components/site-nav";
import { SourceInput } from "@/components/source-input";

const steps = [
  "YouTube URL 또는 영상 파일 업로드",
  "구간과 자막 템플릿 선택",
  "AI Score Top 3 중 하나 선택 (또는 이 구간 그대로)",
  "9:16 쇼츠 미리보기 · MP4 다운로드",
];

export default function VideoPage() {
  return (
    <main>
      <div className="page-shell">
        <section className="hero">
          <SiteNav current="video" />
          <p className="eyebrow">VIDEO TO SHORTS</p>
          <h1>영상에서 쇼츠 구간을 고르세요.</h1>
          <p className="intro">
            YouTube 영상이나 업로드한 파일에서 분석할 구간을 정하면 자막을 읽어 15~60초 후보를
            만들고 AI Score로 Top 3를 추천합니다. 하나를 고르면 자막 템플릿을 얹은 1080x1920
            쇼츠로 렌더링합니다.
          </p>

          <ol className="flow" aria-label="영상 쇼츠 흐름">
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
