# Documentation

ShortsFlow product and delivery decisions are maintained here:

- [Product](PRODUCT.md) defines the MVP1 flows, ranking language, roadmap, and exclusions.
- [Architecture](ARCHITECTURE.md) defines the common Source model and minimal system boundaries.
- [MVP backlog](MVP_BACKLOG.md) defines the ordered delivery plan and the next task.
- [Competitor research](COMPETITOR_RESEARCH.md) records confirmed URL-to-Shorts behavior, evidence boundaries, and acquisition implications.
- [Task 03A validation](TASK_03A_VALIDATION.md) records the executable acquisition checks and environment results.
- [Task 04 Cloud Run deployment](TASK_04_DEPLOYMENT.md) records the async-job infrastructure and validation steps.
- [Task 05 transcript](TASK_05_TRANSCRIPT.md) records the caption-first transcript pipeline and its validation state.
- [Task 05B manual-range Short](TASK_05B_MANUAL_SHORT.md) records the URL + start/end to 9:16 MP4 pipeline, its provider boundaries, and deployment requirements.
- [Task 06 candidates](TASK_06_CANDIDATES.md) records how 10-15 clip candidates are derived from the transcript and what each candidate carries for ranking and rendering.
- [Task 07 ranking](TASK_07_RANKING.md) records the generic AI Score criteria, the Top 3 selection rule, and the ranking provider boundary.
- [Task 08 preview and render](TASK_08_RENDER.md) records candidate-based rendering, the ASS caption templates, inline preview URLs, and the Top 3 UI.
- [Task 09 download UX](TASK_09_DOWNLOAD.md) records the artifact states (ready, expired, unavailable, failed), the retry actions, and the end-to-end acceptance evidence.
- [Task 11 upload sources](TASK_11_UPLOAD.md) records direct-to-storage uploads, the upload acquisition route, and the bucket CORS setup.
