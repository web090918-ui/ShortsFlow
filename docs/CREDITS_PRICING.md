# Credits and Pricing

Decided 2026-10-01 after comparing six URL-to-Shorts products. Numbers for competitors come from their public pricing pages on that date and can change.

## What competitors do

| Product | Free | Unit | Paid (monthly) | Notes |
| --- | --- | --- | --- | --- |
| Vizard | 60 credits per month, 720p, watermark, 3-day storage | 1 credit = 1 minute of uploaded video | Creator and Business tiers from 7,200 credits per year, 4K, no watermark | Recurring monthly free allowance |
| 2short.ai | 30 minutes of AI analysis per month, exports included | minutes of source analysed | Lite $9.90 (5 h), Pro $19.90 (15 h), Premium $49.90 (50 h) | 1080p, no watermark on all plans |
| OpusClip | Free plan: spoken-word clipping only, 3-day media expiry, watermark on templates | credits (conversion not published) | Starter $15, Pro $29, Business custom | Pro adds B-roll, dubbing, scheduler |
| Klap | no free plan shown | clips generated per month | Basic $14 (100 clips), Pro $39 (300), Pro+ $94 (1,000), billed yearly | Only competitor that bills per clip |
| EasyCut (KR) | none | minutes of source processed per month | ₩9,900 (60 min), ₩19,900 (200 min), ₩48,000 (600 min); 6-month discounts | about ₩165 per source minute at the entry tier |
| FikaClip (KR) | 500 credits once at signup | credits by source length: ≤5 min 50C, 5–30 min 100C, 30–60 min 200C | Lite ₩5,500, Creator ₩7,900, Pro ₩20,000 (annual discounts) | Extra features cost credits (title regen 2C, music 50C); one-time purchases exist beside subscriptions |

Two patterns matter. Almost everyone bills by **source minutes analysed**, not by clip, because source length drives their cost too. Korean products give either **no free tier** (EasyCut) or a **one-time signup grant** (FikaClip), while global products give a **recurring monthly free allowance** (Vizard, 2short).

## Our cost drivers (per job, approximate)

| Step | Driver | Rough cost |
| --- | --- | --- |
| Source acquisition (Titan) | per byte plus Apify compute; long videos take 20+ minutes of actor time | ₩3–₩700 per video, once per 23 hours thanks to the source cache |
| Captions (Titan) | per item | about ₩3 |
| Whisper fallback / uploads | per source minute | about ₩8 per minute |
| AI ranking (gpt-4.1-mini) | per analysis | under ₩10 |
| Product narration (gpt-4o-mini-tts) | per second of speech | about ₩20 per Short |
| FFmpeg render on Cloud Run | instance minutes | about ₩15–₩30 per Short |

Source length is the dominant variable for YouTube and uploads, which is why the credit unit follows it. Product Shorts have no source length; their cost is fixed (TTS plus LLM plus render).

## Policy (defaults in `backend/app/config.py`, all adjustable)

- **Unit**: 1 credit = 1 minute of source video analysed, rounded up per job.
- **Signup grant**: 30 credits once per Google account (`credit_signup_grant`). Enough for two or three real analyses, in line with 2short's monthly 30 minutes and FikaClip's one-time grant. No recurring free allowance yet; add `credit_monthly_grant` later if activation data asks for it.
- **Charges**
  - AI analysis (transcript, candidates, ranking): 1 credit per source minute of the selected range (`credit_analysis_per_minute`). A 15-minute range costs 15.
  - Rendering a recommended candidate from a completed analysis: 0 (`credit_candidate_render`). The analysis already paid; exports being included matches 2short and Vizard.
  - "이 구간 그대로 만들기" (manual range, no analysis): 1 credit per clip minute, so 1–3 credits (`credit_manual_short_per_minute`).
  - Product Short (Coupang Partners): 5 credits (`credit_product_short`), roughly a 5-minute analysis, covering TTS and LLM. Angle generation itself is free.
- **When**: charged at job creation, before anything runs. Re-queues while Titan works and Cloud Tasks retries never charge again.
- **Refunds**: automatic, once, when a job ends `FAILED` for good (non-retryable error or the last attempt). Expired download links do not refund; re-rendering a candidate is free anyway.
- **Insufficient balance**: `402 Payment Required` with "크레딧이 부족합니다 (필요 N, 보유 M)". Nothing is created.
- **Development**: with `SHORTSFLOW_AUTH_MODE=disabled` there is no user and nothing is charged.

## Payments (next step, not implemented)

- **Provider**: Toss Payments for Korea (cards, 간편결제, virtual accounts) or PortOne as an aggregator; Stripe later for non-Korean customers. Each needs a registered business (사업자등록) and a PG contract.
- **Products**: start with one-time credit packs, which fit a one-time signup grant and avoid subscription churn logic; add subscriptions with a monthly credit top-up once usage is predictable. Suggested packs, VAT included, priced near EasyCut's ₩165 per minute with room for the free grant: 100 credits ₩9,900, 300 credits ₩24,900, 1,000 credits ₩69,000. Suggested subscriptions later: Starter ₩9,900 for 100 credits per month, Pro ₩29,000 for 400 credits per month, unused credits roll over one month.
- **Ledger integration**: a `payments` collection keyed by the provider's payment id; the webhook verifies amount and currency against the pack catalog server-side, then writes one `purchase` ledger entry. Idempotency on the payment id prevents double grants on webhook retries.
- **Legal**: show prices VAT-inclusive, issue receipts, and publish a refund policy that honours the 7-day withdrawal right for unused credits under the Korean e-commerce act; used credits are non-refundable except for job failures, which the ledger already refunds.
- **Abuse**: the signup grant is per Google account; add a per-IP or per-device signup rate limit before marketing, and consider holding the grant until email is verified by Google (it is, for Google accounts).

## Open decisions for the owner

1. Keep the free grant one-time (current) or add a small monthly allowance (for example 10 credits) to bring users back.
2. Whether a long-source surcharge is needed: a 60-minute analysis costs 60 credits but Titan may spend ₩500+ of actor time on it; the cache makes the second analysis of the same video cheap, so the default is no surcharge.
3. Pack prices above are placeholders until the PG contract and tax setup are known.
