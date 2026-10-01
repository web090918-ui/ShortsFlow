"use client";

import { useEffect, useState } from "react";

import { API_URL } from "@/config";
import { readJsonResponse as readApiResponse } from "@/lib/api";
import { BackgroundNotice } from "@/components/background-notice";
import { RenderResult } from "@/components/render-result";
import type { RenderJob } from "@/components/render-result";
import { BrandColorPicker, CaptionPositionPicker, TemplatePicker } from "@/components/template-picker";
import { creditBudget, creditCost } from "@/lib/auth";
import { useAuthStatus } from "@/lib/auth-context";
import { DEFAULT_BRAND_COLOR, DEFAULT_CAPTION_POSITION, DEFAULT_TEMPLATE_ID } from "@/lib/render-options";
import type { CaptionPosition } from "@/lib/render-options";
import { useRenderOptions } from "@/lib/render-options-context";

export type ProductFacts = {
  provider: string;
  product_id: string;
  title: string;
  origin_price: number | null;
  sales_price: number | null;
  discount_rate: number | null;
  image_url: string;
  image_urls?: string[];
  product_url: string;
  facts: string[];
  description?: string | null;
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
  title?: string | null;
  description?: string | null;
};

function readJsonResponse<T>(response: Response): Promise<T> {
  return readApiResponse<T>(response, "요청을 처리하지 못했습니다.");
}

type Props = {
  sourceId: string;
  product: ProductFacts;
  content: ProductContent | null;
  onContent: (content: ProductContent) => void;
  onRenderStarted?: () => void;
};

const POLL_INTERVAL_MS = 1500;
const MAX_TITLE = 100;
const MAX_DESCRIPTION = 500;

function won(value: number | null) {
  return value === null ? null : `${value.toLocaleString("ko-KR")}원`;
}

