# Handoff (2026-10-01)

Where the project stands, what is waiting on the owner, and what comes next. Read this first when continuing from another machine.

## State

- `main` is the only branch; every change is pushed. Cloud Run (`shortflow`, asia-northeast3) redeploys the backend from `main` via Cloud Build; Vercel redeploys the frontend at www.cutpick.com.
- Tasks 01-09, 05B, and 11 are complete and validated on Cloud Run. Task 10 (Coupang Partners product Shorts) is implemented and locally verified with real FFmpeg; its Cloud Run run (OpenAI TTS `gpt-4o-mini-tts`, angle generation) has not been exercised yet.
- Pages: `/` intro with two entry cards, `/video` (YouTube URL or upload → range → AI Score Top 3 or "이 구간 그대로 만들기" → preview/download), `/affiliate` (Coupang Partners link → product facts → three angles → narrated Short; Agoda and Trip.com marked 준비 중). A landing/workspace redesign landed in commit `54c4291`.
- Caption templates and frame layouts (Task 13, 2026-10-01): the default Short is now the headline composition seen on FikaClip-style showcases (big title with a coloured keyword above the whole source frame on black, small caption below: `STAGE` layout + `HEADLINE_*` templates), plus two karaoke templates with per-word highlight from json3/Whisper word timings and `FIT` (blurred background) and `FILL` (crop) layouts. An optional `title` rides on analysis and render jobs; `[brackets]` mark the keyword. `GET /templates` serves the catalog; the picker shows each style on the viewer's own frame with the typed title. See [Task 13](TASK_13_CAPTION_TEMPLATES.md).
- Tests at the last run: backend 174 (`pytest`, run in the backend Docker image because this machine has no Python), frontend 28 (`vitest`), lint and `next build` clean.

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

1. Task 12A — implemented 2026-10-01 (Google sign-in, session cookie, `user_id` on Sources and jobs, `/my` work history, login enforced in google mode); production check pending the OAuth client.
2. Task 12B — connect the creator's YouTube channel (incremental `youtube.upload` consent) and publish a finished Short with title, description (affiliate link and disclosure), and privacy; test users only until Google verification.
3. Task 10 Cloud Run validation (angles and TTS) once model access is confirmed; then Agoda and Trip.com providers behind `ProductSourceProvider` (their public pages are expected to block servers like Coupang's, so plan on partner links or APIs).

## Operating notes

- Apify Titan is the only YouTube provider; Tunelio is gone. Long videos are acquired asynchronously: the job is re-queued and re-delivered every minute while Titan works, and the source link is cached per video for 23 hours in Firestore `source_media`.
- Titan is slow for long sources (a 27-minute video took over 20 minutes) and billed per byte plus compute; the cache prevents repeat downloads. Apify free credit stood at about $5 of $10 on 2026-09-30.
- Rendered Shorts and uploads live in `gs://shortsflow-shorts-aza-ceo` under `shorts/` and `uploads/`, deleted after one day by lifecycle; signed download links last 24 hours and the API reports `artifact_state` so the UI shows expired or removed files correctly.
- Validation commands are in the README; on a machine without Python, run pytest inside the backend image with `backend/app` and `backend/tests` mounted.
