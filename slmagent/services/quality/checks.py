"""Deterministic quality checks for Phase A (no invented OpenCLIP thresholds)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from slmagent.contracts.models import QualityReport
from slmagent.services.media_tools import probe_media


def check_image(
    path: Path,
    *,
    expected_aspect: str = "16:9",
    stage: str = "CHECK_IMAGE",
) -> QualityReport:
    checks: dict[str, Any] = {}
    warnings: list[str] = []
    passed = True

    exists = path.exists()
    checks["exists"] = exists
    if not exists:
        return QualityReport(stage=stage, passed=False, checks=checks, warnings=["文件不存在"])

    size = path.stat().st_size
    checks["size_bytes"] = size
    if size < 1024:
        passed = False
        warnings.append("文件过小，可能损坏")

    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            w, h = img.size
            mode = img.mode
            extrema = img.convert("L").getextrema()
        checks["width"] = w
        checks["height"] = h
        checks["mode"] = mode
        checks["luma_extrema"] = list(extrema)
        ratio = w / h if h else 0
        expected = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0}.get(expected_aspect, 16 / 9)
        ratio_ok = abs(ratio - expected) < 0.08
        checks["aspect_ok"] = ratio_ok
        if not ratio_ok:
            warnings.append(f"比例偏离预期 {expected_aspect}")
            passed = False
        if extrema[0] == extrema[1]:
            warnings.append("疑似纯色异常帧")
            passed = False
    except Exception as exc:  # noqa: BLE001
        checks["decode_error"] = str(exc)
        passed = False
        warnings.append("无法解码图片")

    checks["openclip_similarity"] = None
    warnings.append("OpenCLIP 阈值待实测校准，本阶段未打分")
    return QualityReport(stage=stage, passed=passed, checks=checks, warnings=warnings)


def check_video(
    path: Path,
    *,
    expected_duration_sec: int = 5,
    stage: str = "CHECK_VIDEO",
) -> QualityReport:
    checks: dict[str, Any] = {}
    warnings: list[str] = []
    passed = True

    exists = path.exists()
    checks["exists"] = exists
    if not exists:
        return QualityReport(stage=stage, passed=False, checks=checks, warnings=["文件不存在"])

    size = path.stat().st_size
    checks["size_bytes"] = size
    if size < 1024:
        passed = False
        warnings.append("视频文件过小（疑似不可播放占位文件）")

    probe = probe_media(path)
    checks["media_probe"] = probe
    if probe.get("available"):
        duration = float(probe.get("duration") or 0)
        checks["duration_sec"] = duration
        if abs(duration - expected_duration_sec) > 1.5:
            warnings.append(f"时长偏离预期 {expected_duration_sec}s")
            passed = False
        width = probe.get("width")
        height = probe.get("height")
        if width and height:
            checks["resolution"] = f"{width}x{height}"
        if not probe.get("has_video"):
            warnings.append("未检测到视频流")
            passed = False
        checks["has_audio"] = bool(probe.get("has_audio"))
    else:
        warnings.append(f"媒体探测失败：{probe.get('error')}")
        passed = False

    checks["frame_similarity"] = None
    warnings.append("首尾帧相似度阈值待实测校准")
    return QualityReport(stage=stage, passed=passed, checks=checks, warnings=warnings)