/** Uploaded pictures (upload://) have no browser URL; previews fall back to the first https one. */
function previewImage(product: ProductFacts): string | null {
  const candidates = [product.image_url, ...(product.image_urls ?? [])];
  return candidates.find((url) => /^https?:\/\//i.test(url)) ?? null;
}

export function ProductStudio({ sourceId, product, content, onContent, onRenderStarted }: Props) {
  const [notes, setNotes] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [selectedAngleId, setSelectedAngleId] = useState<string | null>(null);
  const [templateId, setTemplateId] = useState(DEFAULT_TEMPLATE_ID);
  const [brandColor, setBrandColor] = useState(DEFAULT_BRAND_COLOR);
  const [captionPosition, setCaptionPosition] = useState<CaptionPosition["id"]>(DEFAULT_CAPTION_POSITION);
  const [meta, setMeta] = useState({ title: "", description: "" });
  const renderOptions = useRenderOptions();
  const [ctaUrl, setCtaUrl] = useState("");
  const [termsConfirmed, setTermsConfirmed] = useState(false);
  const [renderJob, setRenderJob] = useState<RenderJob | null>(null);
  const [isStartingRender, setIsStartingRender] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { status: authStatus } = useAuthStatus();
  const productCost = creditCost(authStatus, "product_short");
  const isAffiliate = product.provider === "coupang_partners";
  const pictureCount = Math.max(1, new Set([product.image_url, ...(product.image_urls ?? [])]).size);
  const selectedTemplate = renderOptions.templates.find((template) => template.id === templateId);

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

  function applyContent(next: ProductContent) {
    onContent(next);
    setSelectedAngleId(next.angles[0]?.id ?? null);
    setMeta({
      title: (next.title ?? product.title).slice(0, MAX_TITLE),
      description: (next.description ?? "").slice(0, MAX_DESCRIPTION),
    });
  }

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
      if (source.metadata.product_content) applyContent(source.metadata.product_content);
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
          ...(meta.title.trim() ? { title: meta.title.trim() } : {}),
          ...(meta.description.trim() ? { description: meta.description.trim() } : {}),
          brand_color: brandColor,
          caption_position: captionPosition,
        }),
      });
      setRenderJob(await readJsonResponse<RenderJob>(response));
      onRenderStarted?.();
    } catch (renderError) {
      setError(
        renderError instanceof Error ? renderError.message : "쇼츠 렌더를 시작하지 못했습니다.",
      );
    } finally {
      setIsStartingRender(false);
    }
  }

  const preview = previewImage(product);

  return (
    <section className="range-picker product-studio" aria-labelledby="product-heading">
      <div className="product-card">
        {preview ? (
          // Picture hosts vary (Coupang CDN, user URLs); a plain image avoids remote-pattern config.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="" />
        ) : (
          <span className="product-card-placeholder">사진 {pictureCount}장</span>
        )}
        <div>
          <h3 id="product-heading">{product.title}</h3>
          <p className="product-price">
            {product.discount_rate ? <span className="ai-score">{product.discount_rate}% 할인</span> : null}
            <strong>{won(product.sales_price) ?? "가격 정보 없음"}</strong>
            {product.origin_price && product.sales_price && product.origin_price > product.sales_price ? (
              <s>{won(product.origin_price)}</s>
            ) : null}
            {pictureCount > 1 ? <span className="candidate-time">사진 {pictureCount}장</span> : null}
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
          placeholder="예: 캠핑 갈 때 챙기는 음료로 소개 / 리뷰에서 본 장점 한 줄"
          aria-label="크리에이터 메모"
        />
      </label>

      <button
        type="button"
        className="submit-button"
        onClick={() => generateContent(Boolean(content))}
        disabled={isGenerating}
      >
        {isGenerating ? "AI가 아이디어를 짜는 중..." : content ? "앵글 다시 만들기" : "콘텐츠 앵글 만들기"}
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

          <section className="short-meta" aria-labelledby="product-meta-heading">
            <h3 id="product-meta-heading">제목과 설명</h3>
            <p className="range-help">
              AI가 추천한 문구예요. 자유롭게 고쳐 쓰세요. 제목은 영상 위 헤드라인으로 들어가고, [대괄호]로 감싼
              단어가 브랜드 컬러가 됩니다. 설명은 업로드할 때 씁니다.
            </p>
            <label className="field">
              <span>
                제목
                <small className="field-counter">
                  {meta.title.length} / {MAX_TITLE}
                </small>
              </span>
              <textarea
                aria-label="쇼츠 제목 추천"
                rows={2}
                maxLength={MAX_TITLE}
                value={meta.title}
                onChange={(event) => setMeta((current) => ({ ...current, title: event.target.value }))}
              />
            </label>
            <label className="field">
              <span>
                설명
                <small className="field-counter">
                  {meta.description.length} / {MAX_DESCRIPTION}
                </small>
              </span>
              <textarea
                aria-label="쇼츠 설명 추천"
                rows={4}
                maxLength={MAX_DESCRIPTION}
                value={meta.description}
                onChange={(event) => setMeta((current) => ({ ...current, description: event.target.value }))}
              />
            </label>
          </section>

          <TemplatePicker
            templates={renderOptions.templates}
            value={templateId}
            onChange={setTemplateId}
            layout="STAGE"
            imageUrl={preview}
            title={meta.title}
            brandColor={brandColor}
            captionPosition={captionPosition}
            channelName={authStatus.user?.name ?? null}
            description="사진이 가운데 들어가고 위에는 제목, 아래에는 말하는 문장과 가격이 놓입니다."
          />

          <div className="render-options-row">
            <BrandColorPicker swatches={renderOptions.brand_colors} value={brandColor} onChange={setBrandColor} />
          </div>

          {selectedTemplate?.preview.positionable === "true" ? (
            <CaptionPositionPicker
              positions={renderOptions.caption_positions}
              value={captionPosition}
              onChange={setCaptionPosition}
            />
          ) : null}

          <label className="field">
            <span>{isAffiliate ? "파트너스 단축 링크 (선택, 예: https://link.coupang.com/a/...)" : "영상 설명에 넣을 링크 (선택)"}</span>
            <input
              type="url"
              value={ctaUrl}
              onChange={(event) => setCtaUrl(event.target.value)}
              placeholder={isAffiliate ? "https://link.coupang.com/a/" : "https://"}
              aria-label={isAffiliate ? "파트너스 단축 링크" : "설명 링크"}
            />
          </label>

          <label className="rights-confirmation">
            <input
              type="checkbox"
              checked={termsConfirmed}
              onChange={(event) => setTermsConfirmed(event.target.checked)}
            />
            <span>
              <strong>{isAffiliate ? "쿠팡 파트너스 약관 확인" : "사진·정보 사용 권리 확인"}</strong>
              <small>
                {isAffiliate
                  ? "쿠팡 파트너스 회원으로서 제공된 상품 정보와 이미지를 약관 범위 안에서 사용하며, 영상에 파트너스 활동 고지 문구가 포함되는 것에 동의합니다."
                  : "올린 사진과 정보는 내가 직접 만들었거나 사용 허가를 받은 것이며, 광고·제휴 콘텐츠라면 해당 고지가 영상에 들어가는 것에 동의합니다."}
              </small>
            </span>
          </label>

          <button
            type="button"
            className="submit-button"
            onClick={startRender}
            disabled={!selectedAngle || !termsConfirmed || isStartingRender || renderActive}
          >
            {isStartingRender ? "시작하는 중..." : renderActive ? "재미나게 만드는 중..." : "짧은 영상 만들기"}
          </button>
          {productCost !== null ? (
            <p className="range-help">
              1편에 {productCost}크레딧이 차감됩니다
              {typeof authStatus.credits === "number"
                ? ` (보유 ${authStatus.credits}, 약 ${creditBudget(authStatus)?.productShorts ?? 0}편 가능)`
                : ""}
              . 실패 시 자동 환불됩니다.
            </p>
          ) : null}

          <BackgroundNotice jobId={renderJob?.id ?? null} projectHref={`/my/${sourceId}`} />
          {renderJob ? (
            <RenderResult job={renderJob} onRetry={startRender} retryDisabled={isStartingRender} />
          ) : null}
        </>
      ) : null}
    </section>
  );
}
