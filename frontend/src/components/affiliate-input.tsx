"use client";

import { useState } from "react";
import type { FormEvent } from "react";

import { API_URL } from "@/config";
import { ProductStudio } from "@/components/product-studio";
import type { ProductContent, ProductFacts } from "@/components/product-studio";

type Source = {
  id: string;
  type: "YOUTUBE" | "PRODUCT" | "UPLOAD";
  status: "CREATED" | "PREPARING" | "READY" | "FAILED";
  metadata?: {
    product?: ProductFacts;
    product_content?: ProductContent;
  };
};

const STEPS = ["링크", "상품 확인 · 앵글", "옵션", "결과"];

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
    hint: "아고다 파트너 링크는 준비 중입니다.",
  },
  {
    id: "trip",
    name: "트립닷컴",
    hosts: ["trip.com", "kr.trip.com", "ctrip.com"],
    status: "planned",
    hint: "트립닷컴 어필리에이트 링크는 준비 중입니다.",
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

export function AffiliateInput() {
  const [url, setUrl] = useState("");
  const [source, setSource] = useState<Source | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
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

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSource(null);
    setResultStage("idle");
    const requestedUrl = url.trim();
    const detected = detectProvider(requestedUrl);
    if (!detected) {
      setError("지원하는 어필리에이트 링크가 아닙니다. 현재는 쿠팡 파트너스 링크를 처리합니다.");
      return;
    }
    if (detected.status === "planned") {
      setError(`${detected.name} 링크는 준비 중입니다. 지금은 쿠팡 파트너스 링크만 처리할 수 있습니다.`);
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
      setError(
        submitError instanceof Error ? submitError.message : "상품 정보를 불러오지 못했습니다.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="source-panel" aria-labelledby="affiliate-heading">
      <div className="source-heading">
        <div>
          <p className="section-label">AFFILIATE SHORTS</p>
          <h2 id="affiliate-heading">어떤 상품을 소개할까요?</h2>
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

      <ul className="provider-list" aria-label="지원 공급자">
        {AFFILIATE_PROVIDERS.map((item) => (
          <li key={item.id} className={item.status}>
            {item.name}
            <small>{item.status === "ready" ? "지원" : "준비 중"}</small>
          </li>
        ))}
      </ul>

      <form className="source-entry-form" onSubmit={handleSubmit}>
        <p className="form-intro">쿠팡 파트너스 링크를 넣으면 상품 정보를 먼저 확인할 수 있어요.</p>
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

      {error ? (
        <p className="message error-message" role="alert">
          {error}
        </p>
      ) : null}

      {source?.status === "READY" && source.metadata?.product ? (
        <div className="source-result" aria-live="polite">
          <div className="source-result-header">
            <span>{source.metadata.product.provider === "coupang_partners" ? "쿠팡 파트너스" : source.type}</span>
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
