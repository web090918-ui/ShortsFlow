# Task 13 — Frame layouts and caption templates

Added 2026-10-01 after the owner reported caption text being cut off and asked for
templates closer to what competitors (Opus, Klap, Vizard, CapCut) ship, "the more the
better", with the viewer's own video shown inside the template picker.

## Diagnosis of the cut-off text

The clipped line in the owner's screenshot was the **source video's own burned-in
subtitle**, not a caption we drew. The 9:16 conversion scales a 16:9 frame to cover
1080x1920 and center-crops it, so anything near the left or right edge of the source
(including wide subtitle lines) is removed. Our ASS captions wrap inside 90 px margins
and were never cut.

## Headline composition (same day, second pass)

The owner compared the first template set with FikaClip's showcase and asked for that
look instead: a **big two-line title with one coloured keyword** in the black band above
the video, the **whole source frame in the middle**, and a **small spoken caption** in
the band below. That is now the default (`STAGE` layout + `HEADLINE_YELLOW`).

- `title` (max 80 chars) is accepted on `POST /processing-jobs` (stored on the analysis
  job) and `POST /shorts`. Rendering a Top 3 candidate without a title falls back to the
  analysis title, then to the candidate's `hook_text` when it is 30 characters or
  shorter (a long sentence would wrap into a block). A manual range with no title has
  no headline.
- Keyword: a `[bracketed]` phrase if the user marked one, else the whole second line of a
  two-line title (the showcase look), else the longest word of a one-liner (titles
  with a single word get no colour). User line breaks are kept.
- The headline is an extra `Headline` style (NanumSquareRound 84, bold, outline or box)
  drawn on layer 2 for the whole clip, centred at y=328 for `STAGE`/`FIT` and overlaid at
  y=230 for `FILL`. Every template can draw it; `headline_accent` sets the keyword colour.
- The frontend has a "쇼츠 제목 (선택)" textarea above the pickers; the typed title shows
  up in every template card immediately.

## Frame layouts (`RenderLayout`)

| id | user-facing name | FFmpeg |
| --- | --- | --- |
| `STAGE` (default) | 제목 + 원본 | `scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black` |
| `FIT` | 원본 + 흐린 배경 | `split` → blurred, enlarged copy as background (`boxblur` at quarter size) + whole frame scaled to fit → `overlay` centred |
| `FILL` | 가득 채우기 | `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920` (the original MVP rule) |

Captions are burnt after the layout filter so 1080x1920 positions hold. In `STAGE` and
`FIT` the caption style is forced to bottom-centre with `MarginV 440`, which lands in the
band under a 1080x607 picture instead of covering it.

