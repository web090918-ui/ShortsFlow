from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.processing_jobs as jobs_module
from app.acquisition import AcquisitionPendingError
from app.main import app
from app.processing_jobs import InMemoryProcessingJobRepository
from app.shorts_pipeline import ShortArtifact, ShortErrorCode, ShortPipelineError, ShortStage


client = TestClient(app)


class StubDispatcher:
    def __init__(self) -> None:
        self.resumes: list[tuple[str, int, int]] = []

    def enqueue(self, job_id, background_tasks) -> str:
        return f"queues/test/tasks/processing-{job_id}"

    def schedule_resume(self, job_id, *, delay_seconds, sequence) -> str:
        self.resumes.append((str(job_id), delay_seconds, sequence))
        return f"queues/test/tasks/processing-{job_id}-r{sequence}"


class AllowWorkerAuthenticator:
    def authenticate(self, authorization: str | None) -> None:
        assert authorization == "Bearer test-token"


class StubStorage:
    def __init__(self) -> None:
        self.missing: set[str] = set()

    def store(self, file_path, *, key, filename):
        raise AssertionError("not used by the stub pipeline")

    def exists(self, key: str) -> bool:
        return key not in self.missing


class StubShortPipeline:
    def __init__(self, tmp_path: Path, *, error: Exception | None = None) -> None:
        self.tmp_path = tmp_path
        self.error = error
        self.calls: list[dict] = []
        self.storage = StubStorage()

    def run(
        self,
        *,
        job_id,
        source_url,
        start_seconds,
        end_seconds,
        report,
        captions=None,
        template=None,
        layout=None,
        title=None,
    ):
        self.calls.append(
            {
                "layout": layout,
                "title": title,
                "job_id": job_id,
                "url": source_url,
                "start": start_seconds,
                "end": end_seconds,
                "captions": [cue.text for cue in captions] if captions else None,
                "raw_captions": captions,
                "template": template,
            }
        )
        report(ShortStage.DOWNLOADING, 10)
        if self.error is not None:
            raise self.error
        report(ShortStage.PROCESSING, 60)
        report(ShortStage.UPLOADING, 90)
        output = self.tmp_path / f"{job_id}.mp4"
        output.write_bytes(b"short-bytes")
        return ShortArtifact(
            provider="stub",
            storage="local",
            storage_key=f"shorts/{job_id}.mp4",
            download_url=None,
            local_path=str(output),
            expires_at=None,
            source_title="Sample",
            source_duration_seconds=600,
            source_width=1920,
            source_height=1080,
            output_bytes=11,
        )


@pytest.fixture
def stub_dispatcher():
    return StubDispatcher()


@pytest.fixture(autouse=True)
def isolated_jobs(monkeypatch, stub_dispatcher):
    repository = InMemoryProcessingJobRepository()
    monkeypatch.setattr(jobs_module, "repository", repository)
    monkeypatch.setattr(jobs_module, "dispatcher", stub_dispatcher)
    monkeypatch.setattr(jobs_module, "worker_authenticator", AllowWorkerAuthenticator())
    return repository


def _payload(**overrides) -> dict:
    payload = {
        "youtube_url": "https://www.youtube.com/watch?v=abc123",
        "start_seconds": 135,
        "end_seconds": 185,
        "rights_confirmed": True,
    }
    payload.update(overrides)
    return payload


def _run_worker(job_id: str, retry_count: int = 0):
    return client.post(
        "/worker/process",
        json={"job_id": job_id},
        headers={
            "Authorization": "Bearer test-token",
            "X-CloudTasks-TaskRetryCount": str(retry_count),
        },
    )


def test_creates_queued_short_job() -> None:
    response = client.post("/shorts", json=_payload())

    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "queued"
    assert created["progress"] == 0
    assert created["duration_seconds"] == 50
    assert created["template_id"] == "CLEAN_CAPTION"
    assert created["download_url"] is None

    read = client.get(f"/shorts/{created['id']}")
    assert read.status_code == 200
    assert read.json() == created

    # The underlying processing job is the Task 04 record with the new step.
    job = client.get(f"/processing-jobs/{created['id']}").json()
    assert job["step"] == "SHORT_RENDER"


@pytest.mark.parametrize(
    "overrides, expected_detail",
    [
        ({"rights_confirmed": False}, "소유권"),
        ({"start_seconds": 50, "end_seconds": 50}, "종료 시간은 시작 시간보다"),
        ({"start_seconds": 0, "end_seconds": 181}, "최대 180초"),
        ({"youtube_url": "https://example.com/video"}, "YouTube 영상 URL"),
    ],
)
def test_rejects_invalid_requests(overrides, expected_detail) -> None:
    response = client.post("/shorts", json=_payload(**overrides))

    assert response.status_code == 422
    assert expected_detail in response.json()["detail"]


