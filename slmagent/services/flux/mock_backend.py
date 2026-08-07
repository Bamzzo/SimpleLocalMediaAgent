"""Mock FLUX image generation for Phase A."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from slmagent.configs.settings import get_settings
from slmagent.contracts.models import ImageJob, JobStatus, RecoverableError


class MockFluxBackend:
    def __init__(self) -> None:
        self._jobs: dict[str, ImageJob] = {}
        self._lock = threading.Lock()
        self.settings = get_settings()

    def generate_image(
        self,
        *,
        prompt: str,
        output_path: Path,
        output_name: str,
        aspect_ratio: str = "16:9",
        seed: int | None = None,
        reference_image_path: str | None = None,
    ) -> ImageJob:
        job_id = f"img_{uuid.uuid4().hex[:12]}"
        job = ImageJob(
            job_id=job_id,
            status=JobStatus.QUEUED,
            prompt=prompt,
            output_name=output_name,
            seed=seed,
            meta={
                "aspect_ratio": aspect_ratio,
                "reference_image_path": reference_image_path,
                "backend": "mock",
            },
        )
        with self._lock:
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._run,
            args=(job_id, prompt, output_path, aspect_ratio, seed),
            daemon=True,
        )
        thread.start()
        return job

    def get_job(self, job_id: str) -> ImageJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return ImageJob(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    error=RecoverableError(
                        code="JOB_NOT_FOUND",
                        message=f"未知 job_id: {job_id}",
                        retryable=False,
                        suggested_action="重新提交 generate_image",
                    ),
                )
            return job.model_copy(deep=True)

    def _run(self, job_id: str, prompt: str, output_path: Path, aspect_ratio: str, seed: int | None) -> None:
        self._update(job_id, status=JobStatus.RUNNING)
        time.sleep(self.settings.mock_job_delay_sec)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            width, height = _size_for_ratio(aspect_ratio)
            img = Image.new("RGB", (width, height), color=(12, 24, 40))
            draw = ImageDraw.Draw(img)
            draw.rectangle([40, 40, width - 40, height - 40], outline=(80, 200, 220), width=4)
            label = f"MOCK FLUX\n{output_path.name}\nseed={seed}"
            draw.multiline_text((60, 60), label, fill=(220, 240, 255), spacing=8)
            draw.multiline_text((60, 180), prompt[:240], fill=(160, 190, 210), spacing=6)
            img.save(output_path)
            self._update(job_id, status=JobStatus.SUCCEEDED, output_path=str(output_path))
        except Exception as exc:  # noqa: BLE001 — surface as recoverable job error
            self._update(
                job_id,
                status=JobStatus.FAILED,
                error=RecoverableError(
                    code="MOCK_IMAGE_FAILED",
                    message=str(exc),
                    retryable=True,
                    suggested_action="检查输出目录权限后重试",
                ),
            )

    def _update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        output_path: str | None = None,
        error: RecoverableError | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            data = job.model_dump()
            if status is not None:
                data["status"] = status
            if output_path is not None:
                data["output_path"] = output_path
            if error is not None:
                data["error"] = error
            data["updated_at"] = datetime.now(timezone.utc)
            self._jobs[job_id] = ImageJob.model_validate(data)


def _size_for_ratio(aspect_ratio: str) -> tuple[int, int]:
    mapping = {
        "16:9": (1280, 720),
        "9:16": (720, 1280),
        "1:1": (768, 768),
    }
    return mapping.get(aspect_ratio, (1280, 720))
