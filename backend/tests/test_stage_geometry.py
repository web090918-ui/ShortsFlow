"""Verify real FFmpeg pixels, including sources taller than the reserved band."""

import shutil
import subprocess

import pytest

from app.templates import RenderLayout
from app.video_processing import _vertical_filter


@pytest.mark.parametrize("size", ["640x480", "360x640", "640x360"])
def test_stage_keeps_source_out_of_text_bands(size: str) -> None:
    executable = shutil.which("ffmpeg")
    if executable is None:
        pytest.skip("FFmpeg is not installed")
    frame = subprocess.run(
        [executable, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
         f"color=red:s={size}:d=1", "-vf",
         _vertical_filter(layout=RenderLayout.STAGE, stage_color="#FFFFFF"),
         "-frames:v", "1", "-threads", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
        check=True, capture_output=True, timeout=30,
    ).stdout

    def pixel(y: int, x: int = 540) -> tuple[int, ...]:
        offset = (y * 1080 + x) * 3
        return tuple(frame[offset:offset + 3])

    for y in (520, 620, 1300, 1740):
        assert min(pixel(y)) >= 245, (size, y, pixel(y))
    for x in (0, 540, 1079):
        red, green, blue = pixel(960, x)
        assert red > 240 and green < 15 and blue < 15, (size, x)
