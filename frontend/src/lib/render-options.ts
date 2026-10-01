import { API_URL } from "@/config";

/** Caption preset as the backend `GET /templates` describes it. */
export type CaptionTemplate = {
  id: string;
  name: string;
  description: string;
  tag: string;
  karaoke: boolean;
  preview: {
    /** Stage colour behind the picture (STAGE layout), hex. */
    stage?: string;
    /** "true" when a channel line is drawn under the picture. */
    channel?: string;
    /** Caption treatment: pop (longest word in brand), karaoke, plain, none. */
    caption?: string;
    color?: string;
    stroke?: string;
    background?: string;
    accent?: string;
    weight?: string;
    font?: string;
    glow?: string;
    headlineAccent?: string;
    headlineBox?: string;
    tagline?: string;
    headerBand?: string;
    kicker?: string;
  };
};

export type FrameLayout = {
  id: "STAGE" | "FIT" | "FILL";
  name: string;
  description: string;
};

export type CaptionPosition = {
  id: "BOTTOM" | "MIDDLE";
  name: string;
  description: string;
};

export type BrandSwatch = { id: string; name: string; hex: string };

export type RenderOptions = {
  templates: CaptionTemplate[];
  layouts: FrameLayout[];
  caption_positions: CaptionPosition[];
  brand_colors: BrandSwatch[];
  default_brand_color: string;
};

export const DEFAULT_TEMPLATE_ID = "CAPTION_ACCENT";
export const DEFAULT_LAYOUT_ID: FrameLayout["id"] = "STAGE";
export const DEFAULT_CAPTION_POSITION: CaptionPosition["id"] = "BOTTOM";
export const DEFAULT_BRAND_COLOR = "#4FE1E1";

/** Output sizes; only 9:16 Shorts render today, the rest are shown as planned. */
export const ASPECT_RATIOS: Array<{ id: string; available: boolean }> = [
  { id: "16:9", available: false },
  { id: "5:4", available: false },
  { id: "1:1", available: false },
  { id: "4:5", available: false },
  { id: "9:16", available: true },
];

export const SOURCE_LANGUAGES: Array<{ id: string; name: string }> = [
  { id: "auto", name: "자동 감지" },
  { id: "ko", name: "한국어" },
  { id: "en", name: "English" },
  { id: "ja", name: "日本語" },
];

export const OUTPUT_LANGUAGES: Array<{ id: string; name: string }> = [
  { id: "ko", name: "한국어" },
  { id: "en", name: "English" },
  { id: "ja", name: "日本語" },
];

function stage(
  id: string,
  name: string,
  description: string,
  tag: string,
  preview: CaptionTemplate["preview"],
  karaoke = false,
): CaptionTemplate {
  return {
    id,
    name,
    description,
    tag,
    karaoke,
    preview: { stage: "#000000", channel: "true", weight: "800", ...preview },
  };
}

/**
 * Built-in copy of the catalog so the pickers render before (or without) the
 * server answer. The server list wins once it arrives; keep ids in sync with
 * `backend/app/templates.py`.
 */
