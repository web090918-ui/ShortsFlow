"use client";

import type { CSSProperties } from "react";

import { headlineLines } from "@/lib/render-options";
import type { CaptionTemplate, FrameLayout } from "@/lib/render-options";

type LayoutId = FrameLayout["id"];

/** Sample line shown on every card; the third word is the "spoken" one for karaoke styles. */
const SAMPLE_WORDS = ["이", "장면이", "핵심이에요"];
const SPOKEN_INDEX = 2;
export const SAMPLE_TITLE = "이 장면 하나로\n[채널]이 달라집니다";

type SampleProps = {
  template: CaptionTemplate;
  layout: LayoutId;
  /** A frame from the viewer's own video (thumbnail, captured frame, or product image). */
  imageUrl: string | null;
  /** Headline to show; the sample title when the viewer has not typed one. */
  title?: string | null;
  showHeadline?: boolean;
};

function captionStyle(template: CaptionTemplate): CSSProperties {
  const { preview } = template;
  const style: CSSProperties = {
    color: preview.color ?? "#fff",
    fontWeight: Number(preview.weight ?? "700"),
  };
  if (preview.font === "monospace") style.fontFamily = "'Nanum Gothic Coding', monospace";
  if (preview.font === "cursive") style.fontFamily = "'Nanum Pen Script', cursive";
  if (preview.background) {
    style.backgroundColor = preview.background;
    style.padding = "3px 7px";
    style.borderRadius = "3px";
  } else if (preview.stroke) {
    const s = preview.stroke;
    style.textShadow = `-1px -1px 0 ${s}, 1px -1px 0 ${s}, -1px 1px 0 ${s}, 1px 1px 0 ${s}`;
  }
  if (preview.glow === "true") {
    const g = preview.stroke ?? preview.color ?? "#fff";
    style.textShadow = `0 0 6px ${g}, 0 0 12px ${g}`;
  }
  return style;
}

function spokenStyle(template: CaptionTemplate): CSSProperties | undefined {
  if (!template.karaoke || !template.preview.accent) return undefined;
  return { color: template.preview.accent };
}

function headlineStyle(template: CaptionTemplate): CSSProperties {
  const boxed = template.preview.headlineBox === "true";
  return boxed
    ? { backgroundColor: "rgba(0, 0, 0, 0.85)", padding: "3px 8px", borderRadius: "3px" }
    : { textShadow: "-1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000" };
}

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
 * A miniature 9:16 frame: the viewer's video placed with the chosen layout, the
 * headline above it and the template's caption below. The real render uses the
 * same geometry, so what the card shows is where the text will land.
 */
export function CaptionSample({ template, layout, imageUrl, title, showHeadline = true }: SampleProps) {
  const spoken = spokenStyle(template);
  const accent = template.preview.headlineAccent ?? "#FFD23F";
  const position = layout === "FILL" && template.id === "IMPACT_YELLOW" ? "middle" : "bottom";
  const headlineText = (title && title.trim()) || SAMPLE_TITLE;
  return (
    <span
      className={`caption-sample caption-sample-${layout.toLowerCase()} caption-sample-${position}`}
      aria-hidden="true"
    >
      <Frame imageUrl={imageUrl} layout={layout} />
      {showHeadline ? (
        <b className="caption-sample-headline" style={headlineStyle(template)}>
          {headlineLines(headlineText).map((runs, lineIndex) => (
            <span key={`line-${lineIndex}`} className="caption-sample-headline-line">
              {runs.map((run, runIndex) => (
                <span key={`${runIndex}-${run.text}`} style={run.accent ? { color: accent } : undefined}>
                  {run.text}
                </span>
              ))}
            </span>
          ))}
        </b>
      ) : null}
      <b className="caption-sample-caption" style={captionStyle(template)}>
        {SAMPLE_WORDS.map((word, index) => (
          <span key={word} style={index === SPOKEN_INDEX ? spoken : undefined}>
            {word}
            {index < SAMPLE_WORDS.length - 1 ? " " : ""}
          </span>
        ))}
      </b>
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
}: TemplatePickerProps) {
  return (
    <fieldset className="template-picker">
      <legend>자막 템플릿</legend>
      <p>
        {description ?? "내 영상 위에 어떻게 보이는지 그대로 미리 보여 드려요."}
        {imageUrl ? null : " 영상을 불러오면 그 장면이 미리보기에 들어갑니다."}
      </p>
      <div className="template-options">
        {templates.map((template) => (
          <button
            key={template.id}
            type="button"
            className="template-card"
            aria-pressed={value === template.id}
            aria-label={`${template.name} 템플릿`}
            onClick={() => onChange(template.id)}
          >
            <CaptionSample
              template={template}
              layout={layout}
              imageUrl={imageUrl}
              title={title}
              showHeadline={showHeadline}
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
};

export function LayoutPicker({ layouts, value, onChange, imageUrl }: LayoutPickerProps) {
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
