"use client";

import { useId, useRef, type CSSProperties } from "react";

import { headlineLines, isLightColor, longestWord } from "@/lib/render-options";
import type { BrandSwatch, CaptionPosition, CaptionTemplate, FrameLayout } from "@/lib/render-options";

type LayoutId = FrameLayout["id"];
type PositionId = CaptionPosition["id"];

/** Sample line shown on every card; the third word is the "spoken" one for karaoke styles. */
const SAMPLE_WORDS = ["이게", "바로", "자막입니다"];
const SPOKEN_INDEX = 2;
export const SAMPLE_TITLE = "AI가 고른 오늘의\n핵심 장면";
const SAMPLE_CHANNEL = "내 채널";
const SAMPLE_TAGS = "#하이라이트 #오늘의영상 #쇼츠";
const DEFAULT_BRAND = "#4FE1E1";

type SampleProps = {
  template: CaptionTemplate;
  layout: LayoutId;
  /** A frame from the viewer's own video (thumbnail, captured frame, or product image). */
  imageUrl: string | null;
  /** Headline to show; the sample title when the viewer has not typed one. */
  title?: string | null;
  showHeadline?: boolean;
  brandColor?: string;
  captionPosition?: PositionId;
  channelName?: string | null;
};

function Frame({ imageUrl, layout }: { imageUrl: string | null; layout: LayoutId }) {
  if (!imageUrl) return <span className="caption-sample-frame caption-sample-placeholder" />;
  return (
    <>
      {layout === "FIT" ? (
        <span className="caption-sample-blur" style={{ backgroundImage: `url("${imageUrl}")` }} />
      ) : null}
      <span className="caption-sample-frame" style={{ backgroundImage: `url("${imageUrl}")` }} />
    </>
  );
}

/**
 * A miniature 9:16 frame: the template's stage, the viewer's video placed with the
 * chosen layout, the headline and chrome above it and the caption below or over it.
 * The real render uses the same geometry, so what the card shows is where things land.
 */
export function CaptionSample({
  template,
  layout,
  imageUrl,
  title,
  showHeadline = true,
  brandColor = DEFAULT_BRAND,
  captionPosition = "BOTTOM",
  channelName,
}: SampleProps) {
  const { preview } = template;
  const onStage = layout === "STAGE";
  const stageColor = onStage ? (preview.stage ?? "#000000") : "#000000";
  const light = onStage && isLightColor(stageColor);
  const textColor = light ? "#222222" : "#FFFFFF";
  const outline = light ? "none" : "-1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000";
  const captionKind = preview.caption ?? "plain";
  const headlineText = (title && title.trim()) || SAMPLE_TITLE;
  const leftAligned = onStage && Boolean(preview.tagline || preview.kicker);
  const captionWordStyle = (index: number): CSSProperties | undefined => {
    if (captionKind === "karaoke" && index === SPOKEN_INDEX) return { color: brandColor };
    if (captionKind === "pop" && SAMPLE_WORDS[index] === longestWord(SAMPLE_WORDS.join(" ")))
      return { color: brandColor };
    return undefined;
  };
  const captionBase: CSSProperties = {
    color: textColor,
    fontWeight: Number(preview.weight ?? "800"),
    fontSize: captionKind === "pop" ? "6.67cqw" : captionKind === "karaoke" ? "5.74cqw" : "5.19cqw",
    textShadow: outline,
  };
  if (preview.background && !onStage) {
    captionBase.backgroundColor = preview.background;
    captionBase.padding = "3px 7px";
    captionBase.borderRadius = "3px";
  }
  return (
    <span
      className={`caption-sample caption-sample-${layout.toLowerCase()} caption-sample-${preview.positionable === "true" ? captionPosition.toLowerCase() : "bottom"}${leftAligned ? " caption-sample-left" : ""}${onStage && preview.tagline ? " caption-sample-social" : ""}${onStage && preview.kicker ? " caption-sample-community" : ""}`}
      style={{ background: stageColor }}
      aria-hidden="true"
    >
      <Frame imageUrl={imageUrl} layout={layout} />
      {onStage && preview.headerBand ? (
        <span className="caption-sample-band" style={{ background: brandColor, color: "#222" }}>
          {preview.headerBand}
        </span>
      ) : null}
      {onStage && preview.kicker ? (
        <span className="caption-sample-kicker" style={{ color: brandColor }}>
          {preview.kicker}
        </span>
      ) : null}
      {onStage && preview.tagline ? (
        <span className="caption-sample-pill" style={{ background: brandColor, color: "#222" }}>
          {preview.tagline}
        </span>
      ) : null}
      {showHeadline ? (
        <b
          className="caption-sample-headline"
          style={{
            color: textColor,
            textShadow: preview.headlineBox === "true" ? "none" : outline,
            backgroundColor: preview.headlineBox === "true" ? "rgba(0,0,0,0.85)" : undefined,
          }}
        >
          {headlineLines(headlineText).map((runs, lineIndex) => (
            <span key={`line-${lineIndex}`} className="caption-sample-headline-line">
              {runs.map((run, runIndex) => (
                <span key={`${runIndex}-${run.text}`} style={run.accent ? { color: brandColor } : undefined}>
                  {run.text}
                </span>
              ))}
            </span>
          ))}
        </b>
      ) : null}
      {onStage && preview.tagline ? (
        <span className="caption-sample-tags" style={{ color: brandColor }}>
          {SAMPLE_TAGS}
        </span>
      ) : null}
      {preview.channel === "true" && layout !== "FILL" ? (
        <span className="caption-sample-channel" style={{ color: textColor }}>
          <i /> {channelName?.trim() || SAMPLE_CHANNEL}
        </span>
      ) : null}
      {captionKind !== "none" ? (
        <b className="caption-sample-caption" style={captionBase}>
          {SAMPLE_WORDS.map((word, index) => (
            <span key={word} style={captionWordStyle(index)}>
              {word}
              {index < SAMPLE_WORDS.length - 1 ? " " : ""}
            </span>
          ))}
        </b>
      ) : null}
    </span>
  );
}

