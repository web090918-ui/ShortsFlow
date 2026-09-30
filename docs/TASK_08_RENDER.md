# Task 08 Preview and Render

## Scope

Task 08 closes the AI path of the MVP1 promise: the user inspects the Top 3 from Task 07, picks one, and receives a 1080x1920 MP4 with the previously chosen caption template burned in, previewable in the browser and downloadable. It reuses the Task 05B render pipeline end to end; the only new video work is caption burning. No timeline editing, no face tracking or auto reframe, no B-roll.

```text
Top 3 card -> "이 구간으로 쇼츠 만들기"
  -> POST /shorts { processing_job_id, candidate_id, rights_confirmed }
       server resolves URL, candidate range, template, and caption cues from the analysis job
  -> SHORT_RENDER job (Task 04 queue + Worker)
       Titan acquire -> ASS captions for the clip -> FFmpeg trim + 9:16 + subtitles -> storage
  -> GET /shorts/{id}: preview_url (inline) + download_url (attachment)
  -> <video> preview and download button
```

## Captions

- Cues are the Task 05 transcript segments overlapping the candidate, with sound tags (`[음악]`) and speaker marks (`>>`) removed. Fragments shorter than 0.3 seconds after clamping are dropped.
- `app/captions.py` writes an ASS file whose times are relative to the clip start. `PlayResX/Y` is 1080x1920, so positions match the cropped frame.
- The three templates are ASS styles only, using the bundled NanumGothic font:

| Template | Look |
| --- | --- |
| `CLEAN_CAPTION` | 64 px bold white, black outline, lower third |
| `BOLD_HIGHLIGHT` | 80 px bold accent (#D7FF4F) on a dark box, mid-lower |
| `MINIMAL` | 48 px regular white, thin outline, near the bottom |

- FFmpeg burns the file with `subtitles=filename=...` after the scale and crop in the same encode pass (`FfmpegVideoProcessor.trim_to_vertical(..., subtitles_path=...)`). The container installs `ffmpeg fonts-nanum fontconfig` so libass can shape Korean text.
- A render without captions (the manual path, or a candidate with no overlapping cues) behaves exactly as before.

## API additions

`POST /shorts` accepts either the manual body (`youtube_url`, `start_seconds`, `end_seconds`) or a candidate body (`processing_job_id`, `candidate_id`); mixing them is a `422`. For a candidate the server takes the source URL, range, and template from the completed analysis job (`409` if it is not completed, `404` for an unknown candidate) and stores the caption cues on the job's `render_input`.

`ShortJobResponse` gains `preview_url`, `candidate_id`, `processing_job_id`, and `captions_applied`. `GET /shorts/{id}/file?inline=true` serves the MP4 with an inline disposition for the `<video>` element; on Cloud Storage that is a second V4 signed URL with `response_disposition=inline` and `response_type=video/mp4`.

`result.short` on the job records `template_id`, `captions_applied`, and `preview_url` next to the existing fields.

## Frontend

The Source panel is now the AI path: Source → analysis range, video language, template, rights → "AI 추천 구간 찾기" → step-labelled progress (자막·음성 분석, 후보 구간, AI Score) → Top 3 cards with `AI Score`, time range, hook, reason, and strengths → "이 구간으로 쇼츠 만들기" → render progress → inline `<video>` preview and "쇼츠 다운로드". The 480p analysis download button was removed from the UI; its endpoint remains for development. The manual-range panel (Task 05B) is unchanged and stays first on the page.

## Validation

Task 08 is complete when:

1. Unit tests cover cue selection and clamping, clip-relative ASS timing, per-template styles, the FFmpeg filter order and path escaping, caption pass-through in the pipeline, candidate-based job creation with cue filtering, and the inline file response.
2. Real FFmpeg in the container renders Korean captions for all three templates (visual frame check).
3. A Cloud Run render from a ranked candidate completes with `captions_applied > 0`, a working `preview_url` and `download_url`, and a 1080x1920 MP4 whose duration matches the candidate.
4. The deployed page shows the Top 3 with `AI Score` and plays the finished Short inline.

## Validation result

Implemented on 2026-09-30. Unit tests: 100 backend, 11 frontend. Check 2 passed locally in the backend image: a 1920x1080 synthetic source rendered to 1080x1920 for all three templates and exported frames showed correctly shaped Korean text with the expected box and outline styles. Check 4 passed on 2026-09-30: www.cutpick.com serves the AI panel, and the analysis job on the authorized 27-minute Korean source `ZY-kQtE0WFE` (0-900 seconds, `BOLD_HIGHLIGHT`) completed with a Top 3 led by the 4.2-63.7 second candidate (AI Score 82).

Check 3 failed on 2026-09-30 for a long source: render job `1019cc5a` for that candidate used all three attempts and ended `SOURCE_DOWNLOAD_FAILED` with "영상 확보 작업 시간이 초과되었습니다." Each attempt spent the full 480-second Titan run timeout in `downloading`; Titan needs longer than that to deliver a 27-minute 1080p file, and the Worker lease and Cloud Tasks dispatch deadline were fixed at 600 seconds, so no attempt could wait longer. The caption path itself was not reached. The 19-second test source rendered in about a minute, so the limit is source length, not the pipeline.

Fix applied in code: the lease is now `SHORTSFLOW_PROCESSING_LEASE_SECONDS` (default 600) and drives both the Firestore claim and the Cloud Tasks dispatch deadline. For long sources raise it together with the Titan run timeout and the Cloud Run request timeout, for example `SHORTSFLOW_PROCESSING_LEASE_SECONDS=1500`, `SHORTSFLOW_APIFY_RUN_TIMEOUT_SECONDS=1200`, `--timeout=1800`, and optionally `SHORTSFLOW_APIFY_TITAN_QUALITY=720` to shrink the download. Check 3 remains pending until a long-source render completes with captions.
