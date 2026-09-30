# Competitor Research — URL-to-Shorts Pipeline

## Purpose and evidence rules

This document records competitor behavior observed or documented on 2026-09-27 (FikaClip added 2026-09-30) while investigating a production-safe YouTube acquisition path for ShortsFlow. It is product and architecture research, not permission to copy private implementations or add features outside the MVP1 backlog.

Evidence is classified as follows:

- **Confirmed**: visible in a public product flow, public network response, generated artifact, or official competitor documentation.
- **Inference**: strongly suggested by the confirmed behavior but not directly disclosed.
- **Unknown**: cannot be established from public behavior or documentation.

No account email, user ID, session ID, job ID, short ID, signed URL, cookie, authorization header, or signature is retained in this repository.

## Market pattern

The reviewed products expose a URL-first experience but separate URL submission from long-running acquisition, analysis, and rendering.

```text
Web application
-> source analysis
-> asynchronous import/processing job
-> media acquisition boundary
-> stored/normalized source media
-> transcript and candidate analysis
-> render worker
-> object storage and CDN
-> preview/download
```

They also provide one or more alternate source paths such as local upload, Google Drive, Dropbox, Vimeo, or a public MP4 URL. A URL-first UI therefore does not imply that the web runtime downloads and processes media inside the initiating request.

## Competitor documentation review

### EasyCut

- Accepts YouTube links and local file uploads.
- Its FAQ limits link processing to public content the user uploaded or is authorized to use, and excludes private, paid, age-restricted, and DRM-protected content.
- The public web application is served by Vercel, but this does not establish where acquisition or rendering runs.

References:

- <https://www.easycut.co.kr/faq>
- <https://www.easycut.co.kr/ai-shorts-maker>
- <https://www.easycut.co.kr/pricing>

### OpusClip

- Accepts YouTube and many other platform URLs, public MP4 URLs, and local uploads.
- Its public API creates a clipping project from a `videoUrl` and supports completion notification through a webhook or email.
- Local uploads use a resumable Google Cloud Storage upload before project creation.
- Public or unlisted links are supported; private videos are not accessible.

References:

- <https://help.opus.pro/docs/article/video-sources-supported>
- <https://help.opus.pro/api-reference/endpoints/create-project>
- <https://help.opus.pro/api-reference/endpoints/upload-video-create-project>

### Klap

- Markets direct URL import from YouTube and other platforms so the user does not need to download and re-upload the source manually.
- Also supports file and non-YouTube source paths.
- Does not publicly disclose its YouTube acquisition implementation.

References:

- <https://klap.app/tools/youtube-clip-maker>
- <https://klap.app/tools/video-to-shorts-converter>
- <https://klap.app/privacy-policy>

### Vizard

- Supports link and local-file ingestion.
- States that customer video is stored on AWS, uses encrypted temporary links, and applies retention/deletion rules.
- Does not publicly disclose its YouTube acquisition implementation.

References:

- <https://help.vizard.ai/en/articles/8768883-why-do-my-videos-have-a-lower-resolution-after-exporting>
- <https://help.vizard.ai/en/articles/9629134-vizard-and-data-safety>

### 2short.ai

- Accepts YouTube URLs and provides a file/public-source alternative on paid plans.
- Requires captions for its YouTube clipping workflow, indicating that caption availability is an early analysis gate.
- Caption-first analysis does not by itself explain how renderable source media is acquired.

Reference:

- <https://www.2short.ai/>

### FikaClip (fikad.boo)

Added 2026-09-30 from the public landing page only; no documentation, API, or network observation was reviewed.

