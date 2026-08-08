"""HTTP adapter for the cloud-local MiniMax-H3 FL2VA SGLang worker.

The worker accepts only cloud-local keyframe paths.  This adapter is deliberately
not wired into ``GENERATION_BACKEND=live`` until the two-worker orchestration
path has passed its independent cloud validation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from slmagent.contracts.models import (
    GenerationMode,
    JobStatus,
    RecoverableError,
    VideoJob,
)

_REMOTE_FRAME_PATH = re.compile(
    r"^/root/autodl-tmp/slmagent-live-runs/"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}/images/"
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.png$"
)
_STATUS_MAP = {
    "queued": JobStatus.QUEUED,
    "running": JobStatus.RUNNING,
    "completed": JobStatus.SUCCEEDED,
    "failed": JobStatus.FAILED,
}


class H3HttpBackend:
    """Map the verified H3 FL2VA task API to local ``VideoJob`` values."""

    def __init__(
        self,
        service_url: str,
        *,
        model_path: str = "/root/autodl-tmp/models/MiniMax-H3",
        timeout_sec: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.service_url = service_url.rstrip("/")
        self.model_path = model_path
        self.timeout_sec = timeout_sec
        self._transport = transport
        self._local_outputs: dict[str, Path] = {}
        self._submitted: dict[str, dict[str, Any]] = {}

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
        first_frame_remote_path: str | None = None,
        last_frame_remote_path: str | None = None,
        seed: int = 2101,
    ) -> VideoJob:
        del first_frame_path, last_frame_path
        validation = self._validate_request(
            mode=mode,
            duration_sec=duration_sec,
            resolution=resolution,
            first_frame_remote_path=first_frame_remote_path,
            last_frame_remote_path=last_frame_remote_path,
        )
        if validation is not None:
            return self._failed_job(
                job_id="vid_live_validation",
                code="H3_REQUEST_INVALID",
                message=validation,
                retryable=False,
                suggested_action="Use two FLUX cloud image artifacts with the fixed first-live FL2VA profile.",
                prompt=prompt,
                output_name=output_name,
            )

        payload = {
            "model": self.model_path,
            "prompt": prompt,
            "seconds": 5,
            "task": "fl2va",
            "conditions": [
                self._keyframe(first_frame_remote_path, frame_index=0),
                self._keyframe(last_frame_remote_path, frame_index=-1),
            ],
            "target": {
                "short_edge": 768,
                "aspect_ratio": "16:9",
                "duration_seconds": 5.0,
            },
            "num_outputs_per_prompt": 1,
            "num_inference_steps": 50,
            "flow_shift": 12.0,
            "audio_flow_shift": 3.0,
            "seed": seed,
        }
        try:
            response = self._request("POST", "/v1/videos", json=payload)
        except httpx.HTTPError as exc:
            return self._failed_job(
                job_id="vid_live_submit",
                code="H3_CONNECTION_FAILED",
                message=str(exc),
                retryable=True,
                suggested_action="Check the H3 SSH tunnel and cloud H3 health endpoint.",
                prompt=prompt,
                output_name=output_name,
            )
        if response.is_error:
            return self._failed_from_response(response, prompt=prompt, output_name=output_name)

        try:
            body = response.json()
            job_id = str(body["id"])
            status = _to_status(body.get("status"))
        except (KeyError, TypeError, ValueError) as exc:
            return self._failed_job(
                job_id="vid_live_submit",
                code="H3_RESPONSE_INVALID",
                message=f"H3 submit response is missing a supported id/status: {exc}",
                retryable=False,
                suggested_action="Inspect the H3 worker version and response payload.",
                prompt=prompt,
                output_name=output_name,
            )

        self._local_outputs[job_id] = output_path
        self._submitted[job_id] = {"prompt": prompt, "output_name": output_name}
        return VideoJob(
            job_id=job_id,
            status=status,
            prompt=prompt,
            mode=GenerationMode.FL2VA,
            output_name=str(body.get("output_name") or output_name),
            meta={
                "backend": "live_h3_http",
                "remote_first_frame_path": first_frame_remote_path,
                "remote_last_frame_path": last_frame_remote_path,
                "remote_message": body.get("message"),
                "remote_progress": body.get("progress"),
            },
        )

    def get_job(self, job_id: str) -> VideoJob:
        try:
            response = self._request("GET", f"/v1/videos/{job_id}")
        except httpx.HTTPError as exc:
            return self._failed_job(
                job_id=job_id,
                code="H3_CONNECTION_FAILED",
                message=str(exc),
                retryable=True,
                suggested_action="Check the H3 SSH tunnel and cloud H3 health endpoint.",
            )
        if response.is_error:
            return self._failed_from_response(response)

        try:
            body = response.json()
            status = _to_status(body.get("status"))
            returned_id = str(body["id"])
        except (KeyError, TypeError, ValueError) as exc:
            return self._failed_job(
                job_id=job_id,
                code="H3_RESPONSE_INVALID",
                message=f"H3 status response is missing a supported id/status: {exc}",
                retryable=False,
                suggested_action="Inspect the H3 worker version and response payload.",
            )

        submitted = self._submitted.get(job_id, {})
        job = VideoJob(
            job_id=returned_id,
            status=status,
            prompt=str(submitted.get("prompt") or ""),
            mode=GenerationMode.FL2VA,
            output_name=str(submitted.get("output_name") or ""),
            error=_remote_error(body.get("error")),
            meta={
                "backend": "live_h3_http",
                "remote_file_path": body.get("file_path"),
                "remote_file_paths": body.get("file_paths"),
                "remote_progress": body.get("progress"),
                "remote_size": body.get("size"),
                "remote_seconds": body.get("seconds"),
                "remote_peak_memory_mb": body.get("peak_memory_mb"),
                "remote_inference_time_s": body.get("inference_time_s"),
            },
        )
        if status == JobStatus.SUCCEEDED:
            output_path = self._local_outputs.get(job_id)
            if output_path is None:
                return self._failed_job(
                    job_id=job_id,
                    code="LOCAL_OUTPUT_PATH_UNKNOWN",
                    message="The local output path is unavailable for this live video job.",
                    retryable=False,
                    suggested_action="Submit the video again from the current SLMAgent run.",
                )
            download_error = self._download_content(job_id, output_path)
            if download_error is not None:
                return self._failed_job(
                    job_id=job_id,
                    code=download_error.code,
                    message=download_error.message,
                    retryable=download_error.retryable,
                    suggested_action=download_error.suggested_action,
                )
            job.output_path = str(output_path)
        return job

    def _download_content(self, job_id: str, output_path: Path) -> RecoverableError | None:
        try:
            response = self._request("GET", f"/v1/videos/{job_id}/content")
        except httpx.HTTPError as exc:
            return RecoverableError(
                code="H3_CONTENT_DOWNLOAD_FAILED",
                message=str(exc),
                retryable=True,
                suggested_action="Retry polling after confirming the H3 worker remains available.",
            )
        if response.is_error:
            return _response_error(response, "H3_CONTENT_DOWNLOAD_FAILED")
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("video/"):
            return RecoverableError(
                code="H3_CONTENT_TYPE_INVALID",
                message=f"Expected video content, received {content_type or 'no content type'}.",
                retryable=False,
                suggested_action="Inspect the H3 content endpoint response.",
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".part")
        temporary.write_bytes(response.content)
        if temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            return RecoverableError(
                code="H3_CONTENT_EMPTY",
                message="The H3 worker returned an empty video response.",
                retryable=True,
                suggested_action="Retry polling after checking the completed remote job.",
            )
        temporary.replace(output_path)
        return None

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(
            base_url=self.service_url,
            timeout=self.timeout_sec,
            transport=self._transport,
            trust_env=False,
        ) as client:
            return client.request(method, path, **kwargs)

    @staticmethod
    def _keyframe(remote_path: str | None, *, frame_index: int) -> dict[str, object]:
        assert remote_path is not None
        return {
            "type": "image",
            "uri": f"file://{quote(remote_path, safe='/')}",
            "role": "keyframe",
            "frame_index": frame_index,
        }

    @staticmethod
    def _validate_request(
        *,
        mode: GenerationMode,
        duration_sec: int,
        resolution: str,
        first_frame_remote_path: str | None,
        last_frame_remote_path: str | None,
    ) -> str | None:
        if mode != GenerationMode.FL2VA:
            return "H3 live mode currently supports FL2VA only."
        if duration_sec != 5 or resolution != "768p":
            return "H3 live mode currently supports exactly 5 seconds at 768p."
        for label, remote_path in (
            ("first_frame_remote_path", first_frame_remote_path),
            ("last_frame_remote_path", last_frame_remote_path),
        ):
            if not remote_path or not _REMOTE_FRAME_PATH.fullmatch(remote_path):
                return f"{label} must be a PNG in the cloud slmagent-live-runs image workspace."
        return None

    @staticmethod
    def _failed_job(
        *,
        job_id: str,
        code: str,
        message: str,
        retryable: bool,
        suggested_action: str,
        prompt: str = "",
        output_name: str = "",
    ) -> VideoJob:
        return VideoJob(
            job_id=job_id,
            status=JobStatus.FAILED,
            prompt=prompt,
            mode=GenerationMode.FL2VA,
            output_name=output_name,
            error=RecoverableError(
                code=code,
                message=message,
                retryable=retryable,
                suggested_action=suggested_action,
            ),
            meta={"backend": "live_h3_http"},
        )

    def _failed_from_response(
        self,
        response: httpx.Response,
        *,
        prompt: str = "",
        output_name: str = "",
    ) -> VideoJob:
        error = _response_error(response, "H3_REQUEST_FAILED")
        return self._failed_job(
            job_id="vid_live_request",
            prompt=prompt,
            output_name=output_name,
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            suggested_action=error.suggested_action,
        )


def _to_status(value: object) -> JobStatus:
    try:
        return _STATUS_MAP[str(value)]
    except KeyError as exc:
        raise ValueError(f"Unsupported H3 worker job status: {value!r}") from exc


def _remote_error(value: object) -> RecoverableError | None:
    if not isinstance(value, dict):
        return None
    return RecoverableError(
        code=str(value.get("code") or "H3_REMOTE_ERROR"),
        message=str(value.get("message") or "H3 worker reported an unknown error."),
        retryable=bool(value.get("retryable")),
        suggested_action=str(value.get("suggested_action") or "Inspect the H3 worker logs."),
    )


def _response_error(response: httpx.Response, fallback_code: str) -> RecoverableError:
    try:
        body = response.json()
    except ValueError:
        body = {}
    remote = body.get("error") if isinstance(body, dict) else None
    if isinstance(remote, dict):
        return _remote_error(remote) or RecoverableError(
            code=fallback_code,
            message=f"H3 worker returned HTTP {response.status_code}.",
            retryable=response.status_code >= 500,
            suggested_action="Inspect the H3 worker response and logs.",
        )
    return RecoverableError(
        code=fallback_code,
        message=f"H3 worker returned HTTP {response.status_code}.",
        retryable=response.status_code >= 500,
        suggested_action="Inspect the H3 worker response and logs.",
    )
