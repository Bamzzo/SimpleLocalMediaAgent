from __future__ import annotations

import httpx

from slmagent.contracts.models import JobStatus
from slmagent.services.flux.live_backend import FluxHttpBackend


def test_tunnel_requests_ignore_workstation_proxy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def request(self, method: str, path: str, **kwargs) -> httpx.Response:
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    response = FluxHttpBackend("http://127.0.0.1:18001")._request("GET", "/health")

    assert response.status_code == 200
    assert captured["trust_env"] is False


def test_submit_uses_p6c_contract_and_maps_queued_job(tmp_path) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["json"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "job_id": "img_live_001",
                "status": "queued",
                "remote_run_id": "run_001",
                "output_name": "first_frame.png",
                "message": "queued",
            },
        )

    backend = FluxHttpBackend("http://tunnel", transport=httpx.MockTransport(handler))
    output = tmp_path / "run_001" / "images" / "first_frame.png"

    job = backend.generate_image(
        prompt="test prompt",
        output_path=output,
        output_name="first_frame.png",
        aspect_ratio="16:9",
        seed=7,
    )

    assert job.status == JobStatus.QUEUED
    assert job.job_id == "img_live_001"
    assert seen["path"] == "/v1/images/generations"
    assert seen["json"] == {
        "prompt": "test prompt",
        "remote_run_id": "run_001",
        "output_name": "first_frame.png",
        "seed": 7,
        "width": 1024,
        "height": 576,
        "num_inference_steps": 4,
        "guidance_scale": 1.0,
    }


def test_completed_job_downloads_png_to_local_run(tmp_path) -> None:
    output = tmp_path / "run_002" / "images" / "last_frame.png"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/images/generations":
            return httpx.Response(
                200,
                json={
                    "job_id": "img_live_002",
                    "status": "queued",
                    "remote_run_id": "run_002",
                    "output_name": "last_frame.png",
                    "message": "queued",
                },
            )
        if request.url.path == "/v1/images/img_live_002":
            return httpx.Response(
                200,
                json={
                    "job_id": "img_live_002",
                    "status": "completed",
                    "remote_run_id": "run_002",
                    "output_name": "last_frame.png",
                    "output_path": "/root/autodl-tmp/slmagent-live-runs/run_002/images/last_frame.png",
                    "seed": 0,
                    "width": 1024,
                    "height": 1024,
                    "num_inference_steps": 4,
                    "guidance_scale": 1.0,
                    "created_at": "2026-08-08T00:00:00Z",
                    "started_at": "2026-08-08T00:00:01Z",
                    "finished_at": "2026-08-08T00:00:10Z",
                    "wall_clock_seconds": 9.0,
                    "error": None,
                },
            )
        if request.url.path == "/v1/images/img_live_002/content":
            return httpx.Response(200, content=b"png-bytes", headers={"content-type": "image/png"})
        raise AssertionError(request.url.path)

    backend = FluxHttpBackend("http://tunnel", transport=httpx.MockTransport(handler))
    backend.generate_image(prompt="test", output_path=output, output_name=output.name, aspect_ratio="1:1")

    job = backend.get_job("img_live_002")

    assert job.status == JobStatus.SUCCEEDED
    assert job.output_path == str(output)
    assert output.read_bytes() == b"png-bytes"
    assert job.meta["remote_output_path"].endswith("last_frame.png")


def test_worker_busy_error_is_structured(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "GPU_BUSY",
                    "message": "one queued job already exists",
                    "retryable": True,
                    "suggested_action": "poll the active job before retrying",
                }
            },
        )

    backend = FluxHttpBackend("http://tunnel", transport=httpx.MockTransport(handler))
    job = backend.generate_image(
        prompt="test",
        output_path=tmp_path / "run_003" / "images" / "frame.png",
        output_name="frame.png",
    )

    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert job.error.code == "GPU_BUSY"
    assert job.error.retryable is True