`layout_id` is carried like `template_id`: on `POST /processing-jobs` (stored on the
analysis job), on `POST /shorts` (manual range, or an override when rendering a
candidate; `null` keeps the analysis job's layout), and on every job response.

## Caption templates (`RenderTemplate`)

Listed in the picker, in this order:

| id | name | look | keyword colour |
| --- | --- | --- | --- |
| `HEADLINE_YELLOW` | 헤드라인 옐로 | small white caption, outlined | #FFD23F gold |
| `HEADLINE_RED` | 헤드라인 레드 | same | #E8352B |
| `HEADLINE_LIME` | 헤드라인 라임 | same | #C6F542 |
| `HEADLINE_SKY` | 헤드라인 뉴스 | caption on a dark box | #58C7F5 |
| `HEADLINE_BOX` | 헤드라인 박스 | headline itself on a dark box | #FFD23F |
| `IMPACT_YELLOW` | 임팩트 옐로 | heavy caption, spoken word yellow (karaoke) | #FFD23F |
| `KARAOKE_POP` | 카라오케 팝 | caption on a dark box, spoken word accent (karaoke) | #D7FF4F |
| `CLEAN_CAPTION` | 클린 | original white/outline | #FFD23F |
| `BOLD_HIGHLIGHT` | 볼드 박스 | original accent on box | #D7FF4F |
| `MINIMAL` | 미니멀 | original small caption | white |

`NEWS_BAR`, `NEON_GLOW`, `HANDWRITING`, and `TYPEWRITER` stay valid ids (`listed=False`)
so jobs that used them keep loading, but the picker no longer shows them; the owner
judged them dated next to the headline look.

All styles live in `backend/app/captions.py` (`TEMPLATE_STYLES`); the video code knows
nothing about templates. Product Shorts use the same styles for their spoken lines
(no headline).

### Karaoke (per-word highlight)

`TranscriptSegment.words` keeps word timings when the provider gives them:

- YouTube json3 captions: each `segs[]` entry's `tOffsetMs`; a word ends where the next
  starts (last word ends with the event).
- Whisper: `timestamp_granularities: ["segment", "word"]`; top-level `words` are assigned
  to the segment whose range contains their start.

`select_cues` clamps word timings to the clip, `_resolve_candidate` copies them into the
render input, and `build_ass` emits one Dialogue event per word for karaoke templates
(whole line visible, current word recoloured with `\1c`). Only the fill colour is
overridden mid-line: libass 0.17.3 renders `\3c`/`\bord` combinations inside a line as a
blurred halo over the default glyph, so boxes stay style-level (`BorderStyle 3`).
Without word timings a karaoke template falls back to whole-cue captions.

## Catalog endpoint

`GET /templates` → `{ "templates": [{id, name, description, tag, karaoke, preview}], "layouts": [{id, name, description}] }`.

The frontend keeps a built-in copy (`DEFAULT_RENDER_OPTIONS`) so pickers render
immediately and in tests; `RenderOptionsProvider` (in `layout.tsx`) replaces it with the
server list once loaded. Adding a template therefore means: add the enum value, add a
`CaptionStyle` with `preview` hints, and (optionally) mirror it in the frontend default.

## Picker with the viewer's own frame

`TemplatePicker` and `LayoutPicker` (`frontend/src/components/template-picker.tsx`) draw a
miniature 9:16 frame per card using the viewer's video: the YouTube thumbnail for URL
sources, a frame captured in the browser (`captureVideoFrame`, canvas) for uploads, and
the product image on `/affiliate`. The frame follows the selected layout (cover crop vs.
blurred background + contain) and the sample sentence is styled from the template's
`preview` hints, with the third word marked as "spoken" for karaoke templates.

## Validation

- `backend && pytest`: 178 passed (catalog, STAGE/FIT filters, headline event and
  keyword rule, karaoke events, json3/Whisper words, layout and title passthrough).
- Real FFmpeg in the backend image: a 1920x1080 test clip with its own bottom caption was
  rendered with every template in every layout, including headline titles with marked
  and auto-detected keywords; `STAGE`/`FIT` keep the source caption whole, `FILL` crops it
  as before. No libass font-fallback warnings.
- `frontend`: lint, 28 vitest tests (new `template-picker.test.tsx`, upload test asserts the
  captured frame appears in the previews), `next build`.

## Suggested title and description (same day, third pass)

The owner showed EasyCut's "제목과 설명도 간편하게 입력" step and asked for the same:
AI proposes a title and description per candidate and the user edits them before the
Short is made.

- `OpenAIRanker` now asks for `title` (headline of at most 30 characters, the key phrase
  in `[brackets]`, optional `\n` line break) and `description` (one or two sentences
  plus two or three hashtags) for every candidate; both are kept on `RankedCandidate`
  and so inside `result.ranking.items`. `HeuristicRanker` derives them from the hook.
- `POST /shorts` accepts `description` (max 500) next to `title` (max 100). For a
  candidate render the fallback order is: request → analysis title → AI suggestion →
  short hook (title) and request → AI suggestion (description). Both are stored in
  `render_input` and returned on the job, ready for the YouTube publish step (Task 12B).
- `/video`: a Top 3 card now says "이 구간 선택"; picking one opens a "제목과 설명" panel
  prefilled with the suggestions (counters 100 / 500), and "이 제목으로 쇼츠 만들기"
  sends the edited values. The title doubles as the on-video headline.

## Compositions, brand colour, caption position, languages (same day, fourth pass)

The owner compared the options screen with EasyCut's and asked for its template set
and controls. What changed:

- **Templates** are now compositions on a stage: `CAPTION_POP` (big caption, longest
  word in brand colour), `CAPTION_ACCENT` (karaoke: spoken word in brand colour),
  `DARK_MINIMAL` (no caption), `PAPER` (cream stage, dark text), `SNS_CARD` (white
  stage, tag pill, channel line, left-aligned title, hashtags from the description) and
  `COMMUNITY` (white stage, "오늘의 화제" band, "실시간 베스트" kicker). Every earlier id
  stays valid but unlisted. A channel line (YouTube channel or the signed-in creator's
  name) is drawn under the picture for the new templates.
- **Stage colour** comes from the template (`CaptionStyle.stage_color`) and is passed to
  the FFmpeg `pad` filter; over video (`FIT`/`FILL`) light-stage text falls back to
  white with a dark outline so it stays readable.
- **Brand colour** (`brand_color`, hex) replaces the fixed keyword colours: headline
  keyword, karaoke/pop word, pill and band. Swatches (레드, 코랄, 골드, 아쿠아 default,
  블루) plus a custom colour input; served in `GET /templates` as `brand_colors`.
- **Caption position** (`caption_position`: `BOTTOM` under the picture, `MIDDLE` over
  its centre) on analysis and render jobs; catalog in `caption_positions`.
- **Languages**: `transcript_language` accepts `auto` (Titan default caption track, then
  Whisper language detection) and `output_language` drives the AI's title, description
  and reasons per job (ranker `reason_language` override).
- **Aspect ratio**: only 9:16 renders; the picker shows 16:9/5:4/1:1/4:5 as 준비 중.
  Supporting them means generalising `SHORT_WIDTH/HEIGHT`, ASS PlayRes and the
  compositions; left for a later task.
- `/video` options panel: 언어 선택 card, horizontal template strip with live previews
  (brand colour, caption position, channel line, typed title), 영상 비율 chips, 브랜드
  컬러 swatches, 자막 위치 cards, then 화면 배치 and the rights checkbox.
- Checks: backend 181 `pytest`, frontend 30 `vitest`, lint and `next build`; all six
  compositions rendered with real FFmpeg (brand red/aqua, karaoke, middle caption,
  light stages) and inspected.
