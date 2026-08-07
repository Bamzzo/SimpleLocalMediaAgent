"""Phase A manual acceptance: Gradio-equivalent path via FastAPI + ref upload."""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slmagent.apps.gradio_app import run_job
from slmagent.configs.settings import get_settings
from slmagent.contracts.models import (
    AspectRatio,
    Brief,
    CameraMove,
    ContentType,
    GenerationMode,
    VisualStyle,
)
from slmagent.services.media_tools import get_ffmpeg, probe_media


def _assert_playable(label: str, path: Path, expected_duration: float = 5.0) -> bool:
    size = path.stat().st_size if path.exists() else 0
    probe = probe_media(path) if path.exists() else {"available": False, "error": "missing"}
    duration = float(probe.get("duration") or 0)
    ok = (
        path.exists()
        and size > 1024
        and bool(probe.get("available"))
        and bool(probe.get("has_video"))
        and abs(duration - expected_duration) <= 1.5
    )
    print(
        f"{label}: size={size} probe_ok={probe.get('available')} "
        f"duration={duration} has_video={probe.get('has_video')} tool={probe.get('tool')} "
        f"-> {'OK' if ok else 'FAIL'}"
    )
    if not probe.get("available"):
        print("  probe_error:", probe.get("error"))
    return ok


def main() -> None:
    settings = get_settings()
    base = settings.api_base_url.rstrip("/")
    ffmpeg = get_ffmpeg()
    print("FFMPEG", ffmpeg)
    if not ffmpeg:
        print("ACCEPTANCE FAIL: ffmpeg unavailable (install system ffmpeg or imageio-ffmpeg)")
        raise SystemExit(1)

    health = httpx.get(f"{base}/health", timeout=10)
    health.raise_for_status()
    print("HEALTH", health.json())

    defaults = yaml.safe_load((ROOT / "slmagent" / "configs" / "defaults.yaml").read_text(encoding="utf-8"))
    demo = defaults["demo_case"]

    src = ROOT / "runs" / "_manual_accept" / "ref_product.png"
    if not src.exists():
        from PIL import Image, ImageDraw

        src.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (640, 360), (20, 40, 70))
        ImageDraw.Draw(img).text((40, 40), "SLMAgent ref", fill=(220, 240, 255))
        img.save(src)

    staging = settings.runs_dir / "_uploads" / uuid.uuid4().hex
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / src.name
    shutil.copy2(src, staged)

    brief = Brief(
        project_name=demo["project_name"],
        mode="free",
        content_type=ContentType("项目宣传片"),
        description=demo["description"],
        selling_points=demo["selling_points"],
        audience=demo["audience"],
        visual_style=VisualStyle("科技未来"),
        aspect_ratio=AspectRatio("16:9"),
        duration_sec=5,
        camera_move=CameraMove("缓慢推进"),
        generation_mode=GenerationMode("首尾帧生视频"),
        constraints=demo["constraints"],
        reference_image_paths=[str(staged)],
    )
    response = httpx.post(
        f"{base}/pipeline/run",
        json={"brief": brief.model_dump(mode="json")},
        timeout=settings.api_pipeline_timeout_sec,
    )
    response.raise_for_status()
    data = response.json()
    print("PIPELINE", json.dumps(data, ensure_ascii=False, indent=2))

    pid = data["project_id"]
    root = settings.runs_dir / pid
    required = [
        "brief.json",
        "creative_plan.json",
        "storyboard.json",
        "images/first_frame.png",
        "images/last_frame.png",
        "videos/h3_raw.mp4",
        "final/result.mp4",
        "final_manifest.json",
    ]
    print("--- ARTIFACTS ---")
    missing = []
    for rel in required:
        path = root / rel
        ok = path.exists() and path.stat().st_size > 0
        print(("OK" if ok else "MISSING"), rel, f"size={path.stat().st_size if path.exists() else 0}")
        if not ok:
            missing.append(rel)

    print("--- PLAYABLE VIDEO ---")
    playable_ok = _assert_playable("h3_raw", root / "videos" / "h3_raw.mp4") and _assert_playable(
        "result", root / "final" / "result.mp4"
    )

    manifest = json.loads((root / "final_manifest.json").read_text(encoding="utf-8"))
    refs = manifest["brief"].get("reference_image_paths") or []
    uploads_root = (root / "uploads").resolve()
    print("--- REFS ---")
    ref_ok = True
    for ref in refs:
        rp = Path(ref).resolve()
        under = uploads_root in rp.parents or rp.parent == uploads_root
        print("ref", rp)
        print("  exists", rp.exists(), "under_uploads", under)
        if not (rp.exists() and under):
            ref_ok = False
    print("uploads", [p.name for p in (root / "uploads").glob("*")])

    print("--- GRADIO_VIA_API ---")
    summary, first, last, video, _ = run_job(
        "自由创作模式",
        demo["project_name"],
        "项目宣传片",
        demo["description"],
        demo["selling_points"],
        demo["audience"],
        "科技未来",
        "16:9",
        5,
        "缓慢推进",
        "首尾帧生视频",
        demo["constraints"],
        "",
        [str(src)],
    )
    print(summary)
    gradio_ok = all(Path(p).exists() for p in (first, last, video) if p)
    gradio_playable = _assert_playable("gradio_result", Path(video)) if video else False
    print("gradio_media_ok", gradio_ok, "gradio_playable", gradio_playable)

    evidence = {
        "project_id": pid,
        "ffmpeg": ffmpeg,
        "playable_ok": playable_ok,
        "ref_ok": ref_ok,
        "gradio_playable": gradio_playable,
        "status": data.get("status"),
        "manifest": str(root / "final_manifest.json"),
    }
    evidence_path = ROOT / "runs" / "_manual_accept" / "phase_a1_evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EVIDENCE", evidence_path)

    passed = (
        not missing
        and ref_ok
        and playable_ok
        and gradio_ok
        and gradio_playable
        and data.get("status") in {"completed", "completed_with_warnings"}
    )
    print("ACCEPTANCE", "PASS" if passed else "FAIL")
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
