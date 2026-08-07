"""Explicit pipeline nodes for the P0 single-agent workflow."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from slmagent.configs.settings import get_settings
from slmagent.contracts.models import (
    Brief,
    ErrorRecord,
    FinalManifest,
    ImagePrompt,
    JobStatus,
    VideoPrompt,
)
from slmagent.orchestrator.state import AgentState
from slmagent.services.generation import get_generation_service
from slmagent.services.llm.client import LLMClient
from slmagent.services.postprocess.ffmpeg_export import export_final
from slmagent.services.project_store import ProjectStore
from slmagent.services.quality.checks import check_image, check_video
from slmagent.skills.flux_image_production.prompting import build_image_prompt
from slmagent.skills.h3_video_production.prompting import build_video_prompt


def receive_input(state: AgentState) -> dict[str, Any]:
    store = ProjectStore()
    brief = state["brief"]
    if isinstance(brief, dict):
        brief = Brief.model_validate(brief)
    project_id = state.get("project_id")
    project_root = state.get("project_root")
    if not project_id or not project_root:
        project_id, root = store.create_project(brief.project_name)
        project_root = str(root)

    # Preserve uploads inside the project run.  This makes a completed run
    # self-contained and allows a later service restart to inspect its inputs.
    saved_references: list[str] = []
    for reference in brief.reference_image_paths:
        source = Path(reference)
        if source.is_file():
            saved_references.append(str(store.save_upload(project_id, source)))
    if saved_references:
        brief = brief.model_copy(update={"reference_image_paths": saved_references})
    store.write_json(project_id, "brief.json", brief)
    settings = get_settings()
    return {
        "project_id": project_id,
        "project_root": project_root,
        "brief": brief,
        "jobs": [],
        "quality_reports": [],
        "errors": [],
        "warnings": [],
        "timings_sec": {},
        "image_attempts": 0,
        "video_attempts": 0,
        "backend": settings.generation_backend,
        "llm_mode": settings.resolved_llm_mode(),
        "current_node": "RECEIVE_INPUT",
        "status": "running",
    }


def plan_creative(state: AgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    llm = LLMClient()
    brief = state["brief"]
    creative = llm.plan_creative(brief)
    store = ProjectStore()
    store.write_json(state["project_id"], "creative_plan.json", creative)
    timings = dict(state.get("timings_sec") or {})
    timings["PLAN_CREATIVE"] = round(time.perf_counter() - t0, 3)
    return {
        "creative_plan": creative,
        "timings_sec": timings,
        "current_node": "PLAN_CREATIVE",
        "llm_mode": llm.mode,
    }


def build_storyboard(state: AgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    llm = LLMClient()
    storyboard = llm.build_storyboard(state["brief"], state["creative_plan"])
    store = ProjectStore()
    store.write_json(state["project_id"], "storyboard.json", storyboard)
    timings = dict(state.get("timings_sec") or {})
    timings["BUILD_STORYBOARD"] = round(time.perf_counter() - t0, 3)
    return {
        "storyboard": storyboard,
        "timings_sec": timings,
        "current_node": "BUILD_STORYBOARD",
    }


def prepare_image_prompt(state: AgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    image_prompt = build_image_prompt(state["brief"], state["storyboard"])
    store = ProjectStore()
    store.write_json(state["project_id"], "prompts/image_prompt.json", image_prompt)
    timings = dict(state.get("timings_sec") or {})
    timings["PREPARE_IMAGE_PROMPT"] = round(time.perf_counter() - t0, 3)
    return {
        "image_prompt": image_prompt,
        "timings_sec": timings,
        "current_node": "PREPARE_IMAGE_PROMPT",
    }


def _wait_job(job_id: str, timeout_sec: float = 60.0) -> Any:
    gen = get_generation_service()
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        job = gen.get_job(job_id)
        if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            return job
        time.sleep(0.15)
    job = gen.get_job(job_id)
    return job


def generate_image(state: AgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    settings = get_settings()
    store = ProjectStore()
    project_id = state["project_id"]
    prompt: ImagePrompt = state["image_prompt"]
    if isinstance(prompt, dict):
        prompt = ImagePrompt.model_validate(prompt)

    attempts = int(state.get("image_attempts") or 0)
    errors = list(state.get("errors") or [])
    jobs = list(state.get("jobs") or [])
    warnings = list(state.get("warnings") or [])
    first_path = store.path(project_id, "images", "first_frame.png")
    last_path = store.path(project_id, "images", "last_frame.png")
    gen = get_generation_service()

    ref = prompt.reference_image_paths[0] if prompt.reference_image_paths else None
    seed = prompt.seed

    for label, text, out in (
        ("first_frame", prompt.first_frame_prompt, first_path),
        ("last_frame", prompt.last_frame_prompt, last_path),
    ):
        attempt_local = 0
        while attempt_local <= settings.max_retries_per_stage:
            job = gen.generate_image(
                {
                    "prompt": text,
                    "output_path": str(out),
                    "output_name": out.name,
                    "aspect_ratio": prompt.aspect_ratio,
                    "seed": None if seed is None else seed + (0 if label == "first_frame" else 1),
                    "reference_image_path": ref,
                }
            )
            done = _wait_job(job.job_id)
            jobs.append(done.model_dump(mode="json"))
            if done.status == JobStatus.SUCCEEDED:
                break
            attempt_local += 1
            attempts += 1
            err = done.error
            record = ErrorRecord(
                stage="GENERATE_IMAGE",
                attempt=attempt_local,
                code=err.code if err else "UNKNOWN",
                message=err.message if err else "image generation failed",
                retryable=bool(err.retryable) if err else True,
                suggested_action=err.suggested_action if err else "降低参数后重试",
            )
            errors.append(record)
            store.append_error(project_id, record.model_dump(mode="json"))
            if attempt_local > settings.max_retries_per_stage:
                warnings.append(f"{label} 达到重试上限")
                break

    store.write_json(project_id, "jobs.json", jobs)
    timings = dict(state.get("timings_sec") or {})
    timings["GENERATE_IMAGE"] = round(time.perf_counter() - t0, 3)
    return {
        "first_frame_path": str(first_path) if first_path.exists() else None,
        "last_frame_path": str(last_path) if last_path.exists() else None,
        "jobs": jobs,
        "errors": errors,
        "warnings": warnings,
        "image_attempts": attempts,
        "timings_sec": timings,
        "current_node": "GENERATE_IMAGE",
    }


def check_image_node(state: AgentState) -> dict[str, Any]:
    reports = list(state.get("quality_reports") or [])
    warnings = list(state.get("warnings") or [])
    store = ProjectStore()
    for key in ("first_frame_path", "last_frame_path"):
        p = state.get(key)
        if not p:
            continue
        report = check_image(Path(p), expected_aspect=state["brief"].aspect_ratio.value)
        reports.append(report)
        warnings.extend(report.warnings)
    store.write_json(state["project_id"], "quality_report.json", [r.model_dump(mode="json") for r in reports])
    return {
        "quality_reports": reports,
        "warnings": warnings,
        "current_node": "CHECK_IMAGE",
    }


def prepare_video_prompt(state: AgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    video_prompt = build_video_prompt(
        state["brief"],
        state["storyboard"],
        first_frame_path=state.get("first_frame_path"),
        last_frame_path=state.get("last_frame_path"),
    )
    store = ProjectStore()
    store.write_json(state["project_id"], "prompts/video_prompt.json", video_prompt)
    timings = dict(state.get("timings_sec") or {})
    timings["PREPARE_VIDEO_PROMPT"] = round(time.perf_counter() - t0, 3)
    return {
        "video_prompt": video_prompt,
        "timings_sec": timings,
        "current_node": "PREPARE_VIDEO_PROMPT",
    }


def generate_video(state: AgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    settings = get_settings()
    store = ProjectStore()
    project_id = state["project_id"]
    prompt: VideoPrompt = state["video_prompt"]
    if isinstance(prompt, dict):
        prompt = VideoPrompt.model_validate(prompt)

    attempts = int(state.get("video_attempts") or 0)
    errors = list(state.get("errors") or [])
    jobs = list(state.get("jobs") or [])
    warnings = list(state.get("warnings") or [])
    out = store.path(project_id, "videos", "h3_raw.mp4")
    gen = get_generation_service()

    attempt_local = 0
    succeeded = False
    while attempt_local <= settings.max_retries_per_stage:
        job = gen.generate_video(
            {
                "prompt": prompt.prompt,
                "output_path": str(out),
                "output_name": out.name,
                "mode": prompt.mode,
                "duration_sec": prompt.duration_sec,
                "resolution": prompt.resolution,
                "first_frame_path": prompt.first_frame_path,
                "last_frame_path": prompt.last_frame_path,
            }
        )
        done = _wait_job(job.job_id, timeout_sec=120.0)
        jobs.append(done.model_dump(mode="json"))
        if done.status == JobStatus.SUCCEEDED:
            succeeded = True
            break
        attempt_local += 1
        attempts += 1
        err = done.error
        record = ErrorRecord(
            stage="GENERATE_VIDEO",
            attempt=attempt_local,
            code=err.code if err else "UNKNOWN",
            message=err.message if err else "video generation failed",
            retryable=bool(err.retryable) if err else True,
            suggested_action=err.suggested_action if err else "降低分辨率或缩短时长后重试",
        )
        errors.append(record)
        store.append_error(project_id, record.model_dump(mode="json"))
        if attempt_local > settings.max_retries_per_stage:
            warnings.append("视频生成达到重试上限")
            break

    store.write_json(project_id, "jobs.json", jobs)
    timings = dict(state.get("timings_sec") or {})
    timings["GENERATE_VIDEO"] = round(time.perf_counter() - t0, 3)
    return {
        "raw_video_path": str(out) if succeeded and out.exists() else None,
        "jobs": jobs,
        "errors": errors,
        "warnings": warnings,
        "video_attempts": attempts,
        "timings_sec": timings,
        "current_node": "GENERATE_VIDEO",
    }


def check_video_node(state: AgentState) -> dict[str, Any]:
    reports = list(state.get("quality_reports") or [])
    warnings = list(state.get("warnings") or [])
    raw = state.get("raw_video_path")
    if raw:
        report = check_video(Path(raw), expected_duration_sec=state["brief"].duration_sec)
        reports.append(report)
        warnings.extend(report.warnings)
    else:
        warnings.append("无原始视频可检查")
    store = ProjectStore()
    store.write_json(state["project_id"], "quality_report.json", [r.model_dump(mode="json") for r in reports])
    return {
        "quality_reports": reports,
        "warnings": warnings,
        "current_node": "CHECK_VIDEO",
    }


def postprocess(state: AgentState) -> dict[str, Any]:
    t0 = time.perf_counter()
    store = ProjectStore()
    project_id = state["project_id"]
    final_path = store.path(project_id, "final", "result.mp4")
    raw = state.get("raw_video_path")
    warnings = list(state.get("warnings") or [])
    if raw and Path(raw).exists():
        export_final(Path(raw), final_path)
    else:
        warnings.append("跳过后期：缺少原始视频")
        final_path = Path("")
    timings = dict(state.get("timings_sec") or {})
    timings["POSTPROCESS"] = round(time.perf_counter() - t0, 3)
    return {
        "final_video_path": str(final_path) if final_path and final_path.exists() else None,
        "warnings": warnings,
        "timings_sec": timings,
        "current_node": "POSTPROCESS",
    }


def complete(state: AgentState) -> dict[str, Any]:
    from datetime import datetime, timezone

    warnings = list(state.get("warnings") or [])
    has_final = bool(state.get("final_video_path"))
    status = "completed" if has_final and not warnings else (
        "completed_with_warnings" if has_final else "failed"
    )
    manifest = FinalManifest(
        project_id=state["project_id"],
        project_name=state["brief"].project_name,
        status=status,
        brief=state["brief"],
        creative_plan=state.get("creative_plan"),
        storyboard=state.get("storyboard"),
        image_prompt=state.get("image_prompt"),
        video_prompt=state.get("video_prompt"),
        first_frame_path=state.get("first_frame_path"),
        last_frame_path=state.get("last_frame_path"),
        raw_video_path=state.get("raw_video_path"),
        final_video_path=state.get("final_video_path"),
        jobs=list(state.get("jobs") or []),
        quality_reports=list(state.get("quality_reports") or []),
        errors=list(state.get("errors") or []),
        timings_sec=dict(state.get("timings_sec") or {}),
        backend=state.get("backend") or "mock",
        llm_mode=state.get("llm_mode") or "mock",
        completed_at=datetime.now(timezone.utc),
    )
    store = ProjectStore()
    store.write_json(state["project_id"], "final_manifest.json", manifest)
    return {
        "status": status,
        "current_node": "COMPLETE",
    }
