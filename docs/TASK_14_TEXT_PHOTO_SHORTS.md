# Task 14 — 글·사진으로 만들기 (text + photos → narrated Short)

Added 2026-10-01. The affiliate flow depended on reading a product link, which only
works for Coupang Partners link-generation URLs (coupang.com and agoda.com product
pages return a 403 or a JavaScript shell to servers). The owner decided to make
**typed facts + pictures** the primary input and keep the link as a shortcut that
pre-fills the same facts. The menu entry is "글·사진으로 만들기 — 정보·이야기·사진을
짧은 영상으로".

## Input

- `POST /sources/product` (JSON `ManualProductInput`): `title` (required), `sales_price`,
  `origin_price` (discount rate is derived), `description` (free text, up to 1000 chars;
  short sentences become facts for the AI), `image_urls` (1–3, https or `upload://`),
  `product_url`, `provider_label`. Returns a READY `PRODUCT` Source with
  `metadata.product` (`provider: "manual"`).
- `POST /sources/product-images` registers a picture (JPG/PNG/WEBP ≤ 15MB) and returns an
  `upload://uploads/img-{id}.ext` URL plus a signed PUT (Cloud Storage) or a direct
  `PUT /sources/product-images/{id}/content` target (local). The Source creation refuses
  `upload://` pictures that are not in storage yet (409).
- `ProductFacts` gained `image_urls` and `description`; `all_image_urls` lists every
  picture with the lead first. The Partners provider fills `image_urls=[image_url]`.

## AI suggestions

`ProductContent` carries `title` (headline, ≤30 chars, key phrase in `[brackets]`) and
`description` (one or two sentences + hashtags) next to the three angles. The OpenAI
prompt asks for them; the template generator derives them from the facts
(`suggest_title`, `suggest_description`). The creator's `description` text is passed to
the model as context. `/affiliate` shows them in an editable "제목과 설명" panel; the
edited values ride on `POST /shorts/product` (`title`, `description`) together with
`brand_color` and `caption_position`.

## Rendering — same templates as video Shorts

Product Shorts now use the composition templates and the brand colour. `build_product_ass`
draws on the template's stage: headline band (0..330, keyword in brand colour), picture
box 330..1230, price badge in brand colour under the picture, spoken captions in the
template's caption style (pop / karaoke / plain / none, 하단 or 중앙 for caption
templates), CTA and the disclosure pinned at the bottom. `compose_product_short` takes a
list of pictures: each fills a 1080x900 box for an equal share of the clip with a slow
zoom, the segments are concatenated and padded onto the stage colour, then the ASS is
burnt and the narration mixed in. Uploaded pictures are fetched through
`ArtifactStorage.fetch_to`; https pictures through `download_to_file`.

Verified with real FFmpeg in the backend image (two pictures, 자막 팝형 and SNS 템플릿
stages, gold and aqua brand colours).

## Frontend

`AffiliateInput` has two modes: **직접 입력** (default: title, prices, description, up to
three pictures via file upload or https URL, optional link) and **어필리에이트 링크**
(the Coupang Partners parser as before). `ProductStudio` shows the AI title/description
panel, the full template strip with the product picture as the sample, brand colour
swatches, caption position for caption templates, and a rights/terms checkbox whose text
depends on the provider. The in-workspace route is `/my/affiliate`.

## Checks

- backend `pytest`: 190 passed (manual facts, picture upload + Source via API, content
  suggestions, multi-picture pipeline with storage fetch, product ASS on light stage).
- frontend: lint, 43 vitest tests (manual mode upload flow, validation), `next build`.

## Not done

- Agoda / Trip.com partner APIs (keys needed); they will pre-fill the same form.
- Reviews are not fetched anywhere; the creator pastes them into 설명 or 메모.
- 9:16 only.
