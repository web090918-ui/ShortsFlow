"use client";

import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";

import { API_URL } from "@/config";
import { ProductStudio } from "@/components/product-studio";
import type { ProductContent, ProductFacts } from "@/components/product-studio";
import { putUpload } from "@/lib/upload";
import type { UploadTarget } from "@/lib/upload";

type Source = {
  id: string;
  type: "YOUTUBE" | "PRODUCT" | "UPLOAD";
  status: "CREATED" | "PREPARING" | "READY" | "FAILED";
  metadata?: {
    product?: ProductFacts;
    product_content?: ProductContent;
  };
};

type InputMode = "manual" | "link";
type PictureItem = { id: string; kind: "file"; file: File; preview: string } | { id: string; kind: "url"; url: string };

const STEPS = ["정보·사진", "확인 · 앵글", "옵션", "결과"];
export const MAX_PICTURES = 3;

export const AFFILIATE_PROVIDERS: Array<{
  id: string;
  name: string;
  hosts: string[];
  status: "ready" | "planned";
  hint: string;
}> = [
  {
    id: "coupang",
    name: "쿠팡 파트너스",
    hosts: ["partners.coupang.com", "coupang.com", "link.coupang.com"],
    status: "ready",
    hint: "파트너스 링크 생성 화면(partners.coupang.com/#affiliate/ws/linkgeneration/...)의 URL을 붙여 주세요.",
  },
  {
    id: "agoda",
    name: "아고다",
    hosts: ["agoda.com", "agoda.co.kr"],
    status: "planned",
    hint: "아고다 파트너 링크는 준비 중입니다. 호텔 이름·사진·요금을 직접 입력하면 바로 만들 수 있어요.",
  },
  {
    id: "trip",
    name: "트립닷컴",
    hosts: ["trip.com", "kr.trip.com", "ctrip.com"],
    status: "planned",
    hint: "트립닷컴 어필리에이트 링크는 준비 중입니다. 정보를 직접 입력하면 바로 만들 수 있어요.",
  },
];

export function detectProvider(value: string) {
  try {
    const hostname = new URL(value).hostname.toLowerCase().replace(/^www\./, "");
    return (
      AFFILIATE_PROVIDERS.find((provider) =>
        provider.hosts.some((host) => hostname === host || hostname.endsWith(`.${host}`)),
      ) ?? null
    );
  } catch {
    return null;
  }
}

async function readJsonResponse<T>(response: Response): Promise<T> {
  const payload = await response.json();
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : null;
    throw new Error(detail ?? "요청을 처리하지 못했습니다.");
  }
  return payload as T;
}

function parsePrice(value: string): number | null {
  const digits = value.replace(/[^\d]/g, "");
  return digits ? Number(digits) : null;
}

let pictureCounter = 0;

/** Upload one picture through the API's signed/direct target and return its upload:// URL. */
async function uploadPicture(file: File): Promise<string> {
  const registered = await readJsonResponse<{ image_url: string; upload: UploadTarget }>(
    await fetch(`${API_URL}/sources/product-images`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, content_type: file.type || "image/jpeg", size_bytes: file.size }),
    }),
  );
  await putUpload(registered.upload, file);
  return registered.image_url;
}

