import json
import subprocess
from pathlib import Path

import pytest

from app import video_processing
from app.video_processing import (
    FfmpegVideoProcessor,
    VideoProcessingError,
    parse_silences,
    speech_segments,
)


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


def test_fit_layout_keeps_the_whole_frame_over_a_blurred_background(
    fake_tools, tmp_path: Path
) -> None:
    from app.templates import RenderLayout

    FfmpegVideoProcessor().trim_to_vertical(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        start_seconds=0,
        end_seconds=10,
        subtitles_path=tmp_path / "captions.ass",
        layout=RenderLayout.FIT,
    )

    video_filter = fake_tools[0][fake_tools[0].index("-vf") + 1]
    assert video_filter.startswith("split[bg][fg];")
    assert "boxblur=" in video_filter
    assert "[fg]scale=1080:1920:force_original_aspect_ratio=decrease" in video_filter
    assert "[bgs][fgs]overlay=(W-w)/2:(H-h)/2" in video_filter
    # Captions are burnt onto the composed frame, so their 1080x1920 positions hold.
    assert video_filter.index("overlay=") < video_filter.index(",subtitles=filename=")


def test_stage_layout_fills_picture_band_on_black(fake_tools, tmp_path: Path) -> None:
    from app.templates import RenderLayout

    FfmpegVideoProcessor().trim_to_vertical(
        tmp_path / "input.mp4",
        tmp_path / "output.mp4",
        start_seconds=0,
        end_seconds=10,
        subtitles_path=tmp_path / "captions.ass",
        layout=RenderLayout.STAGE,
    )

    video_filter = fake_tools[0][fake_tools[0].index("-vf") + 1]
    assert video_filter.startswith(
        "scale=1080:608:force_original_aspect_ratio=increase,crop=1080:608,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:0x000000,setsar=1"
    )
    assert video_filter.index("pad=") < video_filter.index(",subtitles=filename=")


def test_probe_reports_whether_the_source_has_audio(fake_tools, tmp_path: Path) -> None:
    info = FfmpegVideoProcessor().probe(tmp_path / "in.mp4")
    assert info.has_audio is True


def test_parse_silences_pairs_log_lines_and_offsets_them() -> None:
    stderr = (
        "[silencedetect @ 0x1] silence_start: 5.2\n"
        "[silencedetect @ 0x1] silence_end: 6.8 | silence_duration: 1.6\n"
        "[silencedetect @ 0x1] silence_start: 20.0\n"
    )
    assert parse_silences(stderr, offset_seconds=100.0) == [(105.2, 106.8)]


def test_speech_segments_keep_padding_and_merge_slivers() -> None:
    segments = speech_segments(
        [(20.0, 22.0), (22.1, 24.0), (39.9, 41.0)], start_seconds=10.0, end_seconds=40.0
    )
    # The 22-22.1 sliver between two pauses is too short for a jump cut, so it stays
    # attached to the first part together with the pause before it; a pause running
    # past the end of the range leaves nothing to cut after the padding.
    assert segments == [(10.0, 22.22), (23.88, 40.0)]
    assert speech_segments([], start_seconds=0.0, end_seconds=30.0) == [(0.0, 30.0)]
    # A pause too short to survive the padding is left alone.
    assert speech_segments([(5.0, 5.2)], start_seconds=0.0, end_seconds=30.0) == [(0.0, 30.0)]


def test_detect_silences_runs_silencedetect_over_the_range_only(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(video_processing.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        stderr = b"[silencedetect] silence_start: 1.0\n[silencedetect] silence_end: 2.5\n"
        return subprocess.CompletedProcess(command, 0, b"", stderr)

    monkeypatch.setattr(video_processing.subprocess, "run", fake_run)

    silences = FfmpegVideoProcessor().detect_silences(
        tmp_path / "in.mp4", start_seconds=30.0, end_seconds=60.0
    )

    command = calls[0]
    assert command[command.index("-ss") + 1] == "30.000"
    assert command[command.index("-t") + 1] == "30.000"
    assert any("silencedetect=noise=-35dB:d=0.6" in part for part in command)
    assert command[-2:] == ["null", "-"]
    assert silences == [(31.0, 32.5)]


def test_trim_to_vertical_with_segments_joins_them_before_reframing(fake_tools, tmp_path: Path) -> None:
    FfmpegVideoProcessor().trim_to_vertical(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        start_seconds=10.0,
        end_seconds=40.0,
        keep_segments=[(10.0, 20.0), (22.0, 40.0)],
    )

    command = fake_tools[0]
    graph = command[command.index("-filter_complex") + 1]
    assert "[0:v]trim=start=0.000:end=10.000,setpts=PTS-STARTPTS[v0]" in graph
    assert "[0:a]atrim=start=12.000:end=30.000,asetpts=PTS-STARTPTS[a1]" in graph
    assert "[v0][a0][v1][a1]concat=n=2:v=1:a=1[vc][aout]" in graph
    assert graph.endswith("crop=1080:1920,setsar=1[vout]")
    assert "-t" not in command
    assert command[command.index("-map") + 1] == "[vout]"
    assert "-vf" not in command


def test_trim_to_vertical_with_a_single_full_segment_uses_the_plain_cut(fake_tools, tmp_path: Path) -> None:
    FfmpegVideoProcessor().trim_to_vertical(
        tmp_path / "in.mp4",
        tmp_path / "out.mp4",
        start_seconds=10.0,
        end_seconds=40.0,
        keep_segments=[(10.0, 40.0)],
    )
    assert "-filter_complex" not in fake_tools[0]
    assert "-vf" in fake_tools[0]
