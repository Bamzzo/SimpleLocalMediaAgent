from __future__ import annotations

from pathlib import Path

from PIL import Image

from slmagent.contracts.models import (
    Brief,
    ImageJob,
    ImagePrompt,
    JobStatus,
    Shot,
    Storyboard,
)
from slmagent.orchestrator.nodes import pipeline
from slmagent.services.project_store import ProjectStore


class _FakeLiveGeneration:
    def __init__(self) -> None:
        self.jobs: dict[str, ImageJob] = {}

    def generate_image(self, payload: dict[str, object]) -> ImageJob:
        output_path = Path(str(payload["output_path"]))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1024, 576), color=(20, 40, 60)).save(output_path)
        label = output_path.stem
        job = ImageJob(
            job_id=f"img_{label}",
            status=JobStatus.SUCCEEDED,
            output_name=output_path.name,
            output_path=str(output_path),
            meta={
                "backend": "live_flux_http",
                "remote_output_path": (
                    "/root/autodl-tmp/slmagent-live-runs/live_handoff/images/"
                    f"{output_path.name}"
                ),
            },
        )
        self.jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str) -> ImageJob:
        return self.jobs[job_id]


def test_live_image_remote_paths_flow_into_video_prompt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("GENERATION_BACKEND", "live")
    from slmagent.configs.settings import get_settings

    get_settings.cache_clear()
    fake = _FakeLiveGeneration()
    monkeypatch.setattr(pipeline, "get_generation_service", lambda: fake)
    store = ProjectStore()
    project_id, project_root = store.create_project("live_handoff")
    brief = Brief(project_name="live_handoff")
    state = {
        "project_id": project_id,
        "project_root": str(project_root),
        "brief": brief,
        "storyboard": Storyboard(
            project_name="live_handoff",
            shots=[
                Shot(
                    subject="product",
                    scene="studio",
                    composition="centered",
                    shot_size="medium",
                    action="slowly turns",
                    camera_move="slow push",
                )
            ],
        ),
        "image_prompt": ImagePrompt(
            first_frame_prompt="first frame",
            last_frame_prompt="last frame",
            aspect_ratio="16:9",
        ),
        "image_attempts": 0,
        "errors": [],
        "jobs": [],
        "warnings": [],
        "timings_sec": {},
    }

    image_result = pipeline.generate_image(state)
    prompt_result = pipeline.prepare_video_prompt({**state, **image_result})
    video_prompt = prompt_result["video_prompt"]

    assert video_prompt.first_frame_path.endswith("images\\first_frame.png")
    assert video_prompt.last_frame_path.endswith("images\\last_frame.png")
    assert video_prompt.first_frame_remote_path == (
        "/root/autodl-tmp/slmagent-live-runs/live_handoff/images/first_frame.png"
    )
    assert video_prompt.last_frame_remote_path == (
        "/root/autodl-tmp/slmagent-live-runs/live_handoff/images/last_frame.png"
    )
    get_settings.cache_clear()
