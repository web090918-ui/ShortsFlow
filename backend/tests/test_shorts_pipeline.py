from pathlib import Path

import pytest

from app.acquisition import AcquiredVideo, AcquisitionError
from app.shorts_pipeline import (
    LocalArtifactStorage,
    ShortErrorCode,
    ShortPipeline,
    ShortPipelineError,
    ShortStage,
    StoredArtifact,
)
from app.video_processing import VideoInfo, VideoProcessingError


class StubProvider:
    name = "stub"

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.destinations: list[Path] = []

    def acquire(self, url, *, destination, progress=None):
        if self.error is not None:
            raise self.error
        destination.write_bytes(b"source")
        self.destinations.append(destination)
        if progress:
            progress(100)
        return AcquiredVideo(
            path=destination, provider=self.name, title="Test", duration_seconds=120
        )


class StubProcessor:
    def __init__(self, *, duration: float = 120, fail: bool = False) -> None:
        self.duration = duration
        self.fail = fail
        self.calls: list[dict] = []

    def probe(self, media_path):
        return VideoInfo(duration_seconds=self.duration, width=1920, height=1080)

    def trim(self, input_path, output_path, *, start_seconds, end_seconds):
        raise AssertionError("pipeline should use the single-pass render")

    def convert_to_vertical(self, input_path, output_path):
        raise AssertionError("pipeline should use the single-pass render")

    def trim_to_vertical(self, input_path, output_path, *, start_seconds, end_seconds):
        if self.fail:
            raise VideoProcessingError("boom")
        self.calls.append({"start": start_seconds, "end": end_seconds})
        output_path.write_bytes(b"short")


class StubStorage:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.stored: list[tuple[Path, str]] = []

    def store(self, file_path, *, key, filename):
        if self.fail:
            raise OSError("bucket unavailable")
        self.stored.append((file_path, key))
        return StoredArtifact(
            storage="stub",
            key=key,
            download_url="https://example.com/short.mp4",
            local_path=None,
            expires_at=None,
        )


def _run(pipeline: ShortPipeline, *, start=10.0, end=40.0):
    stages: list[tuple[ShortStage, int]] = []
    artifact = pipeline.run(
        job_id="job-1",
        source_url="https://www.youtube.com/watch?v=abc",
        start_seconds=start,
        end_seconds=end,
        report=lambda stage, progress: stages.append((stage, progress)),
    )
    return artifact, stages


def test_pipeline_acquires_renders_stores_and_cleans_up() -> None:
    provider = StubProvider()
    processor = StubProcessor()
    storage = StubStorage()
    pipeline = ShortPipeline(provider, processor, storage)

    artifact, stages = _run(pipeline)

    assert artifact.provider == "stub"
    assert artifact.storage == "stub"
    assert artifact.storage_key == "shorts/job-1.mp4"
    assert artifact.download_url == "https://example.com/short.mp4"
    assert artifact.source_duration_seconds == 120
    assert artifact.output_bytes == len(b"short")
    assert processor.calls == [{"start": 10.0, "end": 40.0}]
    assert [stage for stage, _ in stages][:1] == [ShortStage.DOWNLOADING]
    assert ShortStage.PROCESSING in {stage for stage, _ in stages}
    assert ShortStage.UPLOADING in {stage for stage, _ in stages}
    # Temporary media is removed after the attempt.
    assert not provider.destinations[0].exists()
    assert not provider.destinations[0].parent.exists()


def test_pipeline_rejects_range_past_actual_duration_without_retry() -> None:
    pipeline = ShortPipeline(StubProvider(), StubProcessor(duration=30), StubStorage())

    with pytest.raises(ShortPipelineError) as excinfo:
        _run(pipeline, start=10, end=40)

    assert excinfo.value.code == ShortErrorCode.INVALID_TIME_RANGE
    assert excinfo.value.retryable is False


def test_pipeline_maps_acquisition_errors_and_keeps_retry_flag() -> None:
    provider = StubProvider(error=AcquisitionError("blocked", retryable=False))
    pipeline = ShortPipeline(provider, StubProcessor(), StubStorage())

    with pytest.raises(ShortPipelineError) as excinfo:
        _run(pipeline)

    assert excinfo.value.code == ShortErrorCode.SOURCE_DOWNLOAD_FAILED
    assert excinfo.value.retryable is False
    assert str(excinfo.value) == "blocked"


def test_pipeline_maps_ffmpeg_and_storage_failures() -> None:
    with pytest.raises(ShortPipelineError) as ffmpeg_error:
        _run(ShortPipeline(StubProvider(), StubProcessor(fail=True), StubStorage()))
    assert ffmpeg_error.value.code == ShortErrorCode.FFMPEG_FAILED

    with pytest.raises(ShortPipelineError) as storage_error:
        _run(ShortPipeline(StubProvider(), StubProcessor(), StubStorage(fail=True)))
    assert storage_error.value.code == ShortErrorCode.STORAGE_UPLOAD_FAILED
    assert storage_error.value.retryable is True


def test_local_storage_moves_file_into_root(tmp_path: Path) -> None:
    source = tmp_path / "output.mp4"
    source.write_bytes(b"short")
    storage = LocalArtifactStorage(tmp_path / "artifacts")

    stored = storage.store(source, key="shorts/job.mp4", filename="short.mp4")

    assert stored.storage == "local"
    assert stored.download_url is None
    assert stored.local_path == tmp_path / "artifacts" / "shorts" / "job.mp4"
    assert stored.local_path.read_bytes() == b"short"
    assert not source.exists()
