# Task 12A Google Sign-in and Work History

## Scope

Users sign in with Google, every Source and job they create is tagged with their account, and `/my` lists what they made. This is the prerequisite for publishing to a connected YouTube channel (Task 12B) and the first per-user cost boundary: with `SHORTSFLOW_AUTH_MODE=google`, every creation endpoint requires a session.

```text
browser  GET /api/auth/google/start?next=/video        (Next.js rewrites /api/* to Cloud Run)
  -> 302 accounts.google.com (openid email profile, signed state carries `next`)
  -> GET /api/auth/google/callback?code&state
       API exchanges the code, verifies the ID token, upserts users/{id}, sets the
       HttpOnly `sf_session` cookie, 302 back to `next`
browser  GET /api/auth/status -> {auth_required, login_available, user}
         GET /api/me/jobs    -> this account's analyses and Shorts, newest first
```

## Design

- **Same-origin API.** `next.config.ts` rewrites `/api/:path*` to `API_PROXY_TARGET` (the Cloud Run URL in production, `http://localhost:8000` locally) and `API_URL` defaults to `/api`, so the session cookie is first-party and never depends on third-party cookie rules. The old absolute `NEXT_PUBLIC_API_URL` is only for tests.
- **Session.** An HMAC-signed compact token (`SessionSigner`) with a 30-day expiry in an HttpOnly, `SameSite=Lax` cookie, `Secure` when the public origin is https. No server-side session store.
- **Users.** `users` collection (Firestore on Cloud Run, memory locally): id, Google `sub`, email, name, picture, created and last-login times. Lookup by `sub` on every login, so re-login reuses the record.
- **Ownership.** `Source.user_id` (present since Task 02) is now set, and `ProcessingJob.user_id` was added. `GET /me/jobs` filters by `user_id` with an equality query and sorts in memory (no composite index), returning render jobs as `ShortJobResponse` and analysis jobs as a summary (status, range, candidate count, Top 3 hooks).
- **Modes.** `auth_mode=disabled` (default, local development and tests): no login, creation open, `/auth/status` reports `auth_required=false`. `auth_mode=google`: login enforced on `POST /sources`, `POST /sources/upload`, `POST /processing-jobs`, `POST /shorts`, `POST /shorts/product`; reads by job id stay open so result links remain shareable.
- **Frontend.** `AuthMenu` in the navigation (Google 로그인 / 내 작업 / 로그아웃), `LoginGate` around both wizards (sign-in card when required), `/my` with `MyWorks` (RenderResult for Shorts, summary cards for analyses).

## Configuration

```text
SHORTSFLOW_AUTH_MODE=google
SHORTSFLOW_GOOGLE_OAUTH_CLIENT_ID=<web client id>
SHORTSFLOW_GOOGLE_OAUTH_CLIENT_SECRET=<Secret Manager>
SHORTSFLOW_SESSION_SECRET=<Secret Manager, 32+ random bytes>
SHORTSFLOW_APP_PUBLIC_ORIGIN=https://www.cutpick.com
SHORTSFLOW_API_PUBLIC_PREFIX=/api
```

Vercel: `API_PROXY_TARGET=https://shortflow-268642207702.asia-northeast3.run.app` (replaces `NEXT_PUBLIC_API_URL`, which should be removed), then redeploy.

Google Cloud console (project `aza-ceo`): OAuth consent screen (External, Testing, owner as test user), Web application OAuth client with authorized redirect URIs `https://www.cutpick.com/api/auth/google/callback` and `http://localhost:3000/api/auth/google/callback`.

## Validation

1. Unit tests: signer round trip and expiry, start redirect with signed state, callback upsert and cookie, same-account re-login reuse, cancelled and tampered callbacks, enforcement of login on creation in google mode, `/me/jobs` isolation between two accounts; frontend LoginGate states.
2. On Cloud Run with `auth_mode=google`: sign in on www.cutpick.com, create a Short, see it under "내 작업", sign out, and confirm creation returns 401 without a session.

## Validation result

Implemented on 2026-10-01 (backend 148 tests, frontend 21 tests).

Cloud Run configuration completed on 2026-10-01: `/auth/status` on the service and through `https://www.cutpick.com/api/auth/status` (Vercel `API_PROXY_TARGET` applied) returns `auth_required=true, login_available=true`; `POST /sources` without a session returns `401`; `/auth/google/start` redirects to `accounts.google.com` with the `https://www.cutpick.com/api/auth/google/callback` redirect URI and the configured client id. The first deploy attempt failed because the shell split the command and the revision started in google mode without secrets; the code now logs and fails closed instead of exiting (commit "keep serving when Google sign-in is misconfigured").

Browser check (sign in on www.cutpick.com, create a Short, see it under 내 작업, sign out) is performed by the owner and recorded here once done.
