# Handoff (2026-09-30)

Where the project stands, what is waiting on the owner, and what comes next. Read this first when continuing from another machine.

## State

- `main` is the only branch; every change is pushed. Cloud Run (`shortflow`, asia-northeast3) redeploys the backend from `main` via Cloud Build; Vercel redeploys the frontend at www.cutpick.com.
- Tasks 01-09, 05B, and 11 are complete and validated on Cloud Run. Task 10 (Coupang Partners product Shorts) is implemented and locally verified with real FFmpeg; its Cloud Run run (OpenAI TTS `gpt-4o-mini-tts`, angle generation) has not been exercised yet.
- Pages: `/` intro with two entry cards, `/video` (YouTube URL or upload → range → AI Score Top 3 or "이 구간 그대로 만들기" → preview/download), `/affiliate` (Coupang Partners link → product facts → three angles → narrated Short; Agoda and Trip.com marked 준비 중). A landing/workspace redesign landed in commit `54c4291`.
- Tests at the last run: backend 141 (`pytest`, run in the backend Docker image because this machine has no Python), frontend 18 (`vitest`), lint and `next build` clean.

## Waiting on the owner (no code change needed)

1. **Vercel `NEXT_PUBLIC_API_URL`** must be `https://shortflow-268642207702.asia-northeast3.run.app` for Production, then redeploy. The live bundle still calls the retired `shortsflow-api.vercel.app`, which is why the site shows "YouTube가 현재 서버 요청을 제한했습니다". Delete or disable that old Vercel backend project afterwards.
2. **Bucket CORS** for browser uploads on `/video`: `gcloud storage buckets update gs://shortsflow-shorts-aza-ceo --cors-file=cors.json` with the rule in [Task 11](TASK_11_UPLOAD.md).
3. **OpenAI model access** for Task 10: if `/affiliate` rendering fails with HTTP 403, allow `gpt-4o-mini-tts` (and keep `gpt-4.1-mini`) in project `proj_InkVn5EtOT2q8LKO2v8bFE9X`. Ranking uses the same project via `SHORTSFLOW_OPENAI_PROJECT`.
4. **Cloud Run settings** can return to defaults now that acquisition is resumable: `SHORTSFLOW_PROCESSING_LEASE_SECONDS=600`, `SHORTSFLOW_APIFY_RUN_TIMEOUT_SECONDS=480`, `--timeout=900`; keep `SHORTSFLOW_APIFY_TITAN_QUALITY=720`.
5. **For Task 12A (Google login)**: OAuth consent screen (External, Testing, owner as test user), a Web OAuth client with redirect URIs `https://www.cutpick.com/api/auth/google/callback` and `http://localhost:3000/api/auth/google/callback`, client id and secret in Secret Manager, YouTube Data API v3 enabled for 12B.

## Agreed next order

1. Task 12A — Google sign-in, session cookie, `user_id` on Sources and jobs, "내 작업" list, creation endpoints require login.
2. Task 12B — connect the creator's YouTube channel (incremental `youtube.upload` consent) and publish a finished Short with title, description (affiliate link and disclosure), and privacy; test users only until Google verification.
3. Task 10 Cloud Run validation (angles and TTS) once model access is confirmed; then Agoda and Trip.com providers behind `ProductSourceProvider` (their public pages are expected to block servers like Coupang's, so plan on partner links or APIs).

## Operating notes

- Apify Titan is the only YouTube provider; Tunelio is gone. Long videos are acquired asynchronously: the job is re-queued and re-delivered every minute while Titan works, and the source link is cached per video for 23 hours in Firestore `source_media`.
- Titan is slow for long sources (a 27-minute video took over 20 minutes) and billed per byte plus compute; the cache prevents repeat downloads. Apify free credit stood at about $5 of $10 on 2026-09-30.
- Rendered Shorts and uploads live in `gs://shortsflow-shorts-aza-ceo` under `shorts/` and `uploads/`, deleted after one day by lifecycle; signed download links last 24 hours and the API reports `artifact_state` so the UI shows expired or removed files correctly.
- Validation commands are in the README; on a machine without Python, run pytest inside the backend image with `backend/app` and `backend/tests` mounted.