- Korean-market URL-to-Shorts product: "내 영상을 클릭 한 번에 바이럴 숏폼으로 만들어보세요." The flow is three steps: paste a link, let the AI produce short-form clips, then publish to YouTube, TikTok, and Instagram at once.
- **Confirmed (marketing claims)**: highlight detection tuned to the first 10 seconds, context analysis of tone, timing, and emotional arc, AI motion captions with style recommendations, trend-based template learning, automatic reframe by subject type, silence removal, TTS voices, thumbnail generation, multiple aspect ratios, and automatic English subtitles for global distribution. Claims 370,000,000 cumulative views, 700,000 generated Shorts, and a 3x average view increase for users. A free trial ("무료체험") is offered.
- **Inference**: like the other products it separates link submission from long-running processing and renders on a server; the publishing step implies channel connection (an MVP2/MVP3 concern for ShortsFlow).
- **Unknown**: pricing and credit model, how YouTube media is acquired, upload and file limits, private or unlisted link handling, and whether the ranking is generic or channel-personalized.
- **Implication for ShortsFlow**: FikaClip bundles most of the features that the MVP1 exclusions list defers (auto reframe, TTS, multi-platform publishing, trend templates). It confirms the market expects the caption template step (Task 08) and a Top-N recommendation with reasons (Task 07), and it is the closest Korean-language reference for caption styling and copy. It does not change the MVP1 order.

References:

- <https://fikad.boo/>

## EasyCut black-box observation

### Test scope

The same public test video used in Task 03A (`qdck91pAwB4`) was submitted through EasyCut. A four-minute source range was selected from a source whose reported full duration was 9,481 seconds.

This test established competitor behavior only. It did not reveal EasyCut credentials, backend source code, or the mechanism used to pass YouTube's bot challenge.

### Source analysis

**Confirmed:** Before job creation, EasyCut returned the source title, channel, thumbnail, and full duration, then allowed selection of a processing range.

**Confirmed:** The range UI uses a dual-handle timeline plus explicit start and end fields. Its visible guidance permits a range from 4 to 60 minutes. The selected duration is shown as the amount that will be deducted. In an observed 16-minute-9-second source with 16 minutes of allowance remaining, the UI selected `00:00-16:00` and displayed a 16-minute deduction rather than selecting the final nine seconds beyond the available allowance.

This establishes that the selected range is both the analysis scope and the usage-accounting unit. It does not by itself prove whether the acquisition worker downloads only that byte/time range or downloads a larger source artifact before trimming.

Metadata success alone is not evidence of usable media acquisition because metadata can be obtained independently of video/audio stream bytes.

### Async job API

**Confirmed:** Job creation returned HTTP `202 Accepted`. The browser then repeatedly requested a route shaped like `GET /api/jobs/{job_id}`. Those API responses were served by Vercel and returned JSON status.

Observed job fields included:

```text
id
status
stage
progress
sourceDurationSeconds
expectedShortCount
plannedShortCount
readyShortCount
failedShortCount
renderSuccessPercent
wordTimedSubtitlesAvailable
errorMessage
createdAt
expiresAt
shorts
```

**Confirmed:** During processing, the job reported `status=downloading` and `stage=downloading`. Progress advanced while the browser continued polling.

**Inference:** Vercel handles the web/API control plane while a separate execution environment performs acquisition and media processing. The browser flow does not disclose that worker's exact topology or network identity.

EasyCut's public privacy policy narrows this inference further. Its subprocessors table assigns web hosting and request handling to Vercel, while assigning video processing, temporary job storage, and result storage/delivery to Amazon Web Services and AWS Korea in the Seoul region. The same policy says the selected source-video segment, extracted audio, and intermediate transcript are stored during the job and deleted when processing ends; editable clips, completed videos, thumbnails, and subtitle ranges are retained according to the plan for up to 30 days.

No dedicated media-acquisition vendor such as Klap or OpusClip appears in the published subprocessors list. This is strong evidence that EasyCut operates its own video-processing pipeline on AWS rather than delegating the complete job to one of those products. It is not conclusive proof that every acquisition request is made by EasyCut-owned downloader code: a provider that does not receive covered personal data, an omitted/changed subprocessor, or another undisclosed implementation remains technically possible.

### Usage reservation

**Confirmed:** The selected four-minute range reserved 240 seconds when the job started. While processing, usage showed zero committed seconds and 240 reserved seconds. On successful completion it showed 240 committed seconds, zero reserved seconds, and 960 seconds remaining from a 1,200-second trial allowance.

