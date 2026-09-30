import json
import subprocess
from pathlib import Path

import pytest

from app import video_processing
from app.video_processing import FfmpegVideoProcessor, VideoProcessingError


@pytest.fixture
def fake_tools(monkeypatch):
    monkeypatch.setattr(video_processing.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        output = Path(command[-1])
        if command[0].endswith("ffmpeg"):
            output.write_bytes(b"rendered")
            return subprocess.CompletedProcess(command, 0, b"", b"")
        payload = {
            "format": {"duration": "125.5"},
            "streams": [
                {"codec_type": "audio"},
                {"codec_type": "video", "width": 1920, "height": 1080},
            ],
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload).encode(), b"")

    monkeypatch.setattr(video_processing.subprocess, "run", fake_run)
    return calls


def test_probe_reads_duration_and_dimensions(fake_tools, tmp_path: Path) -> None:
    info = FfmpegVideoProcessor().probe(tmp_path / "input.mp4")

    assert info.duration_seconds == 125.5
    assert (info.width, info.height) == (1920, 1080)
    assert fake_tools[0][0].endswith("ffprobe")


def test_trim_to_vertical_builds_single_pass_command(fake_tools, tmp_path: Path) -> None:
    output = tmp_path / "output.mp4"

    FfmpegVideoProcessor().trim_to_vertical(
        tmp_path / "input.mp4", output, start_seconds=135, end_seconds=185
    )

    command = fake_tools[0]
    assert command[0].endswith("ffmpeg")
    assert command[command.index("-ss") + 1] == "135.000"
    assert command.index("-ss") < command.index("-i")
    assert command[command.index("-t") + 1] == "50.000"
    video_filter = command[command.index("-vf") + 1]
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in video_filter
    assert "crop=1080:1920" in video_filter
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"
    assert output.read_bytes() == b"rendered"


def test_trim_to_vertical_burns_subtitles_after_the_crop(fake_tools, tmp_path: Path) -> None:
    subtitles = tmp_path / "it's, a:b.ass"

    FfmpegVideoProcessor().trim_to_vertical(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        start_seconds=0,
        end_seconds=10,
        subtitles_path=subtitles,
    )

    video_filter = fake_tools[0][fake_tools[0].index("-vf") + 1]
    crop_index = video_filter.index("crop=1080:1920")
    subtitles_index = video_filter.index(",subtitles=filename='")
    assert crop_index < subtitles_index
    escaped = video_filter[subtitles_index:]
    assert "it\\'s\\, a\\:b.ass'" in escaped
    assert "\\" in escaped and escaped.endswith("'")


def test_trim_and_convert_are_separate_operations(fake_tools, tmp_path: Path) -> None:
    processor = FfmpegVideoProcessor()

    processor.trim(tmp_path / "in.mp4", tmp_path / "trim.mp4", start_seconds=1, end_seconds=4)
    processor.convert_to_vertical(tmp_path / "trim.mp4", tmp_path / "vertical.mp4")

    trim_command, vertical_command = fake_tools
    assert "-vf" not in trim_command
    assert "-ss" not in vertical_command
    assert "crop=1080:1920" in vertical_command[vertical_command.index("-vf") + 1]


def test_missing_ffmpeg_is_reported(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(video_processing.shutil, "which", lambda name: None)

    with pytest.raises(VideoProcessingError):
        FfmpegVideoProcessor().convert_to_vertical(tmp_path / "a.mp4", tmp_path / "b.mp4")


def test_ffmpeg_failure_is_wrapped(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(video_processing.shutil, "which", lambda name: f"/usr/bin/{name}")

    def failing_run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr=b"Invalid data found")

    monkeypatch.setattr(video_processing.subprocess, "run", failing_run)

    with pytest.raises(VideoProcessingError):
        FfmpegVideoProcessor().trim(
            tmp_path / "a.mp4", tmp_path / "b.mp4", start_seconds=0, end_seconds=1
        )