def test_rejects_negative_start() -> None:
    response = client.post("/shorts", json=_payload(start_seconds=-1))

    assert response.status_code == 422


def test_worker_completes_short_and_serves_file(monkeypatch, tmp_path: Path) -> None:
    pipeline = StubShortPipeline(tmp_path)
    monkeypatch.setattr(jobs_module, "short_pipeline", pipeline)
    created = client.post("/shorts", json=_payload()).json()

    worker = _run_worker(created["id"])
    assert worker.status_code == 200
    assert worker.json()["status"] == "COMPLETED"
    assert worker.json()["result"]["next_step"] == "DOWNLOAD"
    assert pipeline.calls == [
        {
            "job_id": created["id"],
            "url": "https://www.youtube.com/watch?v=abc123",
            "start": 135,
            "end": 185,
            "captions": None,
            "raw_captions": None,
            "template": "CLEAN_CAPTION",
            "layout": "FILL",
            "title": None,
        }
    ]

    short = client.get(f"/shorts/{created['id']}").json()
    assert short["status"] == "completed"
    assert short["artifact_state"] == "ready"
    assert short["progress"] == 100
    assert short["download_url"] == f"/shorts/{created['id']}/file"
    assert short["error_message"] is None

    file_response = client.get(short["download_url"])
    assert file_response.status_code == 200
    assert file_response.headers["content-type"] == "video/mp4"
    assert "cutpick-short-135-185.mp4" in file_response.headers["content-disposition"]
    assert file_response.content == b"short-bytes"

    # Duplicate delivery does not rerun the pipeline.
    _run_worker(created["id"])
    assert len(pipeline.calls) == 1


def test_stage_is_exposed_while_processing(monkeypatch, isolated_jobs) -> None:
    created = client.post("/shorts", json=_payload()).json()
    claimed = isolated_jobs.claim(__import__("uuid").UUID(created["id"]))
    assert claimed is not None and claimed.acquired
    isolated_jobs.save(claimed.job.model_copy(update={"stage": "UPLOADING", "progress": 90}))

    short = client.get(f"/shorts/{created['id']}").json()

    assert short["status"] == "uploading"
    assert short["progress"] == 90


def test_non_retryable_failure_marks_job_failed_immediately(monkeypatch, tmp_path) -> None:
    error = ShortPipelineError(
        ShortErrorCode.INVALID_TIME_RANGE, "선택한 종료 시간이 원본 영상 길이를 초과합니다.",
        retryable=False,
    )
    monkeypatch.setattr(jobs_module, "short_pipeline", StubShortPipeline(tmp_path, error=error))
    created = client.post("/shorts", json=_payload()).json()

    worker = _run_worker(created["id"])

    assert worker.status_code == 200
    assert worker.json()["status"] == "FAILED"
    assert worker.json()["error_code"] == "INVALID_TIME_RANGE"
    short = client.get(f"/shorts/{created['id']}").json()
    assert short["status"] == "failed"
    assert short["error_message"] == "선택한 종료 시간이 원본 영상 길이를 초과합니다."
    assert short["download_url"] is None


def test_retryable_failure_requeues_until_last_attempt(monkeypatch, tmp_path) -> None:
    error = ShortPipelineError(ShortErrorCode.SOURCE_DOWNLOAD_FAILED, "다운로드 실패")
    monkeypatch.setattr(jobs_module, "short_pipeline", StubShortPipeline(tmp_path, error=error))
    created = client.post("/shorts", json=_payload()).json()

    first = _run_worker(created["id"], retry_count=0)
    assert first.status_code == 409
    job = client.get(f"/processing-jobs/{created['id']}").json()
    assert job["status"] == "QUEUED"
    assert job["error_code"] == "SOURCE_DOWNLOAD_FAILED"

    last = _run_worker(created["id"], retry_count=2)
    assert last.status_code == 409
    short = client.get(f"/shorts/{created['id']}").json()
    assert short["status"] == "failed"
    assert short["error_message"] == "다운로드 실패"


