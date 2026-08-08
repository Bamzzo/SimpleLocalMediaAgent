from __future__ import annotations

import json

import httpx

from slmagent.contracts.models import GenerationMode, JobStatus, VideoPrompt
from slmagent.services.h3.live_backend import H3HttpBackend

FIRST = "/root/autodl-tmp/slmagent-live-runs/run_001/images/first_frame.png"
LAST = "/root/autodl-tmp/slmagent-live-runs/run_001/images/last_frame.png"


def _backend(handler) -> H3HttpBackend:
    return H3HttpBackend("http://tunnel", transport=httpx.MockTransport(handler))


def test_submit_uses_verified_fl2va_contract(tmp_path) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "vid_live_001", "status": "queued", "progress": 0})

    output = tmp_path / "run_001" / "videos" / "h3_raw.mp4"
    job = _backend(handler).generate_video(
        prompt="continue naturally",
        output_path=output,
        output_name=output.name,
        first_frame_remote_path=FIRST,
        last_frame_remote_path=LAST,
        seed=2101,
    )

    assert job.status == JobStatus.QUEUED
    assert seen["path"] == "/v1/videos"
    assert seen["json"] == {
        "model": "/root/autodl-tmp/models/MiniMax-H3",
        "prompt": "continue naturally",
        "seconds": 5,
        "task": "fl2va",
        "conditions": [
            {"type": "image", "uri": f"file://{FIRST}", "role": "keyframe", "frame_index": 0},
            {"type": "image", "uri": f"file://{LAST}", "role": "keyframe", "frame_index": -1},
        ],
        "target": {"short_edge": 768, "aspect_ratio": "16:9", "duration_seconds": 5.0},
        "num_outputs_per_prompt": 1,
        "num_inference_steps": 50,
        "flow_shift": 12.0,
        "audio_flow_shift": 3.0,
        "seed": 2101,
    }


def test_completed_job_downloads_mp4_and_preserves_remote_metadata(tmp_path) -> None:
    output = tmp_path / "run_002" / "videos" / "h3_raw.mp4"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/videos":
            return httpx.Response(200, json={"id": "vid_live_002", "status": "queued"})
        if request.url.path == "/v1/videos/vid_live_002":
            return httpx.Response(
                200,
                json={
                    "id": "vid_live_002",
                    "status": "completed",
                    "progress": 100,
                    "file_path": "outputs/vid_live_002.mp4",
                    "file_paths": ["/root/autodl-tmp/sglang/outputs/vid_live_002.mp4"],
                    "peak_memory_mb": 23830.0,
                    "inference_time_s": 796.57,
                },
            )
        if request.url.path == "/v1/videos/vid_live_002/content":
            return httpx.Response(200, content=b"mp4-bytes", headers={"content-type": "video/mp4"})
        raise AssertionError(request.url.path)

    backend = _backend(handler)
    backend.generate_video(
        prompt="test",
        output_path=output,
        output_name=output.name,
        first_frame_remote_path=FIRST.replace("run_001", "run_002"),
        last_frame_remote_path=LAST.replace("run_001", "run_002"),
    )
    job = backend.get_job("vid_live_002")

    assert job.status == JobStatus.SUCCEEDED
    assert job.output_path == str(output)
    assert output.read_bytes() == b"mp4-bytes"
    assert job.meta["remote_file_paths"] == ["/root/autodl-tmp/sglang/outputs/vid_live_002.mp4"]
    assert job.meta["remote_inference_time_s"] == 796.57


def test_invalid_live_scope_fails_without_http_request(tmp_path) -> None:
    backend = _backend(lambda request: (_ for _ in ()).throw(AssertionError(request.url.path)))
    job = backend.generate_video(
        prompt="test",
        output_path=tmp_path / "video.mp4",
        output_name="video.mp4",
        mode=GenerationMode.T2V,
        first_frame_remote_path=FIRST,
        last_frame_remote_path=LAST,
    )

    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert job.error.code == "H3_REQUEST_INVALID"
    assert job.error.retryable is False


def test_video_prompt_preserves_remote_keyframe_paths() -> None:
    prompt = VideoPrompt(
        prompt="continue naturally",
        first_frame_remote_path=FIRST,
        last_frame_remote_path=LAST,
    )

    assert prompt.first_frame_remote_path == FIRST
    assert prompt.last_frame_remote_path == LAST


def test_h3_busy_error_is_structured(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "error": {
                    "code": "GPU_BUSY",
                    "message": "a video job is already active",
                    "retryable": True,
                    "suggested_action": "poll the active job before retrying",
                }
            },
        )

    job = _backend(handler).generate_video(
        prompt="test",
        output_path=tmp_path / "video.mp4",
        output_name="video.mp4",
        first_frame_remote_path=FIRST,
        last_frame_remote_path=LAST,
    )

    assert job.status == JobStatus.FAILED
    assert job.error is not None
    assert job.error.code == "GPU_BUSY"
    assert job.error.retryable is True


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
    response = H3HttpBackend("http://127.0.0.1:13010")._request("GET", "/health")

    assert response.status_code == 200
    assert captured["trust_env"] is False
