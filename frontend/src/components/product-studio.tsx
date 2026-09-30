"use client";

import { useEffect, useState } from "react";

import { API_URL } from "@/config";
import { RenderResult } from "@/components/render-result";
import type { RenderJob } from "@/components/render-result";

type TemplateId = "CLEAN_CAPTION" | "BOLD_HIGHLIGHT" | "MINIMAL";

export type ProductFacts = {
  provider: string;
  product_id: string;
  title: string;
  origin_price: number | null;
  sales_price: number | null;
  discount_rate: number | null;
  image_url: string;
  product_url: string;
  facts: string[];
};

export type ContentAngle = {
  id: string;
  name: string;
  summary: string;
  hook: string;
  script: string[];
  cta: string;
};

export type ProductContent = {
  generator: string;
  selling_points: string[];
  angles: ContentAngle[];
  disclosure: string;
};

type Props = {
  sourceId: string;
  product: ProductFacts;
  content: ProductContent | null;
  onContent: (content: ProductContent) => void;
};

const POLL_INTERVAL_MS = 1500;
const TEMPLATES: Array<{ id: TemplateId; name: string }> = [
  { id: "CLEAN_CAPTION", name: "Clean Caption" },
  { id: "BOLD_HIGHLIGHT", name: "Bold Highlight" },
  { id: "MINIMAL", name: "Minimal" },
];

async function readJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail ?? "요청을 처리하지 못했습니다.");
  }
  return payload as T;
}

function won(value: number | null) {
  return value === null ? null : `${value.toLocaleString("ko-KR")}원`;
}

