# Task 03A — Dedicated YouTube Acquisition Worker Validation

## Goal

Validate that the existing YouTube provider can run outside Vercel and produce media references that downstream processing can actually read. This is an environment validation task, not Task 04 async job implementation.

## Pass criteria

A candidate worker environment passes only when all of the following are true:

1. The provider resolves the expected video ID, title, and duration.
2. It selects separate usable video and audio formats.
3. A range request can read bytes from both selected streams using the provider headers.
4. The report does not expose direct stream URLs or request headers.
5. The same public, authorized test video succeeds three consecutive times.

Metadata extraction by itself is not a pass. Direct stream URLs can be returned yet remain unusable because of a PO-token, IP, or expiry restriction.

## Probe command

From `backend/`:

```powershell
.\.venv\Scripts\python.exe -m app.acquisition_probe "https://www.youtube.com/watch?v=VIDEO_ID"
```

In the backend container:

```text
python -m app.acquisition_probe "https://www.youtube.com/watch?v=VIDEO_ID"
```

The probe reads up to 64 KiB for an HLS manifest and at most 1 KiB of media payload. It follows nested HLS playlists until it verifies bytes from the first media segment. It does not download the full video and never prints the private processing reference.

## Environment matrix

| Environment | Result | Evidence |
| --- | --- | --- |
| Local development machine | Passed, 2026-09-27 | Three consecutive runs resolved `qdck91pAwB4`; video format `614` reached an HLS media segment with HTTP 200 and audio format `140-drc` returned HTTP 206. Runs completed in 2.096-2.188 seconds. |
| Vercel Python Function | Failed | YouTube returned a bot challenge for the shared cloud egress IP even with the JavaScript challenge runtime available. |
| AWS Lightsail dedicated worker | Failed, 2026-09-27 | A 2 GB Ubuntu instance in Seoul (`ap-northeast-2`) returned YouTube's `Sign in to confirm you’re not a bot` challenge for `qdck91pAwB4`. Moving the existing provider from Vercel to a dedicated cloud VM did not solve acquisition. |

## Decision rule

- Do not proceed to Task 04 until a different acquisition method passes the probe three consecutive times.
- Keep Vercel for the frontend and lightweight API, not media acquisition.
- Do not add account cookies, residential proxies, IP rotation, or a separate token service during this validation without an explicit product and security decision.
- If the dedicated host receives the same bot challenge, stop and select a licensed acquisition provider or revise the input contract; moving Cloud Tasks alone will not solve acquisition.

## Conclusion

Task 03A completed with a negative infrastructure result. The provider works from the local development network, but both Vercel shared egress and an AWS Lightsail public cloud IP are rejected by YouTube. A generic cloud VM is therefore not an acceptable production acquisition strategy by itself.

The next decision is a product/acquisition decision, not an async orchestration task:

1. Select and validate a licensed media acquisition provider, or
2. Revise the contract so the user supplies an authorized source file while the YouTube URL supplies metadata, or
3. Explicitly approve a separately reviewed token/authentication approach, including its security, policy, and maintenance risks.
