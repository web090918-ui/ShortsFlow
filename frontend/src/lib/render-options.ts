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
    headlineAccent?: string;
    headlineBox?: string;
  };
};

export type FrameLayout = {
  id: "STAGE" | "FIT" | "FILL";
  name: string;
  description: string;
};

export type RenderOptions = {
  templates: CaptionTemplate[];
  layouts: FrameLayout[];
};

export const DEFAULT_TEMPLATE_ID = "HEADLINE_YELLOW";
export const DEFAULT_LAYOUT_ID: FrameLayout["id"] = "STAGE";

function headline(
  id: string,
  name: string,
  description: string,
  headlineAccent: string,
  extra: Partial<CaptionTemplate["preview"]> = {},
): CaptionTemplate {
  return {
    id,
    name,
    description,
    tag: "요즘 감성",
    karaoke: false,
    preview: { color: "#FFFFFF", stroke: "#000000", weight: "800", headlineAccent, headlineBox: "false", ...extra },
  };
}

/**
 * Built-in copy of the catalog so the pickers render before (or without) the
 * server answer. The server list wins once it arrives; keep ids in sync with
 * `backend/app/templates.py`.
 */
export const DEFAULT_RENDER_OPTIONS: RenderOptions = {
  templates: [
    headline("HEADLINE_YELLOW", "헤드라인 옐로", "큰 제목에 노란 키워드, 아래에 작은 자막. 요즘 쇼츠의 기본형.", "#FFD23F"),
    headline("HEADLINE_RED", "헤드라인 레드", "빨간 키워드로 긴장감을 주는 제목. 다큐·이슈 영상에.", "#E8352B"),
    headline("HEADLINE_LIME", "헤드라인 라임", "연두 키워드. 정보·꿀팁 영상에 잘 맞아요.", "#C6F542"),
    headline("HEADLINE_SKY", "헤드라인 뉴스", "하늘색 키워드와 박스 자막. 뉴스·시사 느낌.", "#58C7F5", {
      background: "#000000",
    }),
    headline("HEADLINE_BOX", "헤드라인 박스", "제목을 검은 박스 위에 얹어 어떤 배경에서도 또렷하게.", "#FFD23F", {
      headlineBox: "true",
    }),
    {
      id: "IMPACT_YELLOW",
      name: "임팩트 옐로",
      description: "두꺼운 자막, 말하는 단어만 노란색으로 바뀌어요.",
      tag: "단어 강조",
      karaoke: true,
      preview: { color: "#FFFFFF", stroke: "#000000", accent: "#FFD23F", weight: "900", headlineAccent: "#FFD23F" },
    },
    {
      id: "KARAOKE_POP",
      name: "카라오케 팝",
      description: "검은 박스 위 흰 글씨, 말하는 단어만 형광색으로.",
      tag: "단어 강조",
      karaoke: true,
      preview: { color: "#FFFFFF", background: "#111111", accent: "#D7FF4F", weight: "900", headlineAccent: "#D7FF4F" },
    },
    {
      id: "CLEAN_CAPTION",
      name: "클린",
      description: "읽기 쉬운 기본 자막. 흰 글씨에 검은 외곽선.",
      tag: "기본",
      karaoke: false,
      preview: { color: "#FFFFFF", stroke: "#000000", weight: "700", headlineAccent: "#FFD23F" },
    },
    {
      id: "BOLD_HIGHLIGHT",
      name: "볼드 박스",
      description: "형광 글씨를 검은 박스 위에. 핵심 문장을 강하게.",
      tag: "기본",
      karaoke: false,
      preview: { color: "#D7FF4F", background: "#111111", weight: "800", headlineAccent: "#D7FF4F" },
    },
    {
      id: "MINIMAL",
      name: "미니멀",
      description: "화면을 가리지 않는 작은 자막.",
      tag: "기본",
      karaoke: false,
      preview: { color: "#FFFFFF", stroke: "#000000", weight: "400", headlineAccent: "#FFFFFF" },
    },
  ],
  layouts: [
    {
      id: "STAGE",
      name: "제목 + 원본",
      description: "검은 배경 가운데에 원본 화면을 그대로 두고, 위에는 제목, 아래에는 자막을 넣습니다.",
    },
    {
      id: "FIT",
      name: "원본 + 흐린 배경",
      description: "원본 화면을 전부 보여 주고 위아래는 흐린 배경으로 채웁니다.",
    },
    {
      id: "FILL",
      name: "가득 채우기",
      description: "화면을 꽉 채우고 양옆을 잘라냅니다. 인물 중심 영상에 좋아요.",
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

/**
 * Same rule as the backend: a `[bracketed]` phrase is the coloured part; otherwise the
 * whole second line of a two-line title; otherwise the longest word of a one-liner.
 */
export function headlineKeyword(title: string): string | null {
  const marked = /\[([^[\]]+)\]/.exec(title);
  if (marked) return marked[1].trim() || null;
  const lines = title
    .split("\n")
    .map((line) => line.trim().split(/\s+/).join(" "))
    .filter(Boolean);
  if (lines.length >= 2) return lines[1];
  const words = title.trim().split(/\s+/).filter((word) => word.length >= 2);
  if (words.length < 2) return null;
  return words.reduce((longest, word) => (word.length > longest.length ? word : longest), "");
}

export type HeadlineRun = { text: string; accent: boolean };

/** Title split into lines of plain and keyword runs for rendering with an accent colour. */
export function headlineLines(title: string): HeadlineRun[][] {
  const keyword = headlineKeyword(title);
  const lines = title
    .split("\n")
    .map((line) => line.replace(/[[\]]/g, "").trim().split(/\s+/).join(" "))
    .filter(Boolean);
  let remaining = keyword;
  return lines.map((line) => {
    if (!remaining) return [{ text: line, accent: false }];
    const at = line.indexOf(remaining);
    if (at < 0) return [{ text: line, accent: false }];
    const runs = [
      { text: line.slice(0, at), accent: false },
      { text: remaining, accent: true },
      { text: line.slice(at + remaining.length), accent: false },
    ].filter((run) => run.text.length > 0);
    remaining = null;
    return runs;
  });
}
