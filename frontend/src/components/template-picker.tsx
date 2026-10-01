"use client";

import type { CSSProperties } from "react";

import type { CaptionTemplate, FrameLayout } from "@/lib/render-options";

type LayoutId = FrameLayout["id"];

/** Sample line shown on every card; the third word is the "spoken" one for karaoke styles. */
const SAMPLE_WORDS = ["이", "장면이", "핵심이에요"];
const SPOKEN_INDEX = 2;

type SampleProps = {
  template: CaptionTemplate;
  layout: LayoutId;
  /** A frame from the viewer's own video (thumbnail, captured frame, or product image). */
  imageUrl: string | null;
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

/**
 * A miniature 9:16 frame: the viewer's video placed with the chosen layout, the
 * template's caption on top. The real render uses the same geometry, so what the
 * card shows is where the text will land.
 */
export function CaptionSample({ template, layout, imageUrl }: SampleProps) {
  const spoken = spokenStyle(template);
  const position = layout === "FIT" ? "fit" : template.id === "IMPACT_YELLOW" ? "middle" : "bottom";
  return (
    <span
      className={`caption-sample caption-sample-${layout.toLowerCase()} caption-sample-${position}`}
      aria-hidden="true"
    >
      {imageUrl ? (
        <>
          {layout === "FIT" ? (
            <span className="caption-sample-blur" style={{ backgroundImage: `url("${imageUrl}")` }} />
          ) : null}
          <span className="caption-sample-frame" style={{ backgroundImage: `url("${imageUrl}")` }} />
        </>
      ) : (
        <span className="caption-sample-frame caption-sample-placeholder" />
      )}
      <b style={captionStyle(template)}>
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
  description?: string;
};

export function TemplatePicker({
  templates,
  value,
  onChange,
  layout = "FILL",
  imageUrl,
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
            <CaptionSample template={template} layout={layout} imageUrl={imageUrl} />
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
      <p>원본에 자막이나 중요한 화면이 양옆에 있다면 ‘원본 그대로’를 고르세요.</p>
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
              {imageUrl ? (
                <>
                  {layout.id === "FIT" ? (
                    <span
                      className="caption-sample-blur"
                      style={{ backgroundImage: `url("${imageUrl}")` }}
                    />
                  ) : null}
                  <span
                    className="caption-sample-frame"
                    style={{ backgroundImage: `url("${imageUrl}")` }}
                  />
                </>
              ) : (
                <span className="caption-sample-frame caption-sample-placeholder" />
              )}
            </span>
            <strong>{layout.name}</strong>
            <small>{layout.description}</small>
          </button>
        ))}
      </div>
    </fieldset>
  );
}
