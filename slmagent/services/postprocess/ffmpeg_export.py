"""FFmpeg export / remux for P0."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from slmagent.services.media_tools import get_ffmpeg


def export_final(raw_video: Path, final_path: Path) -> Path:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    if _try_ffmpeg_copy(raw_video, final_path):
        return final_path
    shutil.copy2(raw_video, final_path)
    return final_path


def _try_ffmpeg_copy(src: Path, dest: Path) -> bool:
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return False
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.returncode == 0 and dest.exists() and dest.stat().st_size > 1024
