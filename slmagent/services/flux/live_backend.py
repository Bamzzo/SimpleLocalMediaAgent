"""HTTP adapter for the cloud-local FLUX task service.

This client implements the P6C contract. It is intentionally not wired into
``GENERATION_BACKEND=live`` until the H3 adapter and shared cloud artifact flow
are implemented as well.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from slmagent.contracts.models import ImageJob, JobStatus, RecoverableError

_REMOTE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_STATUS_MAP = {
    "queued": JobStatus.QUEUED,
    "running": JobStatus.RUNNING,
    "completed": JobStatus.SUCCEEDED,
    "failed": JobStatus.FAILED,
}


class FluxHttpBackend:
    """Maps the cloud FLUX worker contract into local ``ImageJob`` values."""

    def __init__(
        self,
        service_url: str,
        *,
        timeout_sec: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.service_url = service_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self._transport = transport
        self._local_outputs: dict[str, Path] = {}

    def generate_image(
        self,
        *,
        prompt: str,
        output_path: Path,
        output_name: str,
        aspect_ratio: str = "16:9",
        seed: int | None = None,
        reference_image_path: str | None = None,
        remote_run_id: str | None = None,
    ) -> ImageJob:
        del reference_image_path  # FLUX P6C contract currently supports text-to-image only.
        remote_run_id = remote_run_id or self._remote_run_id_for(output_path)
        width, height = _dimensions_for_ratio(aspect_ratio)
        payload = {
            "prompt": prompt,
            "remote_run_id": remote_run_id,
            "output_name": output_name,
            "seed": 0 if seed is None else seed,
            "width": width,
            "height": height,
            "num_inference_steps": 4,
            "guidance_scale": 1.0,
        }
        try:
            response = self._request("POST", "/v1/images/generations", json=payload)
        except httpx.HTTPError as exc:
            return self._failed_job(
                job_id="img_live_submit",
                prompt=prompt,
                output_name=output_name,
                seed=seed,
                code="FLUX_CONNECTION_FAILED",
                message=str(exc),
                retryable=True,
                suggested_action="Check the SSH tunnel and FLUX worker health endpoint.",
            )

        if response.is_error:
            return self._failed_from_response(response, prompt, output_name, seed)

        body = response.json()
        job_id = str(body["job_id"])
        self._local_outputs[job_id] = output_path
        return ImageJob(
            job_id=job_id,
            status=_to_status(body.get("status")),
            prompt=prompt,
            output_name=str(body.get("output_name") or output_name),
            seed=seed,
            meta={
                "backend": "live_flux_http",
                "remote_run_id": str(body.get("remote_run_id") or remote_run_id),
                "remote_message": str(body.get("message") or ""),
            },
        )

    def get_job(self, job_id: str) -> ImageJob:
        try:
            response = self._request("GET", f"/v1/images/{job_id}")
        except httpx.HTTPError as exc:
            return self._failed_job(
                job_id=job_id,
                code="FLUX_CONNECTION_FAILED",
                message=str(exc),
                retryable=True,
                suggested_action="Check the SSH tunnel and FLUX worker health endpoint.",
            )

        if response.is_error:
            return self._failed_from_response(response)

        body = response.json()
        status = _to_status(body.get("status"))
        job = ImageJob(
            job_id=str(body["job_id"]),
            status=status,
            output_name=str(body.get("output_name") or ""),
            seed=body.get("seed"),
            error=_remote_error(body.get("error")),
            meta={
                "backend": "live_flux_http",
                "remote_run_id": str(body.get("remote_run_id") or ""),
                "remote_output_path": body.get("output_path"),
                "width": body.get("width"),
                "height": body.get("height"),
                "num_inference_steps": body.get("num_inference_steps"),
                "guidance_scale": body.get("guidance_scale"),
                "wall_clock_seconds": body.get("wall_clock_seconds"),
            },
        )
        if status == JobStatus.SUCCEEDED:
            output_path = self._local_outputs.get(job_id)
            if output_path is None:
                return self._failed_job(
                    job_id=job_id,
                    code="LOCAL_OUTPUT_PATH_UNKNOWN",
                    message="The local output path is unavailable for this live image job.",
                    retryable=False,
                    suggested_action="Submit the image again from the current SLMAgent run.",
                )
            download_error = self._download_content(job_id, output_path)
            if download_error:
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
            response = self._request("GET", f"/v1/images/{job_id}/content")
        except httpx.HTTPError as exc:
            return RecoverableError(
                code="FLUX_CONTENT_DOWNLOAD_FAILED",
                message=str(exc),
                retryable=True,
                suggested_action="Retry after confirming the FLUX worker remains available.",
            )
        if response.is_error:
            return _response_error(response, "FLUX_CONTENT_DOWNLOAD_FAILED")
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/png"):
            return RecoverableError(
                code="FLUX_CONTENT_TYPE_INVALID",
                message=f"Expected image/png, received {content_type or 'no content type'}.",
                retryable=False,
                suggested_action="Inspect the FLUX worker content endpoint response.",
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".part")
        temporary.write_bytes(response.content)
        if temporary.stat().st_size == 0:
            temporary.unlink(missing_ok=True)
            return RecoverableError(
                code="FLUX_CONTENT_EMPTY",
                message="The FLUX worker returned an empty PNG response.",
                retryable=True,
                suggested_action="Retry after checking the completed remote job.",
            )
        temporary.replace(output_path)
        return None

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(
            base_url=self.service_url,
            timeout=self.timeout_sec,
            transport=self._transport,
            # The endpoint is an SSH local forward.  It must never inherit a
            # workstation-wide HTTP proxy, which cannot reach 127.0.0.1 on
            # this machine and may return a misleading 502 before SSH sees it.
            trust_env=False,
        ) as client:
            return client.request(method, path, **kwargs)

    @staticmethod
    def _remote_run_id_for(output_path: Path) -> str:
        # Local run layout is runs/<project_id>/images/<file>.png.
        candidate = output_path.parent.parent.name
        if not _REMOTE_RUN_ID.fullmatch(candidate):
            raise ValueError(f"Cannot derive a safe remote_run_id from {output_path}")
        return candidate

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
        seed: int | None = None,
    ) -> ImageJob:
        return ImageJob(
            job_id=job_id,
            status=JobStatus.FAILED,
            prompt=prompt,
            output_name=output_name,
            seed=seed,
            error=RecoverableError(
                code=code,
                message=message,
                retryable=retryable,
                suggested_action=suggested_action,
            ),
            meta={"backend": "live_flux_http"},
        )

    def _failed_from_response(
        self,
        response: httpx.Response,
        prompt: str = "",
        output_name: str = "",
        seed: int | None = None,
    ) -> ImageJob:
        error = _response_error(response, "FLUX_REQUEST_FAILED")
        return self._failed_job(
            job_id="img_live_request",
            prompt=prompt,
            output_name=output_name,
            seed=seed,
            code=error.code,
            message=error.message,
            retryable=error.retryable,
            suggested_action=error.suggested_action,
        )


def _dimensions_for_ratio(aspect_ratio: str) -> tuple[int, int]:
    return {
        "16:9": (1024, 576),
        "9:16": (576, 1024),
        "1:1": (1024, 1024),
    }.get(aspect_ratio, (1024, 576))


def _to_status(value: object) -> JobStatus:
    try:
        return _STATUS_MAP[str(value)]
    except KeyError as exc:
        raise ValueError(f"Unsupported FLUX worker job status: {value!r}") from exc


def _remote_error(value: object) -> RecoverableError | None:
    if not isinstance(value, dict):
        return None
    return RecoverableError(
        code=str(value.get("code") or "FLUX_REMOTE_ERROR"),
        message=str(value.get("message") or "FLUX worker reported an unknown error."),
        retryable=bool(value.get("retryable")),
        suggested_action=str(value.get("suggested_action") or "Inspect the FLUX worker logs."),
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
            message=f"FLUX worker returned HTTP {response.status_code}.",
            retryable=response.status_code >= 500,
        )
    return RecoverableError(
        code=fallback_code,
        message=f"FLUX worker returned HTTP {response.status_code}.",
        retryable=response.status_code >= 500,
        suggested_action="Inspect the FLUX worker response and logs.",
    )