export const DEFAULT_RENDER_OPTIONS: RenderOptions = {
  templates: [
    stage("CAPTION_POP", "자막 팝형", "핵심 어절을 크고 리듬감 있게. 검은 배경에 제목과 큰 자막.", "자막", {
      caption: "pop",
      weight: "900",
    }),
    stage(
      "CAPTION_ACCENT",
      "자막 강조형",
      "말하는 어절만 브랜드 컬러로. 단어 타이밍을 따라 색이 바뀝니다.",
      "자막",
      { caption: "karaoke" },
      true,
    ),
    stage("DARK_MINIMAL", "다크 미니멀", "제목과 영상만. 자막 없이 깔끔하게.", "미니멀", { caption: "none" }),
    stage("PAPER", "페이퍼", "종이 느낌의 밝은 배경에 짙은 글씨. 차분한 정보 영상에.", "밝은 배경", {
      stage: "#F5F1E8",
      caption: "plain",
      color: "#222222",
    }),
    stage("SNS_CARD", "SNS 템플릿", "태그 말풍선, 채널명, 제목, 해시태그를 카드처럼. 흰 배경.", "카드", {
      stage: "#FFFFFF",
      caption: "plain",
      color: "#222222",
      tagline: "다시 보게 되는 순간",
    }),
    stage("COMMUNITY", "커뮤니티 템플릿", "‘오늘의 화제’ 헤더와 게시글 느낌의 제목. 흰 배경.", "카드", {
      stage: "#FFFFFF",
      caption: "plain",
      color: "#222222",
      headerBand: "오늘의 화제",
      kicker: "실시간 베스트",
    }),
  ],
  layouts: [
    {
      id: "STAGE",
      name: "제목 + 원본",
      description: "템플릿 배경 가운데에 원본 화면을 그대로 두고, 위에는 제목, 아래에는 자막을 넣습니다.",
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
  caption_positions: [
    {
      id: "BOTTOM",
      name: "하단",
      description: "원본 영상에 자막이 없을 때. 화면을 덜 가리며 내용을 안정적으로 전달해요.",
    },
    {
      id: "MIDDLE",
      name: "중앙",
      description: "짧은 대사·몰입형 장면. 간헐적 자막에 시선을 빠르게 모아줘요.",
    },
  ],
  brand_colors: [
    { id: "red", name: "레드", hex: "#FF4D4F" },
    { id: "coral", name: "코랄", hex: "#FF7A59" },
    { id: "gold", name: "골드", hex: "#FFD23F" },
    { id: "aqua", name: "아쿠아", hex: DEFAULT_BRAND_COLOR },
    { id: "blue", name: "블루", hex: "#3B82F6" },
  ],
  default_brand_color: DEFAULT_BRAND_COLOR,
};

export async function fetchRenderOptions(signal?: AbortSignal): Promise<RenderOptions> {
  const response = await fetch(`${API_URL}/templates`, { signal });
  if (!response.ok) throw new Error("템플릿 목록을 불러오지 못했습니다.");
  const payload = (await response.json()) as Partial<RenderOptions>;
  return {
    templates: payload.templates?.length ? payload.templates : DEFAULT_RENDER_OPTIONS.templates,
    layouts: payload.layouts?.length ? payload.layouts : DEFAULT_RENDER_OPTIONS.layouts,
    caption_positions: payload.caption_positions?.length
      ? payload.caption_positions
      : DEFAULT_RENDER_OPTIONS.caption_positions,
    brand_colors: payload.brand_colors?.length ? payload.brand_colors : DEFAULT_RENDER_OPTIONS.brand_colors,
    default_brand_color: payload.default_brand_color ?? DEFAULT_BRAND_COLOR,
  };
}

export function templateName(options: RenderOptions, id: string | null | undefined) {
  return options.templates.find((template) => template.id === id)?.name ?? id ?? "";
}

/** Light stages (paper, white) take dark text; the renderer applies the same rule. */
export function isLightColor(hex: string | undefined): boolean {
  if (!hex || !/^#[0-9a-f]{6}$/i.test(hex)) return false;
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return 0.299 * r + 0.587 * g + 0.114 * b > 160;
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
  return longestWord(title);
}

export function longestWord(text: string): string | null {
  const words = text.trim().split(/\s+/).filter((word) => word.length >= 2);
  if (words.length < 2) return null;
  return words.reduce((longest, word) => (word.length > longest.length ? word : longest), "");
}

export type HeadlineRun = { text: string; accent: boolean };

/** Text split into plain and accent runs around `keyword` (first occurrence). */
export function accentRuns(text: string, keyword: string | null): HeadlineRun[] {
  if (!keyword) return [{ text, accent: false }];
  const at = text.indexOf(keyword);
  if (at < 0) return [{ text, accent: false }];
  return [
    { text: text.slice(0, at), accent: false },
    { text: keyword, accent: true },
    { text: text.slice(at + keyword.length), accent: false },
  ].filter((run) => run.text.length > 0);
}

/** Title split into lines of plain and keyword runs for rendering with an accent colour. */
export function headlineLines(title: string): HeadlineRun[][] {
  const keyword = headlineKeyword(title);
  const lines = title
    .split("\n")
    .map((line) => line.replace(/[[\]]/g, "").trim().split(/\s+/).join(" "))
    .filter(Boolean);
  let remaining = keyword;
  return lines.map((line) => {
    if (!remaining || line.indexOf(remaining) < 0) return [{ text: line, accent: false }];
    const runs = accentRuns(line, remaining);
    remaining = null;
    return runs;
  });
}