def _completed_analysis_job(repository, *, template="BOLD_HIGHLIGHT"):
    """Persist a finished transcript/candidate/ranking job like the Worker would."""
    from datetime import datetime, timezone

    from app.processing_jobs import ProcessingJobRecord, ProcessingStep

    now = datetime.now(timezone.utc)
    job = ProcessingJobRecord(
        id=uuid4(),
        source_id=uuid4(),
        source_url="https://www.youtube.com/watch?v=analysis1",
        status="COMPLETED",
        step=ProcessingStep.RANKING,
        progress=100,
        start_seconds=0,
        end_seconds=600,
        duration_seconds=600,
        template_id=template,
        attempt_count=1,
        error_message=None,
        result={
            "next_step": "RENDER",
            "transcript": {
                "segments": [
                    {"start_seconds": 95, "end_seconds": 101, "text": "이전 문장"},
                    {"start_seconds": 101, "end_seconds": 110, "text": ">> 후보 안 첫 문장 [음악]"},
                    {"start_seconds": 110, "end_seconds": 120, "text": "[음악]"},
                    {"start_seconds": 120, "end_seconds": 150, "text": "후보 안 둘째 문장"},
                    {"start_seconds": 170, "end_seconds": 180, "text": "후보 밖"},
                ]
            },
            "candidates": {
                "items": [
                    {"id": "cand-a", "index": 1, "start_seconds": 100, "end_seconds": 155},
                    {"id": "cand-b", "index": 2, "start_seconds": 300, "end_seconds": 340},
                ]
            },
            "ranking": {"top_3": []},
        },
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
    )
    repository.save(job)
    return job


def test_creates_short_from_ranked_candidate_with_captions(
    monkeypatch, isolated_jobs, tmp_path
) -> None:
    pipeline = StubShortPipeline(tmp_path)
    monkeypatch.setattr(jobs_module, "short_pipeline", pipeline)
    analysis = _completed_analysis_job(isolated_jobs)

    response = client.post(
        "/shorts",
        json={
            "processing_job_id": str(analysis.id),
            "candidate_id": "cand-a",
            "rights_confirmed": True,
        },
    )

    assert response.status_code == 202
    created = response.json()
    assert created["youtube_url"] == "https://www.youtube.com/watch?v=analysis1"
    assert created["start_seconds"] == 100
    assert created["end_seconds"] == 155
    assert created["template_id"] == "BOLD_HIGHLIGHT"
    assert created["candidate_id"] == "cand-a"
    assert created["processing_job_id"] == str(analysis.id)

    worker = _run_worker(created["id"])
    assert worker.status_code == 200
    call = pipeline.calls[0]
    assert call["start"] == 100 and call["end"] == 155
    assert call["template"] == "BOLD_HIGHLIGHT"
    assert call["layout"] == "FILL"
    # Only cues overlapping the candidate reach the renderer.
    assert call["captions"] == ["이전 문장", "후보 안 첫 문장", "후보 안 둘째 문장"]

    short = client.get(f"/shorts/{created['id']}").json()
    assert short["status"] == "completed"
    assert short["preview_url"] == f"/shorts/{created['id']}/file?inline=true"

    inline = client.get(short["preview_url"])
    assert inline.status_code == 200
    assert inline.headers["content-disposition"].startswith("inline")


def test_candidate_render_validates_inputs(isolated_jobs) -> None:
    analysis = _completed_analysis_job(isolated_jobs)

    mixed = client.post(
        "/shorts",
        json={
            "processing_job_id": str(analysis.id),
            "candidate_id": "cand-a",
            "youtube_url": "https://youtu.be/x",
            "rights_confirmed": True,
        },
    )
    assert mixed.status_code == 422

    missing_candidate = client.post(
        "/shorts",
        json={
            "processing_job_id": str(analysis.id),
            "candidate_id": "nope",
            "rights_confirmed": True,
        },
    )
    assert missing_candidate.status_code == 404

    unknown_job = client.post(
        "/shorts",
        json={"processing_job_id": str(uuid4()), "candidate_id": "cand-a", "rights_confirmed": True},
    )
    assert unknown_job.status_code == 404

    incomplete = isolated_jobs.get(analysis.id).model_copy(update={"status": "QUEUED"})
    isolated_jobs.save(incomplete)
    not_ready = client.post(
        "/shorts",
        json={"processing_job_id": str(analysis.id), "candidate_id": "cand-a", "rights_confirmed": True},
    )
    assert not_ready.status_code == 409


