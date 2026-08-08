"""Unified async generation facade used by FastAPI tools and orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from slmagent.configs.settings import get_settings
from slmagent.contracts.models import GenerationMode, ImageJob, JobStatus, VideoJob
from slmagent.services.flux.live_backend import FluxHttpBackend
from slmagent.services.flux.mock_backend import MockFluxBackend
from slmagent.services.h3.live_backend import H3HttpBackend
from slmagent.services.h3.mock_backend import MockH3Backend


class GenerationService:
    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.generation_backend == "live":
            self.flux = FluxHttpBackend(self.settings.flux_service_url)
            self.h3 = H3HttpBackend(
                self.settings.h3_service_url,
                model_path=self.settings.h3_model_path,
            )
        else:
            self.flux = MockFluxBackend()
            self.h3 = MockH3Backend()
        self._job_kinds: dict[str, str] = {}

    def generate_image(self, payload: dict[str, Any]) -> ImageJob:
        # Live FLUX HTTP client will replace mock in Phase B.
        job = self.flux.generate_image(
            prompt=payload["prompt"],
            output_path=Path(payload["output_path"]),
            output_name=payload.get("output_name", "image.png"),
            aspect_ratio=payload.get("aspect_ratio", "16:9"),
            seed=payload.get("seed"),
            reference_image_path=payload.get("reference_image_path"),
        )
        self._job_kinds[job.job_id] = "image"
        return job

    def generate_video(self, payload: dict[str, Any]) -> VideoJob:
        mode = payload.get("mode", GenerationMode.FL2VA)
        if isinstance(mode, str):
            mode = GenerationMode(mode)
        job = self.h3.generate_video(
            prompt=payload["prompt"],
            output_path=Path(payload["output_path"]),
            output_name=payload.get("output_name", "video.mp4"),
            mode=mode,
            duration_sec=int(payload.get("duration_sec", 5)),
            resolution=payload.get("resolution", "768p"),
            first_frame_path=payload.get("first_frame_path"),
            last_frame_path=payload.get("last_frame_path"),
            first_frame_remote_path=payload.get("first_frame_remote_path"),
            last_frame_remote_path=payload.get("last_frame_remote_path"),
        )
        self._job_kinds[job.job_id] = "video"
        return job

    def get_job(self, job_id: str) -> ImageJob | VideoJob:
        kind = self._job_kinds.get(job_id)
        if kind == "image":
            return self.flux.get_job(job_id)
        if kind == "video":
            return self.h3.get_job(job_id)
        if job_id.startswith("img_"):
            return self.flux.get_job(job_id)
        if job_id.startswith("vid_"):
            return self.h3.get_job(job_id)
        # Unknown prefix: try both
        img = self.flux.get_job(job_id)
        if img.status != JobStatus.FAILED or (img.error and img.error.code != "JOB_NOT_FOUND"):
            return img
        return self.h3.get_job(job_id)


_service: GenerationService | None = None


def get_generation_service() -> GenerationService:
    global _service
    if _service is None:
        _service = GenerationService()
    return _service
