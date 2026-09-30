# Task 09 Download UX

## Scope

Task 09 finishes the YouTube URL to downloadable Short acceptance path. Rendering (Task 08) already returned a download link; this task makes the download action explicit and gives every artifact state a useful screen instead of a broken link.

## Artifact states

`GET /shorts/{id}` returns `artifact_state`, computed on the server on every read:

| State | Meaning | Server rule | UI |
| --- | --- | --- | --- |
| `pending` | still rendering | job not `COMPLETED` or `FAILED` | stage label and progress |
| `ready` | downloadable | completed, link not expired, object still in storage | inline `<video>` preview, "쇼츠 다운로드 (MP4)" with the `download` attribute, "…까지 다운로드할 수 있습니다" |
| `expired` | signed link TTL passed | `result.short.expires_at <= now` | "다운로드 링크 만료" and "다시 만들기" |
| `unavailable` | object removed | `ArtifactStorage.exists(key)` is false (bucket lifecycle deletes after one day) | "파일 보관 기간 종료" and "다시 만들기" |
| `failed` | render failed | job `FAILED` | error message and "다시 시도" |

When the state is not `ready`, `download_url` and `preview_url` are `null`, so the client never renders a link that would 404. `GET /shorts/{id}/file` returns `410` with a distinct message for expired and removed artifacts, `409` while rendering.

The frontend re-evaluates expiry every 30 seconds from `download_expires_at`, so a page left open flips to the expired screen on its own.

## Retry

- Manual panel: "다시 시도" and "다시 만들기" re-post the last URL and range.
- AI panel: they re-post the last `processing_job_id` and `candidate_id`, so the same ranked candidate is rendered again with the same template.
- Because source media is cached per video (Task 08), a re-render of an expired Short usually skips Titan and finishes in about a minute.

`ArtifactStorage.exists(key)` was added to the storage boundary (`LocalArtifactStorage` checks the file, `GcsArtifactStorage` checks the blob); the API reads it through `ShortPipeline.storage`.

## End-to-end acceptance (YouTube URL to downloadable Short)

Both MVP1 paths were exercised on Cloud Run against the deployed site:

| Path | Date | Evidence |
| --- | --- | --- |
| Manual range (Task 05B) | 2026-09-29 | job `cc2ddd7e`, 19-second public source, range 2-12 s, `apify_titan` + `gcs`, signed URL 200, 1080x1920, 10.00 s, byte-identical via the API redirect |
| AI Top 3 (Tasks 05-08) | 2026-09-30 | analysis `c52cfd36` (15 candidates, AI Score Top 3) then render `3171148c` of the Top 1 candidate from a 27-minute Korean source, `BOLD_HIGHLIGHT`, 26 captions, preview inline 200, download `cutpick-short-4-64.mp4` 34.2 MB, 1080x1920, 59.45 s, frames checked |

Task 09 adds the state handling on top; the Cloud Run check for this task is that a completed render reports `artifact_state=ready` with a working link, and that the API reports `expired` or `unavailable` correctly once the link or object is gone.

## Validation

1. Unit tests cover `ready`, `expired`, `unavailable`, `failed`, and `pending` on the API, the `410` messages, and the frontend screens for each state including client-side expiry and retry callbacks.
2. On Cloud Run a completed render reports `artifact_state=ready` and the link downloads; after the bucket lifecycle removes the object the same job reports `unavailable`.

## Validation result

Implemented on 2026-09-30 (backend 114 tests, frontend 16 tests).

Cloud Run check on 2026-09-30, about three minutes after the revision went live, using existing render jobs:

| Job | Storage | Result |
| --- | --- | --- |
| `3171148c` (Top 1 candidate, rendered 01:54 UTC) | GCS | `artifact_state=ready`, `download_expires_at=2026-10-01T01:54Z`, download and preview URLs present, `/file` → `307` to the signed URL |
| `cc2ddd7e` (manual range, rendered 2026-09-29 07:08 UTC) | GCS | `ready` with `download_expires_at=2026-09-30T07:08Z`; still inside its 24-hour window at check time, so the link is correctly kept until then |
| `03dfc541` (rendered before Cloud Storage was configured) | local disk of a since-replaced instance | `artifact_state=unavailable`, links `null`, `/file` → `410` "쇼츠 영상이 보관 기간이 지나 삭제되었습니다. 다시 만들어 주세요." |

The `expired` branch is covered by unit tests on both sides and will apply to `cc2ddd7e` after 07:08 UTC; the bucket lifecycle rule then removes the object a day after upload, at which point the same job reports `unavailable`.

Task 09 is complete. The MVP1 YouTube path (URL → transcript → candidates → AI Score Top 3 → captioned 9:16 render → preview → download, plus the manual-range shortcut) is delivered end to end. Task 10 (Product/Affiliate flow) may begin.
