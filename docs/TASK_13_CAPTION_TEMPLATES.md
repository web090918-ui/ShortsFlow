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

## Frame layouts (`RenderLayout`)

| id | user-facing name | FFmpeg |
| --- | --- | --- |
| `FILL` (default) | 가득 채우기 | `scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920` (unchanged) |
| `FIT` | 원본 그대로 | `split` → blurred, enlarged copy as background (`boxblur` at quarter size) + whole frame scaled to fit (`force_original_aspect_ratio=decrease`) → `overlay` centred |

Captions are burnt after the layout filter so 1080x1920 positions hold. In `FIT` the
caption style is forced to bottom-centre with `MarginV 440`, which lands in the blurred
band under a 1080x607 picture instead of covering it.

`layout_id` is carried like `template_id`: on `POST /processing-jobs` (stored on the
analysis job), on `POST /shorts` (manual range, or an override when rendering a
candidate; `null` keeps the analysis job's layout), and on every job response.

## Caption templates (`RenderTemplate`)

| id | style | font | notes |
| --- | --- | --- | --- |
| `CLEAN_CAPTION` | white, black outline | NanumGothic | original |
| `BOLD_HIGHLIGHT` | accent on black box | NanumGothic | original |
| `MINIMAL` | small white | NanumGothic | original |
| `IMPACT_YELLOW` | heavy white, spoken word yellow, middle of frame | NanumSquareRound | karaoke |
| `KARAOKE_POP` | white on a dark box, spoken word in accent | NanumSquareRound | karaoke |
| `NEWS_BAR` | white on a wide dark bar | NanumBarunGothic | |
| `NEON_GLOW` | cyan with magenta glow (`\blur6`) | NanumSquare | |
| `HANDWRITING` | pen-style | Nanum Pen Script (`fonts-nanum-extra`) | |
| `TYPEWRITER` | monospace accent on black box | NanumGothicCoding | |

All styles live in `backend/app/captions.py` (`TEMPLATE_STYLES`); the video code knows
nothing about templates. Product Shorts use the same styles for their spoken lines.

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

- `backend && pytest`: 167 passed (catalog, FIT filter, karaoke events, json3/Whisper
  words, layout passthrough).
- Real FFmpeg in the backend image: a 1920x1080 test clip with its own bottom caption was
  rendered with every new template in both layouts; `FIT` keeps the source caption whole,
  `FILL` crops it as before. No libass font-fallback warnings.
- `frontend`: lint, 28 vitest tests (new `template-picker.test.tsx`, upload test asserts the
  captured frame appears in the previews), `next build`.