def test_pending_acquisition_defers_the_job_without_spending_attempts(
    monkeypatch, stub_dispatcher, tmp_path
) -> None:
    pending = AcquisitionPendingError("아직 확보 중", retry_after_seconds=60)
    pipeline = StubShortPipeline(tmp_path, error=pending)
    monkeypatch.setattr(jobs_module, "short_pipeline", pipeline)
    created = client.post("/shorts", json=_payload()).json()

    worker = _run_worker(created["id"])

    assert worker.status_code == 200
    job = worker.json()
    assert job["status"] == "QUEUED"
    assert job["stage"] == "DOWNLOADING"
    assert job["error_code"] is None
    assert job["error_message"] == "아직 확보 중"
    assert stub_dispatcher.resumes == [(created["id"], 60, 1)]

    short = client.get(f"/shorts/{created['id']}").json()
    assert short["status"] == "downloading"
    assert short["error_message"] is None

    # The resumed delivery claims the job again and can now finish it.
    pipeline.error = None
    resumed = _run_worker(created["id"])
    assert resumed.json()["status"] == "COMPLETED"
    assert resumed.json()["resume_count"] if "resume_count" in resumed.json() else True
    assert client.get(f"/shorts/{created['id']}").json()["status"] == "completed"


def _complete(monkeypatch, tmp_path, *, expires_at=None):
    pipeline = StubShortPipeline(tmp_path)
    monkeypatch.setattr(jobs_module, "short_pipeline", pipeline)
    created = client.post("/shorts", json=_payload()).json()
    _run_worker(created["id"])
    if expires_at is not None:
        job = jobs_module.repository.get(__import__("uuid").UUID(created["id"]))
        result = dict(job.result)
        result["short"] = {**result["short"], "expires_at": expires_at.isoformat()}
        jobs_module.repository.save(job.model_copy(update={"result": result}))
    return pipeline, created["id"]


def test_expired_download_link_is_reported_and_not_served(monkeypatch, tmp_path) -> None:
    from datetime import datetime, timedelta, timezone

    _, job_id = _complete(
        monkeypatch, tmp_path, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )

    short = client.get(f"/shorts/{job_id}").json()
    assert short["status"] == "completed"
    assert short["artifact_state"] == "expired"
    assert short["download_url"] is None
    assert short["preview_url"] is None
    assert short["download_expires_at"] is not None

    response = client.get(f"/shorts/{job_id}/file")
    assert response.status_code == 410
    assert "만료" in response.json()["detail"]


def test_removed_artifact_is_reported_as_unavailable(monkeypatch, tmp_path) -> None:
    pipeline, job_id = _complete(monkeypatch, tmp_path)
    pipeline.storage.missing.add(f"shorts/{job_id}.mp4")

    short = client.get(f"/shorts/{job_id}").json()
    assert short["artifact_state"] == "unavailable"
    assert short["download_url"] is None

    response = client.get(f"/shorts/{job_id}/file")
    assert response.status_code == 410
    assert "삭제" in response.json()["detail"]


def test_future_expiry_keeps_the_artifact_ready(monkeypatch, tmp_path) -> None:
    from datetime import datetime, timedelta, timezone

    _, job_id = _complete(
        monkeypatch, tmp_path, expires_at=datetime.now(timezone.utc) + timedelta(hours=20)
    )

    short = client.get(f"/shorts/{job_id}").json()
    assert short["artifact_state"] == "ready"
    assert short["download_url"] == f"/shorts/{job_id}/file"


def test_failed_and_pending_jobs_expose_artifact_state(monkeypatch, tmp_path) -> None:
    created = client.post("/shorts", json=_payload()).json()
    assert created["artifact_state"] == "pending"

    error = ShortPipelineError(ShortErrorCode.FFMPEG_FAILED, "편집 실패", retryable=False)
    monkeypatch.setattr(jobs_module, "short_pipeline", StubShortPipeline(tmp_path, error=error))
    _run_worker(created["id"])
    assert client.get(f"/shorts/{created['id']}").json()["artifact_state"] == "failed"


def test_file_download_requires_completed_job() -> None:
    created = client.post("/shorts", json=_payload()).json()

    response = client.get(f"/shorts/{created['id']}/file")

    assert response.status_code == 409


def test_unknown_short_job_returns_404() -> None:
    assert client.get(f"/shorts/{uuid4()}").status_code == 404
    assert client.get(f"/shorts/{uuid4()}/file").status_code == 404


