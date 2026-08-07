"""Resolve ffmpeg/ffprobe for Mock media and deterministic checks."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache
def get_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


@lru_cache
def get_ffprobe() -> str | None:
    found = shutil.which("ffprobe")
    if found:
        return found
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return None
    # Some bundles ship ffprobe next to ffmpeg.
    sibling = Path(ffmpeg).with_name("ffprobe.exe" if Path(ffmpeg).suffix.lower() == ".exe" else "ffprobe")
    if sibling.exists():
        return str(sibling)
    return None


def probe_media(path: Path) -> dict[str, Any]:
    """Return duration/streams. Prefer ffprobe; fall back to ffmpeg -i parse."""
    path = Path(path)
    if not path.exists():
        return {"available": False, "error": "file missing"}

    ffprobe = get_ffprobe()
    if ffprobe:
        try:
            cmd = [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,width,height",
                "-of",
                "json",
                str(path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                data = json.loads(result.stdout or "{}")
                streams = data.get("streams") or []
                fmt = data.get("format") or {}
                video = next((s for s in streams if s.get("codec_type") == "video"), {})
                return {
                    "available": True,
                    "tool": "ffprobe",
                    "duration": float(fmt.get("duration") or 0),
                    "has_video": any(s.get("codec_type") == "video" for s in streams),
                    "has_audio": any(s.get("codec_type") == "audio" for s in streams),
                    "width": video.get("width"),
                    "height": video.get("height"),
                }
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc)}

    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return {"available": False, "error": "ffmpeg/ffprobe not found"}

    try:
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        text = (result.stderr or "") + (result.stdout or "")
        duration = 0.0
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
        if match:
            h, m, s = match.groups()
            duration = int(h) * 3600 + int(m) * 60 + float(s)
        width = height = None
        vmatch = re.search(r"Video:.*?\s(\d{2,5})x(\d{2,5})", text)
        if vmatch:
            width, height = int(vmatch.group(1)), int(vmatch.group(2))
        has_video = "Video:" in text
        has_audio = "Audio:" in text
        # ffmpeg -i exits non-zero even on success; treat parseable duration/video as ok.
        if has_video or duration > 0:
            return {
                "available": True,
                "tool": "ffmpeg",
                "duration": duration,
                "has_video": has_video,
                "has_audio": has_audio,
                "width": width,
                "height": height,
            }
        return {"available": False, "error": "ffmpeg could not parse media streams", "raw_tail": text[-500:]}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "error": str(exc)}