export function AffiliateInput() {
  const [mode, setMode] = useState<InputMode>("manual");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [salesPrice, setSalesPrice] = useState("");
  const [originPrice, setOriginPrice] = useState("");
  const [description, setDescription] = useState("");
  const [productUrl, setProductUrl] = useState("");
  const [pictures, setPictures] = useState<PictureItem[]>([]);
  const [pictureUrl, setPictureUrl] = useState("");
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [resultStage, setResultStage] = useState<"idle" | "options" | "result">("idle");

  const provider = detectProvider(url.trim());
  const currentStep =
    resultStage === "result"
      ? 4
      : source?.metadata?.product_content
        ? resultStage === "options"
          ? 3
          : 2
        : source?.status === "READY"
          ? 2
          : 1;

  function addFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    setPictures((current) => {
      const room = MAX_PICTURES - current.length;
      const added = files.slice(0, Math.max(0, room)).map((file) => ({
        id: `p${++pictureCounter}`,
        kind: "file" as const,
        file,
        preview: typeof URL.createObjectURL === "function" ? URL.createObjectURL(file) : "",
      }));
      return [...current, ...added];
    });
  }

  function addPictureUrl() {
    const value = pictureUrl.trim();
    if (!value) return;
    if (!/^https:\/\//i.test(value)) {
      setError("이미지 주소는 https로 시작해야 합니다.");
      return;
    }
    setError(null);
    setPictures((current) =>
      current.length >= MAX_PICTURES ? current : [...current, { id: `p${++pictureCounter}`, kind: "url", url: value }],
    );
    setPictureUrl("");
  }

  function removePicture(id: string) {
    setPictures((current) => current.filter((item) => item.id !== id));
  }

  async function handleManualSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSource(null);
    setResultStage("idle");
    if (!title.trim()) {
      setError("제목을 입력해 주세요.");
      return;
    }
    if (pictures.length === 0) {
      setError("사진을 1장 이상 넣어 주세요.");
      return;
    }
    setIsSubmitting(true);
    try {
      const imageUrls: string[] = [];
      for (const [index, picture] of pictures.entries()) {
        if (picture.kind === "url") {
          imageUrls.push(picture.url);
          continue;
        }
        setProgress(`사진 ${index + 1}/${pictures.length} 올리는 중...`);
        imageUrls.push(await uploadPicture(picture.file));
      }
      setProgress("정보 정리 중...");
      const response = await fetch(`${API_URL}/sources/product`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: title.trim(),
          sales_price: parsePrice(salesPrice),
          origin_price: parsePrice(originPrice),
          description: description.trim() || null,
          image_urls: imageUrls,
          product_url: productUrl.trim() || null,
        }),
      });
      setSource(await readJsonResponse<Source>(response));
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "정보를 저장하지 못했습니다.");
    } finally {
      setIsSubmitting(false);
      setProgress(null);
    }
  }

  async function handleLinkSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSource(null);
    setResultStage("idle");
    const requestedUrl = url.trim();
    const detected = detectProvider(requestedUrl);
    if (!detected) {
      setError("지원하는 어필리에이트 링크가 아닙니다. 현재는 쿠팡 파트너스 링크를 처리합니다. 다른 상품은 ‘직접 입력’으로 만들어 보세요.");
      return;
    }
    if (detected.status === "planned") {
      setError(`${detected.name} 링크는 준비 중입니다. ‘직접 입력’에서 이름·사진·가격을 넣으면 바로 만들 수 있어요.`);
      return;
    }
    setIsSubmitting(true);
    try {
      const response = await fetch(`${API_URL}/sources?prepare=true`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: requestedUrl }),
      });
      setSource(await readJsonResponse<Source>(response));
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "상품 정보를 불러오지 못했습니다.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const providerLabel =
    source?.metadata?.product?.provider === "coupang_partners"
      ? "쿠팡 파트너스"
      : source?.metadata?.product?.provider === "manual"
        ? "직접 입력"
        : source?.type;

  return (
    <section className="source-panel affiliate-panel" aria-labelledby="affiliate-heading">
      <div className="source-heading">
        <div>
          <p className="section-label">TEXT · PHOTO SHORTS</p>
          <h2 id="affiliate-heading">정보·이야기·사진을 짧은 영상으로</h2>
        </div>
      </div>

      <ol className="stepper" aria-label="진행 단계">
        {STEPS.map((label, index) => {
          const number = index + 1;
          const state = number < currentStep ? "done" : number === currentStep ? "current" : "";
          return (
            <li key={label} className={state} aria-current={number === currentStep ? "step" : undefined}>
              <span>{number}</span>
              {label}
            </li>
          );
        })}
      </ol>

      <div className="mode-switch" aria-label="입력 방식">
        <button type="button" aria-pressed={mode === "manual"} className={mode === "manual" ? "active" : ""} onClick={() => { setMode("manual"); setError(null); }}>
          직접 입력
        </button>
        <button type="button" aria-pressed={mode === "link"} className={mode === "link" ? "active" : ""} onClick={() => { setMode("link"); setError(null); }}>
          어필리에이트 링크
        </button>
      </div>

      {mode === "manual" ? (
        <form className="manual-product-form" onSubmit={handleManualSubmit}>
          <p className="form-intro">
            제목과 사진 1장 이상을 넣어 주세요. 가격·설명·링크는 선택 사항입니다.
          </p>
          <label className="field">
            <span>제목</span>
            <input
              type="text"
              value={title}
              maxLength={120}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="예: 코카콜라 오리지널 190ml 30개 / 도쿄 다이아몬드 호텔 6박"
              aria-label="제목"
              required
            />
          </label>
          <div className="field-row">
            <label className="field">
              <span>가격 (선택)</span>
              <input
                type="text"
                inputMode="numeric"
                value={salesPrice}
                onChange={(event) => setSalesPrice(event.target.value)}
                placeholder="13200"
                aria-label="가격"
              />
            </label>
            <label className="field">
              <span>정가 (선택)</span>
              <input
                type="text"
                inputMode="numeric"
                value={originPrice}
                onChange={(event) => setOriginPrice(event.target.value)}
                placeholder="21900"
                aria-label="정가"
              />
            </label>
          </div>
          <label className="field">
            <span>설명 · 이야기 (선택)</span>
            <textarea
              value={description}
              rows={4}
              maxLength={1000}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="특징, 써 본 느낌, 리뷰에서 본 이야기 등을 자유롭게 적어 주세요. AI가 대본에 반영합니다."
              aria-label="설명"
            />
          </label>

          <fieldset className="picture-field">
            <legend>사진 <span className="picture-count">{pictures.length}/{MAX_PICTURES}장</span></legend>
            <div className="picture-list">
              {pictures.map((picture, index) => (
                <figure key={picture.id} className="picture-item">
                  {/* Local previews and arbitrary hosts; a plain image avoids remote-pattern config. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={picture.kind === "file" ? picture.preview : picture.url} alt="" />
                  <figcaption>{index === 0 ? "대표" : `${index + 1}번째`}</figcaption>
                  <button type="button" onClick={() => removePicture(picture.id)} aria-label={`사진 ${index + 1} 삭제`}>
                    ×
                  </button>
                </figure>
              ))}
              {pictures.length < MAX_PICTURES ? (
                <label className="picture-add">
                  <input type="file" accept="image/*" multiple onChange={addFiles} aria-label="사진 파일" />
                  <span>+ 사진 올리기</span>
                </label>
              ) : null}
            </div>
            <div className="picture-url-row">
              <input
                type="url"
                spellCheck={false}
                value={pictureUrl}
                onChange={(event) => setPictureUrl(event.target.value)}
                placeholder="또는 이미지 주소(https://...)를 붙여 넣고 추가"
                aria-label="이미지 주소"
              />
              <button type="button" className="secondary-button submit-button" onClick={addPictureUrl} disabled={!pictureUrl.trim() || pictures.length >= MAX_PICTURES}>
                추가
              </button>
            </div>
            <p className="range-help">첫 번째 사진이 대표 사진이 되고, 여러 장이면 문장을 따라 차례로 바뀝니다.</p>
          </fieldset>

          <label className="field">
            <span>링크 (선택)</span>
            <input
              type="url"
              value={productUrl}
              onChange={(event) => setProductUrl(event.target.value)}
              placeholder="영상 설명에 넣을 상품·예약·블로그 링크"
              aria-label="링크"
            />
          </label>

          <button className="submit-button source-entry-submit" type="submit" disabled={isSubmitting}>
            {isSubmitting ? progress ?? "저장하는 중..." : "이 정보로 시작하기"}
          </button>
          <p className="input-footnote">다음 단계에서 AI가 소개 방향 3가지와 제목·설명을 제안합니다.</p>
        </form>
      ) : (
        <form className="source-entry-form affiliate-link-form" onSubmit={handleLinkSubmit}>
          <p className="form-intro">쿠팡 파트너스 링크를 넣으면 상품명·가격·이미지를 자동으로 채웁니다.</p>
          <ul className="provider-list" aria-label="지원 공급자">
            {AFFILIATE_PROVIDERS.map((item) => (
              <li key={item.id} className={item.status}>
                {item.name}
                <small>{item.status === "ready" ? "지원" : "준비 중"}</small>
              </li>
            ))}
          </ul>
          <label className="field">
            <span>어필리에이트 링크</span>
            <input
              type="url"
              spellCheck={false}
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://partners.coupang.com/#affiliate/ws/linkgeneration/..."
              required
            />
          </label>
          <p className={provider?.status === "planned" ? "range-help range-error" : "range-help"}>
            {provider ? `${provider.name} · ${provider.hint}` : AFFILIATE_PROVIDERS[0].hint}
          </p>
          <button className="submit-button source-entry-submit" type="submit" disabled={isSubmitting}>
            {isSubmitting ? "상품 정보 불러오는 중..." : "상품 정보 불러오기"}
          </button>
          <p className="input-footnote">상품을 확인한 뒤, 소개할 콘텐츠 앵글을 선택하세요.</p>
        </form>
      )}

      {error ? (
        <p className="message error-message" role="alert">
          {error}
        </p>
      ) : null}

      {source?.status === "READY" && source.metadata?.product ? (
        <div className="source-result" aria-live="polite">
          <div className="source-result-header">
            <span>{providerLabel}</span>
            <strong>{source.status}</strong>
          </div>
          <ProductStudio
            sourceId={source.id}
            product={source.metadata.product}
            content={source.metadata.product_content ?? null}
            onContent={(content) => {
              setResultStage("options");
              setSource((current) =>
                current
                  ? { ...current, metadata: { ...current.metadata, product_content: content } }
                  : current,
              );
            }}
            onRenderStarted={() => setResultStage("result")}
          />
        </div>
      ) : null}
    </section>
  );
}