This demonstrates a reserve-then-commit usage model and billing by selected source duration rather than full source duration.

### Transcript availability

**Confirmed:** `wordTimedSubtitlesAvailable` changed from false to true while the job still reported the downloading stage. The final shorts contained timestamped subtitle segments.

**Inference:** Caption/transcript availability is detected or acquired independently of completion of the main video download. The observation does not distinguish YouTube captions, a separate audio path, or STT.

### Completion and acquisition result

**Confirmed:** The job completed successfully for the same video that received a bot challenge from the ShortsFlow provider on Vercel and AWS Lightsail. It produced three playable vertical MP4 results from the selected range. End-to-end processing took no more than approximately seven minutes in the observed run.

This proves that EasyCut has a viable acquisition path for this specific input. It does not establish how reliable that path is across videos, accounts, regions, or time.

### Candidate and ranking result

The job planned five outputs but completed three ready shorts with zero render failures and a 100% render success rate.

| Result | Source range | Duration | Internal score | Selection behavior |
| --- | ---: | ---: | ---: | --- |
| 1 | 137-215 seconds | 78 seconds | 81 | AI-selected candidate |
| 2 | 40-115 seconds | 75 seconds | 77 | AI-selected candidate |
| 3 | 0-45 seconds | 45 seconds | none | Evenly placed fallback because AI selection was unavailable |

**Confirmed:** Candidate records separate raw selection boundaries from final render boundaries and include an adjustment reason, repositioning flag, score, hook title, and recommendation reason.

Representative fields:

```text
selectionRawStartSeconds
selectionRawEndSeconds
selectionRawDurationSeconds
selectionCandidateIndex
selectionLengthAdjustment
selectionRepositioned
startSeconds
endSeconds
durationSeconds
viralScore
hookTitle
highlightReason
```

**Confirmed:** The third result explicitly disclosed that it was a time-distributed fallback because AI could not be used. EasyCut therefore favors returning an output even when it cannot produce enough scored recommendations.

### Render specification

**Confirmed:** Ready shorts contained a declarative render snapshot with:

- a 1080 by 1920 canvas;
- 30 frames per second;
- ordered video, title, comment, and channel layers;
- frame-based overlay intervals;
- font identity, file, weight, and hash;
- template and render versions;
- clip-level expiration and rerender state.

The tested template added 11-15 comment-style overlays per result.

**Inference:** The comment text, generated-looking nicknames, like counts, and evenly scheduled intervals strongly suggest synthetic comment overlays. ShortsFlow must not treat this inference as permission to implement them, and they are outside the MVP1 backlog.

**Inference:** A deterministic render worker consumes the serialized composition. The evidence does not identify whether it uses FFmpeg, a browser renderer, Remotion, or another engine.

**Confirmed:** EasyCut's privacy policy states that its AI processing does not perform speaker biometric identification or face recognition. Generic claims that EasyCut necessarily uses YOLO, MediaPipe, or face recognition for automatic reframing are therefore unsupported by the reviewed evidence.

### Result delivery

**Confirmed:** Preview used a completed MP4 rather than HLS. The video and JPEG poster were served from CloudFront signed URLs. Object paths were versioned and had the following conceptual form:

```text
outputs/{opaque-owner}/{job}/{short}/v1.mp4
thumbnails/{opaque-owner}/{job}/{short}.jpg
```

The observed result record expired after one day for the free account. The observed CloudFront URL expired about 20 minutes after issuance. This separates object retention from short-lived delivery authorization.

The signed URL used CloudFront `Expires`, `Key-Pair-Id`, and `Signature` parameters. The HTML attribute `controlslist=nodownload` only hides a browser control and is not access control.

**Inference:** The application stores an object key or equivalent stable artifact reference and issues a new signed URL for preview/download. CloudFront is confirmed, but its origin cannot be proven to be S3 from the browser response alone.

### Pricing and operational limits

The observed public account-state response exposed these current plan characteristics:

