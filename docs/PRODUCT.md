# ShortsFlow Product Definition

## Product position

ShortsFlow helps a user turn one source into a recommended, rendered, downloadable Short. MVP1 validates the shortest useful journey: `URL or upload -> Short`.

ShortsFlow is not intended to remain a generic bulk Shorts generator. Later phases will use channel context and performance feedback to improve what creators choose to make. That long-term direction must not make MVP1 harder to ship.

## MVP1 goal: Create

MVP1 starts without Channel DNA or YouTube Analytics. A user should be able to provide one of the following sources:

1. YouTube video URL
2. Affiliate or product URL
3. Video file upload

The first delivery target is the complete YouTube flow. The Product/Affiliate flow is part of MVP1, but it is implemented only after the YouTube flow works end-to-end. Upload shares the common Source model and follows the video-processing path when scheduled by the backlog.

## YouTube flow

```text
YouTube URL
-> Source creation
-> Video information
-> Transcript
-> 10-15 clip candidates
-> Generic AI Ranking
-> Top 3 Recommendation
-> Candidate selection
-> 9:16 Short Render
-> Preview
-> Download
```

## Product/Affiliate flow

```text
Product URL
-> Source creation
-> Product information extraction
-> Selling-point analysis
-> 3 content angles
-> Hook + Script + CTA
-> Product image/video + TTS + Caption
-> Short Render
-> Preview
-> Download
```

Affiliate support in MVP1 creates content from a product source. Affiliate conversion tracking is explicitly excluded.

## Ranking in MVP1

MVP1 uses Generic AI Ranking, not Personal Virality Score. Ranking may consider:

- Hook strength
- Context completeness
- Information density
- Emotional or curiosity potential
- Shorts duration suitability
- Standalone understandability

User-facing labels should use `AI Score` or `Recommended Score`.

The output is a ranked set of candidates with three recommendations. The user remains responsible for choosing which candidate to render.

## Product phases

### MVP1 — Create

Turn a supported source into a rendered Short that can be previewed and downloaded.

### MVP2 — Personalize

```text
Channel Connect
-> Channel DNA
-> Personal Ranking
```

### MVP3 — Learn

```text
Publish
-> Measure
-> Learn
-> Better Recommendation
```

## MVP1 exclusions

- Channel DNA
- YouTube Analytics
- Personal Virality Score
- Automatic publishing
- Published-performance collection
- Instagram
- TikTok
- Competitor-channel analysis
- Trend Discovery
- AI Avatar
- Voice Clone
- Advanced Timeline Editor
- Advanced Auto Reframe
- AI B-roll
- Affiliate Conversion Tracking
- Kubernetes
- Kafka
- Redis
- Microservices

## Delivery principle

The product must validate one complete flow before broadening its feature set. Development therefore completes YouTube URL to preview and download before Product/Affiliate implementation. Future expansion should remain possible, but no later-phase behavior is implemented speculatively.