export function ProductStudio({ sourceId, product, content, onContent }: Props) {
  const [notes, setNotes] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedAngleId, setSelectedAngleId] = useState<string | null>(null);
  const [templateId, setTemplateId] = useState<TemplateId>("BOLD_HIGHLIGHT");
  const [ctaUrl, setCtaUrl] = useState("");
  const [termsConfirmed, setTermsConfirmed] = useState(false);
  const [renderJob, setRenderJob] = useState<RenderJob | null>(null);
  const [isStartingRender, setIsStartingRender] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedAngle = content?.angles.find((angle) => angle.id === selectedAngleId) ?? null;
  const renderActive =
    renderJob !== null && renderJob.status !== "completed" && renderJob.status !== "failed";

  useEffect(() => {
    if (!renderJob || renderJob.status === "completed" || renderJob.status === "failed") return;
    const job = renderJob;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_URL}/shorts/${job.id}`, { signal: controller.signal });
        setRenderJob(await readJsonResponse<RenderJob>(response));
      } catch (pollError) {
        if (controller.signal.aborted) return;
        const message =
          pollError instanceof Error ? pollError.message : "렌더 상태를 확인하지 못했습니다.";
        setRenderJob((current) =>
          current
            ? { ...current, status: "failed", artifact_state: "failed", error_message: message }
            : current,
        );
      }
    }, POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [renderJob]);

  async function generateContent(refresh: boolean) {
    setError(null);
    setIsGenerating(true);
    try {
      const response = await fetch(`${API_URL}/sources/${sourceId}/product-content`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes.trim() || null, refresh }),
      });
      const source = await readJsonResponse<{ metadata: { product_content?: ProductContent } }>(
        response,
      );
      if (source.metadata.product_content) {
        onContent(source.metadata.product_content);
        setSelectedAngleId(source.metadata.product_content.angles[0]?.id ?? null);
      }
    } catch (generateError) {
      setError(
        generateError instanceof Error ? generateError.message : "콘텐츠 앵글을 만들지 못했습니다.",
      );
    } finally {
      setIsGenerating(false);
    }
  }

  async function startRender() {
    if (!selectedAngle || !termsConfirmed) return;
    setError(null);
    setRenderJob(null);
    setIsStartingRender(true);
    try {
      const response = await fetch(`${API_URL}/shorts/product`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: sourceId,
          angle_id: selectedAngle.id,
          template_id: templateId,
          cta_url: ctaUrl.trim() || null,
          terms_confirmed: true,
        }),
      });
      setRenderJob(await readJsonResponse<RenderJob>(response));
    } catch (renderError) {
      setError(
        renderError instanceof Error ? renderError.message : "상품 쇼츠 렌더를 시작하지 못했습니다.",
      );
    } finally {
      setIsStartingRender(false);
    }
  }

  return (
    <section className="range-picker product-studio" aria-labelledby="product-heading">
      <div className="product-card">
        {/* Coupang CDN host varies per product; a plain image keeps it simple. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={product.image_url} alt="" />
        <div>
          <h3 id="product-heading">{product.title}</h3>
          <p className="product-price">
            {product.discount_rate ? <span className="ai-score">{product.discount_rate}% 할인</span> : null}
            <strong>{won(product.sales_price) ?? "가격 정보 없음"}</strong>
            {product.origin_price && product.sales_price && product.origin_price > product.sales_price ? (
              <s>{won(product.origin_price)}</s>
            ) : null}
          </p>
          {product.facts.length > 0 ? (
            <ul className="candidate-tags">
              {product.facts.map((fact) => (
                <li key={fact}>{fact}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>

      <label className="field">
        <span>크리에이터 메모 (선택)</span>
        <input
          type="text"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="예: 캠핑 갈 때 챙기는 음료로 소개"
          aria-label="크리에이터 메모"
        />
      </label>

      <button
        type="button"
        className="submit-button"
        onClick={() => generateContent(Boolean(content))}
        disabled={isGenerating}
      >
        {isGenerating ? "앵글 만드는 중..." : content ? "앵글 다시 만들기" : "콘텐츠 앵글 만들기"}
      </button>

      {error ? (
        <p className="message error-message" role="alert">
          {error}
        </p>
      ) : null}

      {content ? (
        <>
          <section className="candidate-list" aria-labelledby="angles-heading">
            <h3 id="angles-heading">콘텐츠 앵글 3개</h3>
            {content.selling_points.length > 0 ? (
              <ul className="candidate-tags">
                {content.selling_points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            ) : null}
            {content.angles.map((angle) => {
              const isSelected = angle.id === selectedAngleId;
              return (
                <article
                  key={angle.id}
                  className={isSelected ? "candidate-card selected" : "candidate-card"}
                >
                  <header>
                    <span className="candidate-rank">{angle.name}</span>
                    <span className="candidate-time">{angle.script.length + 2}문장</span>
                  </header>
                  <p className="candidate-hook">“{angle.hook}”</p>
                  <p className="candidate-reason">{angle.summary}</p>
                  <ol className="angle-script">
                    {angle.script.map((line, index) => (
                      <li key={`${angle.id}-${index}`}>{line}</li>
                    ))}
                    <li className="angle-cta">{angle.cta}</li>
                  </ol>
                  <button
                    type="button"
                    className={isSelected ? "submit-button" : "submit-button secondary-button"}
                    aria-pressed={isSelected}
                    onClick={() => setSelectedAngleId(angle.id)}
                  >
                    {isSelected ? "선택됨" : "이 앵글 선택"}
                  </button>
                </article>
              );
            })}
          </section>

          <fieldset className="template-picker">
            <legend>자막 템플릿</legend>
            <div className="template-options">
              {TEMPLATES.map((template) => (
                <button
                  key={template.id}
                  type="button"
                  className="template-card"
                  aria-pressed={templateId === template.id}
                  onClick={() => setTemplateId(template.id)}
                >
                  <strong>{template.name}</strong>
                </button>
              ))}
            </div>
          </fieldset>

          <label className="field">
            <span>파트너스 단축 링크 (선택, 예: https://link.coupang.com/a/...)</span>
            <input
              type="url"
              value={ctaUrl}
              onChange={(event) => setCtaUrl(event.target.value)}
              placeholder="https://link.coupang.com/a/"
              aria-label="파트너스 단축 링크"
            />
          </label>

          <label className="rights-confirmation">
            <input
              type="checkbox"
              checked={termsConfirmed}
              onChange={(event) => setTermsConfirmed(event.target.checked)}
            />
            <span>
              <strong>쿠팡 파트너스 약관 확인</strong>
              <small>
                쿠팡 파트너스 회원으로서 제공된 상품 정보와 이미지를 약관 범위 안에서 사용하며,
                영상에 파트너스 활동 고지 문구가 포함되는 것에 동의합니다.
              </small>
            </span>
          </label>

          <button
            type="button"
            className="submit-button"
            onClick={startRender}
            disabled={!selectedAngle || !termsConfirmed || isStartingRender || renderActive}
          >
            {isStartingRender ? "작업 등록 중..." : renderActive ? "렌더링 중..." : "상품 쇼츠 만들기"}
          </button>

          {renderJob ? (
            <RenderResult job={renderJob} onRetry={startRender} retryDisabled={isStartingRender} />
          ) : null}
        </>
      ) : null}
    </section>
  );
}
