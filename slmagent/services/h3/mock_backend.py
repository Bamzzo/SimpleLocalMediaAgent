"""Mock MiniMax-H3 video generation for Phase A."""

from __future__ import annotations

import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from slmagent.configs.settings import get_settings
from slmagent.contracts.models import GenerationMode, JobStatus, RecoverableError, VideoJob
from slmagent.services.media_tools import get_ffmpeg


class MockH3Backend:
    def __init__(self) -> None:
        self._jobs: dict[str, VideoJob] = {}
        self._lock = threading.Lock()
        self.settings = get_settings()

    def generate_video(
        self,
        *,
        prompt: str,
        output_path: Path,
        output_name: str,
        mode: GenerationMode = GenerationMode.FL2VA,
        duration_sec: int = 5,
        resolution: str = "768p",
        first_frame_path: str | None = None,
        last_frame_path: str | None = None,
    ) -> VideoJob:
        job_id = f"vid_{uuid.uuid4().hex[:12]}"
        job = VideoJob(
            job_id=job_id,
            status=JobStatus.QUEUED,
            prompt=prompt,
            mode=mode,
            output_name=output_name,
            meta={
                "duration_sec": duration_sec,
                "resolution": resolution,
                "first_frame_path": first_frame_path,
                "last_frame_path": last_frame_path,
                "backend": "mock",
            },
        )
        with self._lock:
            self._jobs[job_id] = job
        thread = threading.Thread(
            target=self._run,
            args=(job_id, output_path, duration_sec, first_frame_path),
            daemon=True,
        )
        thread.start()
        return job

    def get_job(self, job_id: str) -> VideoJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return VideoJob(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    error=RecoverableError(
                        code="JOB_NOT_FOUND",
                        message=f"未知 job_id: {job_id}",
                        retryable=False,
                        suggested_action="重新提交 generate_video",
                    ),
                )
            return job.model_copy(deep=True)

    def _run(
        self,
        job_id: str,
        output_path: Path,
        duration_sec: int,
        first_frame_path: str | None,
    ) -> None:
        self._update(job_id, status=JobStatus.RUNNING)
        time.sleep(self.settings.mock_job_delay_sec)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            ok = _write_placeholder_mp4(output_path, duration_sec, first_frame_path)
            if not ok:
                raise RuntimeError("无法生成占位视频")
            self._update(job_id, status=JobStatus.SUCCEEDED, output_path=str(output_path))
        except Exception as exc:  # noqa: BLE001
            self._update(
                job_id,
                status=JobStatus.FAILED,
                error=RecoverableError(
                    code="MOCK_VIDEO_FAILED",
                    message=str(exc),
                    retryable=True,
                    suggested_action="安装 ffmpeg 或检查输出目录后重试",
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
            self._jobs[job_id] = VideoJob.model_validate(data)


def _write_placeholder_mp4(output_path: Path, duration_sec: int, first_frame_path: str | None) -> bool:
    """Encode a real silent H.264 mp4 via ffmpeg (system or imageio-ffmpeg bundle)."""
    ffmpeg = get_ffmpeg()
    if not ffmpeg:
        return False
    # Prefer first-frame still loop; otherwise solid color. Avoid drawtext (font deps).
    if first_frame_path and Path(first_frame_path).exists():
        cmd = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            first_frame_path,
            "-t",
            str(duration_sec),
            "-vf",
            "scale=1280:720",
            "-r",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output_path),
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0c1828:s=1280x720:d={duration_sec}",
            "-r",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output_path),
        ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1024