def test_candidate_render_carries_layout_and_word_timings(
    monkeypatch, isolated_jobs, tmp_path
) -> None:
    pipeline = StubShortPipeline(tmp_path)
    monkeypatch.setattr(jobs_module, "short_pipeline", pipeline)
    analysis = _completed_analysis_job(isolated_jobs)
    analysis.layout_id = "FIT"
    analysis.result["transcript"]["segments"][1]["words"] = [
        {"start_seconds": 101, "end_seconds": 105, "text": "후보"},
        {"start_seconds": 105, "end_seconds": 110, "text": "안"},
    ]
    isolated_jobs.save(analysis)

    created = client.post(
        "/shorts",
        json={
            "processing_job_id": str(analysis.id),
            "candidate_id": "cand-a",
            "rights_confirmed": True,
        },
    ).json()
    assert created["layout_id"] == "FIT"

    assert _run_worker(created["id"]).status_code == 200
    call = pipeline.calls[0]
    assert call["layout"] == "FIT"
    assert call["captions"][1] == "후보 안 첫 문장"
    assert [w.text for w in call["raw_captions"][1].words] == ["후보", "안"]
    assert call["raw_captions"][0].words is None


def test_layout_can_be_overridden_per_render_and_set_on_manual_ranges(
    monkeypatch, isolated_jobs, tmp_path
) -> None:
    pipeline = StubShortPipeline(tmp_path)
    monkeypatch.setattr(jobs_module, "short_pipeline", pipeline)
    analysis = _completed_analysis_job(isolated_jobs)

    override = client.post(
        "/shorts",
        json={
            "processing_job_id": str(analysis.id),
            "candidate_id": "cand-a",
            "rights_confirmed": True,
            "layout_id": "FIT",
        },
    ).json()
    manual = client.post(
        "/shorts",
        json={
            "youtube_url": "https://www.youtube.com/watch?v=abc123",
            "start_seconds": 10,
            "end_seconds": 40,
            "rights_confirmed": True,
            "template_id": "NEON_GLOW",
            "layout_id": "FIT",
        },
    ).json()

    assert override["layout_id"] == "FIT"
    assert manual["layout_id"] == "FIT" and manual["template_id"] == "NEON_GLOW"
    assert _run_worker(manual["id"]).status_code == 200
    assert pipeline.calls[0]["layout"] == "FIT"


def test_candidate_render_titles_from_a_short_hook_unless_the_user_typed_one(
    monkeypatch, isolated_jobs, tmp_path
) -> None:
    pipeline = StubShortPipeline(tmp_path)
    monkeypatch.setattr(jobs_module, "short_pipeline", pipeline)
    analysis = _completed_analysis_job(isolated_jobs)
    items = analysis.result["candidates"]["items"]
    items[0]["hook_text"] = "독립을 위해 목숨을 건 여자"
    items[1]["hook_text"] = "이 문장은 서른 글자를 훌쩍 넘기는 긴 설명이라 제목으로 쓰기에는 어울리지 않습니다"
    isolated_jobs.save(analysis)

    short_hook = client.post(
        "/shorts",
        json={"processing_job_id": str(analysis.id), "candidate_id": "cand-a", "rights_confirmed": True},
    ).json()
    long_hook = client.post(
        "/shorts",
        json={"processing_job_id": str(analysis.id), "candidate_id": "cand-b", "rights_confirmed": True},
    ).json()
    typed = client.post(
        "/shorts",
        json={
            "processing_job_id": str(analysis.id),
            "candidate_id": "cand-b",
            "rights_confirmed": True,
            "title": "  암표 수수료도 [이제 다 제 겁니다]  ",
        },
    ).json()

    assert short_hook["title"] == "독립을 위해 목숨을 건 여자"
    assert long_hook["title"] is None
    assert typed["title"] == "암표 수수료도 [이제 다 제 겁니다]"

    assert _run_worker(typed["id"]).status_code == 200
    assert pipeline.calls[0]["title"] == "암표 수수료도 [이제 다 제 겁니다]"


def test_manual_range_carries_its_title_to_the_render(monkeypatch, isolated_jobs, tmp_path) -> None:
    pipeline = StubShortPipeline(tmp_path)
    monkeypatch.setattr(jobs_module, "short_pipeline", pipeline)

    created = client.post(
        "/shorts",
        json={
            "youtube_url": "https://www.youtube.com/watch?v=abc123",
            "start_seconds": 10,
            "end_seconds": 40,
            "rights_confirmed": True,
            "template_id": "HEADLINE_YELLOW",
            "layout_id": "STAGE",
            "title": "첫 영유아 건강검진, 왜 받아야 할까?",
        },
    ).json()

    assert created["title"] == "첫 영유아 건강검진, 왜 받아야 할까?"
    assert created["layout_id"] == "STAGE"
    assert _run_worker(created["id"]).status_code == 200
    call = pipeline.calls[0]
    assert call["title"] == "첫 영유아 건강검진, 왜 받아야 할까?"
    assert call["template"] == "HEADLINE_YELLOW" and call["layout"] == "STAGE"