| Plan | Source processing per month | Retention | Max active jobs | Monthly price |
| --- | ---: | ---: | ---: | ---: |
| Plus | 100 minutes | 7 days | 1 | KRW 9,900 |
| Standard | 200 minutes | 15 days | 2 | KRW 19,900 |
| Pro | 600 minutes | 30 days | 3 | KRW 49,900 |

**Confirmed:** EasyCut differentiates paid plans using processed source minutes, artifact retention, and job concurrency. Historical/package plan records also appeared in the state response but are not relevant to the ShortsFlow MVP architecture.

## What remains unknown

None of the reviewed evidence establishes whether EasyCut or another competitor uses:

- yt-dlp or a proprietary extractor;
- browser cookies or managed YouTube accounts;
- PO tokens;
- residential, ISP, or rotating proxy infrastructure;
- a third-party acquisition vendor;
- a direct commercial or written approval arrangement with YouTube;
- full-source download or selected-range acquisition.

The presence of a Vercel frontend/API does not mean YouTube media is downloaded from Vercel. A successful competitor run also does not make an undocumented acquisition technique compliant or suitable for ShortsFlow.

## YouTube policy constraint

YouTube's API developer policies state that API clients must not download, import, back up, cache, or store YouTube audiovisual content without YouTube's prior written approval. User confirmation of copyright ownership and compliance with YouTube platform terms are separate concerns.

References:

- <https://developers.google.com/youtube/terms/developer-policies>
- <https://developers.google.com/youtube/terms/api-services-terms-of-service>

## Product and architecture implications for ShortsFlow

### Adopt when the matching backlog task begins

- Keep the Vercel/web API control plane separate from long-running media execution.
- Model explicit job status, stage, progress, counters, and actionable error details.
- Poll initially or expose another simple progress mechanism; do not hold the submission request open.
- Preserve both suggested candidate boundaries and final adjusted render boundaries.
- Store a generic score, hook, and concise recommendation reason for ranked candidates.
- Separate candidate-generation failure from render failure.
- Do not force a low-quality fallback into Top 3 merely to reach a fixed count. Two qualified recommendations are better than two qualified recommendations plus an unscored filler.
- Store stable artifact keys, not signed URLs; issue short-lived preview/download URLs.
- Separate delivery URL TTL from artifact retention.
- Version render outputs so a rerender does not overwrite the previous artifact unexpectedly.

### Do not add to MVP1 now

- synthetic comment overlays;
- an advanced template or timeline editor;
- complex font and frame-level editing controls;
- billing, quota reservation, or plan entitlements before required;
- a proxy fleet, cookie vault, account farm, or token service without an explicit security, policy, and maintenance decision.

## Acquisition decision

Task 03A remains a negative production validation for the existing yt-dlp provider: the current approach worked from a local residential network but failed from Vercel and AWS Lightsail. A separate external acquisition experiment on 2026-09-27 successfully returned metadata and a playable selected 480p range through Tunelio.

The validated Tunelio request consumed 16 credits: 6 for `/info` and 10 for `/create`; downloading the signed tunnel URL consumed no additional credits. The current published Pro plan provides 100,000 monthly credits for USD 9, which is 6,250 complete info-and-create operations before retries or duplicate calls. These prices are provider claims and can change, so ShortsFlow must cache Source metadata, prevent duplicate creation calls, track failures, and retain a replaceable provider boundary. Tunelio is an independent provider and the current public terms do not provide a production SLA.

References:

- <https://tunelio.dev/docs/>
- <https://tunelio.dev/terms/>

Before Task 04, choose and validate one acquisition contract:

1. a licensed/compliant media acquisition provider;
2. a user-supplied source file or authorized cloud object, with the YouTube URL used for metadata;
3. a separately approved authentication/token approach following policy, security, and operational review.

Before production launch, the selected external contract still needs repeated multi-video reliability checks, expiry/error handling, cost monitoring, and legal review. A black-box competitor success is evidence that the product experience is possible, not evidence that its undisclosed implementation can or should be copied.