type TemplatePickerProps = {
  templates: CaptionTemplate[];
  value: string;
  onChange: (id: string) => void;
  layout?: LayoutId;
  imageUrl: string | null;
  title?: string | null;
  showHeadline?: boolean;
  description?: string;
  brandColor?: string;
  captionPosition?: PositionId;
  channelName?: string | null;
};

export function TemplatePicker({
  templates,
  value,
  onChange,
  layout = "STAGE",
  imageUrl,
  title,
  showHeadline = true,
  description,
  brandColor,
  captionPosition,
  channelName,
}: TemplatePickerProps) {
  const selected = templates.find((template) => template.id === value);
  const strip = useRef<HTMLDivElement>(null);
  const stripId = useId();
  const scroll = (direction: number) => {
    const element = strip.current;
    if (element) element.scrollBy({ left: direction * element.clientWidth * 0.8, behavior: "smooth" });
  };
  return (
    <fieldset className="template-picker">
      <legend>
        템플릿 {selected ? <em className="template-selected-name">{selected.name}</em> : null}
      </legend>
      <p>
        {description ?? "스타일을 고르면 제목과 자막 디자인에 적용됩니다. 카드는 배치 예시이며 실제 자막은 영상에 맞춰 생성돼요."}
        {imageUrl ? null : " 영상을 불러오면 그 장면이 미리보기에 들어갑니다."}
      </p>
      <div className="template-browse">
        <span>{templates.length}가지 스타일 · 옆으로 넘겨 비교하세요</span>
        <div>
          <button type="button" aria-label="이전 스타일 보기" aria-controls={stripId} onClick={() => scroll(-1)}>←</button>
          <button type="button" aria-label="다음 스타일 보기" aria-controls={stripId} onClick={() => scroll(1)}>→</button>
        </div>
      </div>
      <div ref={strip} id={stripId} className="template-options template-scroll">
        {templates.map((template) => (
          <button
            key={template.id}
            type="button"
            className="template-card"
            aria-pressed={value === template.id}
            aria-label={`${template.name} 템플릿`}
            onClick={() => onChange(template.id)}
            onFocus={(event) => event.currentTarget.scrollIntoView?.({ block: "nearest", inline: "nearest" })}
          >
            <span className="template-selection-mark" aria-hidden="true">{value === template.id ? "✓ 선택됨" : "선택"}</span>
            <CaptionSample
              template={template}
              layout={layout}
              imageUrl={imageUrl}
              title={title}
              showHeadline={showHeadline}
              brandColor={brandColor}
              captionPosition={captionPosition}
              channelName={channelName}
            />
            <strong>
              {template.name} <em>{template.tag}</em>
            </strong>
            <small>{template.description}</small>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

type LayoutPickerProps = {
  layouts: FrameLayout[];
  value: LayoutId;
  onChange: (id: LayoutId) => void;
  imageUrl: string | null;
  stageColor?: string;
};

export function LayoutPicker({ layouts, value, onChange, imageUrl, stageColor = "#000000" }: LayoutPickerProps) {
  return (
    <fieldset className="template-picker layout-picker">
      <legend>화면 배치</legend>
      <p>원본에 자막이나 중요한 화면이 양옆에 있다면 원본을 그대로 두는 배치를 고르세요.</p>
      <div className="layout-options">
        {layouts.map((layout) => (
          <button
            key={layout.id}
            type="button"
            className="template-card"
            aria-pressed={value === layout.id}
            aria-label={`${layout.name} 배치`}
            onClick={() => onChange(layout.id)}
          >
            <span
              className={`caption-sample caption-sample-${layout.id.toLowerCase()} caption-sample-bottom`}
              style={{ background: layout.id === "STAGE" ? stageColor : "#000" }}
              aria-hidden="true"
            >
              <Frame imageUrl={imageUrl} layout={layout.id} />
            </span>
            <strong>{layout.name}</strong>
            <small>{layout.description}</small>
          </button>
        ))}
      </div>
    </fieldset>
  );
}

type BrandColorPickerProps = {
  swatches: BrandSwatch[];
  value: string;
  onChange: (hex: string) => void;
};

export function BrandColorPicker({ swatches, value, onChange }: BrandColorPickerProps) {
  const custom = !swatches.some((swatch) => swatch.hex.toLowerCase() === value.toLowerCase());
  const current = swatches.find((swatch) => swatch.hex.toLowerCase() === value.toLowerCase());
  return (
    <div className="brand-picker" role="group" aria-label="브랜드 컬러">
      <span className="brand-picker-label">브랜드 컬러</span>
      {swatches.map((swatch) => (
        <button
          key={swatch.id}
          type="button"
          className="brand-swatch"
          style={{ background: swatch.hex }}
          aria-label={`${swatch.name} 컬러`}
          aria-pressed={swatch.hex.toLowerCase() === value.toLowerCase()}
          onClick={() => onChange(swatch.hex)}
        />
      ))}
      <label className={custom ? "brand-swatch brand-custom selected" : "brand-swatch brand-custom"} title="직접 고르기">
        <span aria-hidden="true">+</span>
        <input
          type="color"
          aria-label="브랜드 컬러 직접 선택"
          value={value}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
        />
      </label>
      <span className="brand-picker-name">{current?.name ?? value.toUpperCase()}</span>
    </div>
  );
}

type CaptionPositionPickerProps = {
  positions: CaptionPosition[];
  value: PositionId;
  onChange: (id: PositionId) => void;
};

export function CaptionPositionPicker({ positions, value, onChange }: CaptionPositionPickerProps) {
  return (
    <fieldset className="template-picker position-picker">
      <legend>자막 위치</legend>
      <p>영상에 맞는 위치를 고르면 미리보기에 바로 반영돼요.</p>
      <div className="position-options">
        {positions.map((position) => (
          <button
            key={position.id}
            type="button"
            className="position-card"
            aria-pressed={value === position.id}
            aria-label={`자막 ${position.name}`}
            onClick={() => onChange(position.id)}
          >
            <strong>{position.name}</strong>
            <small>{position.description}</small>
            <i aria-hidden="true" className={`position-glyph position-glyph-${position.id.toLowerCase()}`} />
          </button>
        ))}
      </div>
    </fieldset>
  );
}

/** Output sizes: only 9:16 renders today; the others are shown so the plan is visible. */
export function AspectRatioChips({ ratios }: { ratios: Array<{ id: string; available: boolean }> }) {
  return (
    <div className="ratio-chips" role="group" aria-label="영상 비율">
      <span className="brand-picker-label">영상 비율</span>
      {ratios.map((ratio) => (
        <button
          key={ratio.id}
          type="button"
          className="ratio-chip"
          aria-pressed={ratio.available}
          disabled={!ratio.available}
          title={ratio.available ? "쇼츠 세로 비율" : "준비 중"}
        >
          {ratio.id}
        </button>
      ))}
      <small className="ratio-note">지금은 쇼츠 세로(9:16)만 만들 수 있어요. 다른 비율은 준비 중입니다.</small>
    </div>
  );
}
