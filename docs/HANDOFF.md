# Handoff (2026-10-01, evening)

Where the project stands, what is waiting on the owner, and what comes next. Read this first when continuing from another machine.

## State

- `main` is the only branch; every change is pushed. Cloud Run (`shortflow`, asia-northeast3) redeploys the backend from `main` via Cloud Build; Vercel redeploys the frontend at www.cutpick.com.
- Tasks 01-09, 05B, and 11 are complete and validated on Cloud Run. Task 10 (Coupang Partners product Shorts) is implemented and locally verified with real FFmpeg; its Cloud Run run (OpenAI TTS `gpt-4o-mini-tts`, angle generation) has not been exercised yet.
- Pages: `/` intro with two entry cards, `/video` (YouTube URL or upload → range → AI Score Top 3 or "이 구간 그대로 만들기" → preview/download), `/affiliate` (Coupang Partners link → product facts → three angles → narrated Short; Agoda and Trip.com marked 준비 중). A landing/workspace redesign landed in commit `54c4291`.
- Caption templates and frame layouts (Task 13, 2026-10-01): the default Short is now the headline composition seen on FikaClip-style showcases (big title with a coloured keyword above the whole source frame on black, small caption below: `STAGE` layout + `HEADLINE_*` templates), plus two karaoke templates with per-word highlight from json3/Whisper word timings and `FIT` (blurred background) and `FILL` (crop) layouts. An optional `title` rides on analysis and render jobs; `[brackets]` mark the keyword. `GET /templates` serves the catalog; the picker shows each style on the viewer's own frame with the typed title. See [Task 13](TASK_13_CAPTION_TEMPLATES.md).
- Options (2026-10-01, later): templates are now six stage compositions (자막 팝형, 자막 강조형, 다크 미니멀, 페이퍼, SNS, 커뮤니티) with a brand colour, caption position (하단/중앙), 영상 언어 자동 감지 and 제작 언어; AI suggests an editable title and description per Top 3 clip. 9:16 only; other ratios shown as planned.
- 글·사진으로 만들기 (Task 14, 2026-10-01): typed title/price/description plus up to three pictures (upload or URL) become a READY product Source; AI suggests angles, title and description; product Shorts render on the same stage templates with brand colour and a picture slideshow. The Coupang link is now a shortcut inside that flow. See [Task 14](TASK_14_TEXT_PHOTO_SHORTS.md).
- Member workspace (2026-10-01, owner's commits `dd32db6`…`20d7bc0` plus follow-ups): `/my` is a light-themed workspace with a sidebar (내 프로젝트 / 영상 쇼츠 만들기 / 글·사진으로 만들기), a red 크레딧 button in the top bar, and the studios rendered inside it at `/my/video` and `/my/affiliate`. 내 프로젝트 groups work per source video (`GET /me/projects`, `/my/{source_id}`). Credit charging rules live in 계정 · 제작 설정; the balance carries a "?" tooltip with what it can make.
- Picking a clip (2026-10-01): each Top 3 card shows a miniature of the finished Short in the chosen template/brand colour (upload: a frame captured at the clip start; YouTube: a muted player paused at that second), the AI title/description, hook, reason and tags. Starting any render opens a layer popup: it keeps going on the server; the file is in 내 프로젝트.
- Tests at the last run: backend 190 (`pytest`, run in the backend Docker image because this machine has no Python), frontend 44 (`vitest`), lint and `next build` clean. Last commit `4e14f1e`.

## Waiting on the owner (no code change needed)

1. ~~Vercel `API_PROXY_TARGET`~~ done 2026-10-01: `https://www.cutpick.com/api/*` proxies to Cloud Run. Delete or disable the retired `shortsflow-api.vercel.app` project when convenient.
1b. ~~Login (Task 12A) on Cloud Run~~ done 2026-10-01: `auth_mode=google`, OAuth client, and both secrets are live; `/auth/status` reports login available. Owner's browser check (sign in → create → 내 작업 → sign out) still to be recorded in [Task 12A](TASK_12A_LOGIN.md).
2. **Bucket CORS** for browser uploads on `/video`: `gcloud storage buckets update gs://shortsflow-shorts-aza-ceo --cors-file=cors.json` with the rule in [Task 11](TASK_11_UPLOAD.md).
3. **OpenAI model access** for Task 10: if `/affiliate` rendering fails with HTTP 403, allow `gpt-4o-mini-tts` (and keep `gpt-4.1-mini`) in project `proj_InkVn5EtOT2q8LKO2v8bFE9X`. Ranking uses the same project via `SHORTSFLOW_OPENAI_PROJECT`.
4. **Cloud Run settings** can return to defaults now that acquisition is resumable: `SHORTSFLOW_PROCESSING_LEASE_SECONDS=600`, `SHORTSFLOW_APIFY_RUN_TIMEOUT_SECONDS=480`, `--timeout=900`; keep `SHORTSFLOW_APIFY_TITAN_QUALITY=720`.
5. **For Task 12A (Google login)**: OAuth consent screen (External, Testing, owner as test user), a Web OAuth client with redirect URIs `https://www.cutpick.com/api/auth/google/callback` and `http://localhost:3000/api/auth/google/callback`, client id and secret in Secret Manager, YouTube Data API v3 enabled for 12B.

## Credits (added 2026-10-01)

1 credit = 1 source minute analysed; signup grant 30 once per account; analysis 1 per minute, manual Short 1 per clip minute, candidate render 0, product Short 5; charged at creation, refunded once on final failure, 402 when short. Competitor research, cost drivers, pack and subscription proposals, and the payment-provider plan (Toss Payments or PortOne first, Stripe later) are in [CREDITS_PRICING.md](CREDITS_PRICING.md). Payments themselves are not implemented; the ledger already has a `purchase` reason for the webhook to use.

## Agreed next order

1. **Owner checks after today's deploys**: on `/my/video`, run one YouTube analysis end to end (Top 3 cards with scene previews → 제목과 설명 → render → layer popup → 내 프로젝트). On `/my/affiliate`, make one 글·사진 Short with 1–2 uploaded pictures (needs bucket CORS, item 2 above) and watch for a TTS 403 (item 3 above). Report any template card that looks off by name.
2. Task 12B — connect the creator's YouTube channel (incremental `youtube.upload` consent) and publish a finished Short with the stored title/description (affiliate link and disclosure) and privacy; test users only until Google verification. Jobs already carry `title` and `description` for this.
3. Agoda / Trip.com: partner API keys → providers behind `ProductSourceProvider` that pre-fill the 글·사진 form (public pages return 403 or a JS shell; reviews are not available anywhere, creators paste them into 설명/메모).
4. Later: server-side start frames for YouTube candidates (needs the media, so only when it is already cached), other aspect ratios (generalise 1080x1920 and the compositions), payments (ledger `purchase` reason).

## Where things are (for the next machine)

- Templates/compositions: `backend/app/captions.py` (`TEMPLATE_STYLES`, `build_ass`, `build_product_ass`), `backend/app/templates.py` (enums), `backend/app/render_options.py` (`GET /templates`); frontend mirror in `frontend/src/lib/render-options.ts`, pickers in `frontend/src/components/template-picker.tsx`.
- Video wizard: `frontend/src/components/source-input.tsx`; Top 3 scene preview `candidate-scene.tsx`; popup `background-notice.tsx`.
- 글·사진: `backend/app/products.py` (`ManualProductInput`), `backend/app/sources.py` (`POST /sources/product`, `/sources/product-images`), `backend/app/product_pipeline.py`, `video_processing.compose_product_short`; frontend `affiliate-input.tsx`, `product-studio.tsx`.
- Workspace: `frontend/src/components/member-workspace.tsx` (+ `.module.css`), `my-projects.tsx`, routes under `frontend/src/app/my/`; backend `backend/app/me.py`.
- Scratch render checks used today (FFmpeg frames per template) are not in the repo; recreate with a 4-second `testsrc2` clip and `build_ass` if needed.
- An untracked `output/` folder exists in the owner's checkout; it is not part of the repo.

## Operating notes

- Apify Titan is the only YouTube provider; Tunelio is gone. Long videos are acquired asynchronously: the job is re-queued and re-delivered every minute while Titan works, and the source link is cached per video for 23 hours in Firestore `source_media`.
- Titan is slow for long sources (a 27-minute video took over 20 minutes) and billed per byte plus compute; the cache prevents repeat downloads. Apify free credit stood at about $5 of $10 on 2026-09-30.
- Rendered Shorts and uploads live in `gs://shortsflow-shorts-aza-ceo` under `shorts/` and `uploads/`, deleted after one day by lifecycle; signed download links last 24 hours and the API reports `artifact_state` so the UI shows expired or removed files correctly.
- Validation commands are in the README; on a machine without Python, run pytest inside the backend image with `backend/app` and `backend/tests` mounted.
