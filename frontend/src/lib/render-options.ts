import { API_URL } from "@/config";

/** Caption preset as the backend `GET /templates` describes it. */
export type CaptionTemplate = {
  id: string;
  name: string;
  description: string;
  tag: string;
  karaoke: boolean;
  preview: {
    color?: string;
    stroke?: string;
    background?: string;
    accent?: string;
    weight?: string;
    font?: string;
    glow?: string;
  };
};

export type FrameLayout = {
  id: "FILL" | "FIT";
  name: string;
  description: string;
};

export type RenderOptions = {
  templates: CaptionTemplate[];
  layouts: FrameLayout[];
};

/**
 * Built-in copy of the catalog so the pickers render before (or without) the
 * server answer. The server list wins once it arrives; keep ids in sync with
 * `backend/app/templates.py`.
 */
export const DEFAULT_RENDER_OPTIONS: RenderOptions = {
  templates: [
    {
      id: "CLEAN_CAPTION",
      name: "Clean Caption",
      description: "읽기 쉬운 기본 자막. 흰 글씨에 검은 외곽선.",
      tag: "기본",
      karaoke: false,
      preview: { color: "#FFFFFF", stroke: "#000000", weight: "700" },
    },
    {
      id: "BOLD_HIGHLIGHT",
      name: "Bold Highlight",
      description: "형광 글씨를 검은 박스 위에. 핵심 문장을 강하게.",
      tag: "강조",
      karaoke: false,
      preview: { color: "#D7FF4F", background: "#111111", weight: "800" },
    },
    {
      id: "MINIMAL",
      name: "Minimal",
      description: "화면을 가리지 않는 작은 자막.",
      tag: "미니멀",
      karaoke: false,
      preview: { color: "#FFFFFF", stroke: "#000000", weight: "400" },
    },
    {
      id: "IMPACT_YELLOW",
      name: "Impact Yellow",
      description: "두꺼운 흰 글씨, 말하는 단어만 노란색. 요즘 쇼츠의 정석.",
      tag: "유행",
      karaoke: true,
      preview: { color: "#FFFFFF", stroke: "#000000", accent: "#FFE600", weight: "900" },
    },
    {
      id: "KARAOKE_POP",
      name: "Karaoke Pop",
      description: "검은 박스 위 흰 글씨, 말하는 단어만 형광색으로. 캡컷 스타일.",
      tag: "유행",
      karaoke: true,
      preview: { color: "#FFFFFF", background: "#111111", accent: "#D7FF4F", weight: "900" },
    },
    {
      id: "NEWS_BAR",
      name: "News Bar",
      description: "뉴스 하단 자막처럼 가로 띠 위에 또렷하게.",
      tag: "정보",
      karaoke: false,
      preview: { color: "#FFFFFF", background: "#202020", weight: "700" },
    },
    {
      id: "NEON_GLOW",
      name: "Neon Glow",
      description: "어두운 영상 위에 빛나는 네온 글씨.",
      tag: "감성",
      karaoke: false,
      preview: { color: "#4FE1FF", stroke: "#D74FFF", weight: "800", glow: "true" },
    },
    {
      id: "HANDWRITING",
      name: "Handwriting",
      description: "손글씨 느낌의 따뜻한 자막. 브이로그와 감성 영상에.",
      tag: "감성",
      karaoke: false,
      preview: { color: "#FFFFFF", stroke: "#303030", weight: "400", font: "cursive" },
    },
    {
      id: "TYPEWRITER",
      name: "Typewriter",
      description: "고정폭 글씨와 검은 박스. 설명·튜토리얼 영상에.",
      tag: "정보",
      karaoke: false,
      preview: { color: "#D7FF4F", background: "#000000", weight: "700", font: "monospace" },
    },
  ],
  layouts: [
    {
      id: "FILL",
      name: "가득 채우기",
      description: "화면을 꽉 채우고 양옆을 잘라냅니다. 인물 중심 영상에 좋아요.",
    },
    {
      id: "FIT",
      name: "원본 그대로",
      description:
        "원본 화면을 전부 보여 주고 위아래는 흐린 배경으로 채웁니다. 원본 자막이나 화면 구성이 잘리지 않아요.",
    },
  ],
};

export async function fetchRenderOptions(signal?: AbortSignal): Promise<RenderOptions> {
  const response = await fetch(`${API_URL}/templates`, { signal });
  if (!response.ok) throw new Error("템플릿 목록을 불러오지 못했습니다.");
  const payload = (await response.json()) as Partial<RenderOptions>;
  return {
    templates: payload.templates?.length ? payload.templates : DEFAULT_RENDER_OPTIONS.templates,
    layouts: payload.layouts?.length ? payload.layouts : DEFAULT_RENDER_OPTIONS.layouts,
  };
}

export function templateName(options: RenderOptions, id: string | null | undefined) {
  return options.templates.find((template) => template.id === id)?.name ?? id ?? "";
}
