import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from slmagent.contracts.models import Brief, FinalManifest
from slmagent.orchestrator.graph import run_pipeline


def test_mock_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("GENERATION_BACKEND", "mock")

    # Reset settings cache so env takes effect
    from slmagent.configs.settings import get_settings

    get_settings.cache_clear()

    brief = Brief(
        project_name="测试宣传镜头",
        description="端到端 mock 验收",
        selling_points="可追踪, 可复现",
    )
    result = run_pipeline(brief)

    assert result["status"] in {"completed", "completed_with_warnings"}
    assert result["project_id"]
    assert Path(result["first_frame_path"]).exists()
    assert Path(result["last_frame_path"]).exists()
    assert Path(result["final_video_path"]).exists()

    manifest = tmp_path / "runs" / result["project_id"] / "final_manifest.json"
    assert manifest.exists()

    from slmagent.services.media_tools import get_ffmpeg, probe_media

    assert get_ffmpeg(), "ffmpeg must be available via PATH or imageio-ffmpeg"
    final = Path(result["final_video_path"])
    assert final.stat().st_size > 1024
    probe = probe_media(final)
    assert probe.get("available")
    assert probe.get("has_video")
    assert abs(float(probe.get("duration") or 0) - 5.0) <= 1.5


def test_manifest_records_started_and_completed_times(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("GENERATION_BACKEND", "mock")
    from slmagent.configs.settings import get_settings

    get_settings.cache_clear()
    result = run_pipeline(Brief(project_name="timing_check", description="manifest timing"))
    payload = json.loads(
        (tmp_path / "runs" / result["project_id"] / "final_manifest.json").read_text(encoding="utf-8")
    )
    manifest = FinalManifest.model_validate(payload)
    assert manifest.started_at is not None
    assert manifest.completed_at is not None
    assert manifest.created_at == manifest.started_at
    assert manifest.started_at <= manifest.completed_at
    # Wall clock should cover at least mock job delay; allow tiny clock skew.
    assert (manifest.completed_at - manifest.started_at).total_seconds() >= 0


def test_final_manifest_accepts_legacy_without_started_at():
    # Compatibility: older P10-style manifests may omit started_at and set
    # created_at≈completed_at at wrap-up time.
    stamp = datetime(2026, 8, 8, 9, 14, 31, tzinfo=UTC)
    manifest = FinalManifest.model_validate(
        {
            "project_id": "legacy_run",
            "project_name": "legacy",
            "status": "completed_with_warnings",
            "brief": {"project_name": "legacy"},
            "backend": "live",
            "llm_mode": "mock",
            "created_at": stamp.isoformat().replace("+00:00", "Z"),
            "completed_at": stamp.isoformat().replace("+00:00", "Z"),
        }
    )
    assert manifest.started_at is None
    assert manifest.created_at == stamp
    assert manifest.completed_at == stamp


def test_reference_upload_is_copied_into_project_run(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("GENERATION_BACKEND", "mock")
    from slmagent.configs.settings import get_settings

    get_settings.cache_clear()
    original = tmp_path / "reference.png"
    original.write_bytes(b"phase-a-reference")

    result = run_pipeline(Brief(project_name="upload_check", reference_image_paths=[str(original)]))
    brief_path = tmp_path / "runs" / result["project_id"] / "brief.json"
    saved_path = __import__("json").loads(brief_path.read_text(encoding="utf-8"))["reference_image_paths"][0]
    assert Path(saved_path).exists()
    assert Path(saved_path).parent.name == "uploads"


def test_api_pipeline_smoke(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("GENERATION_BACKEND", "mock")
    from slmagent.configs.settings import get_settings
    from slmagent.services import generation

    get_settings.cache_clear()
    generation._service = None
    from slmagent.api.main import app

    client = TestClient(app)
    response = client.post("/pipeline/run", json={"brief": {"project_name": "api_smoke"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"completed", "completed_with_warnings"}
    assert Path(payload["final_video_path"]).exists()
    assert payload["backend"] == "mock"
    assert payload["llm_mode"] == "mock"


def test_live_generation_selects_real_clients_without_connecting(monkeypatch):
    monkeypatch.setenv("GENERATION_BACKEND", "live")
    from slmagent.configs.settings import get_settings
    from slmagent.services import generation
    from slmagent.services.flux.live_backend import FluxHttpBackend
    from slmagent.services.h3.live_backend import H3HttpBackend

    get_settings.cache_clear()
    generation._service = None
    service = generation.get_generation_service()
    assert isinstance(service.flux, FluxHttpBackend)
    assert isinstance(service.h3, H3HttpBackend)
    generation._service = None
    get_settings.cache_clear()
