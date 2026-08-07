from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from slmagent.contracts.models import Brief
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
    import slmagent.services.generation as generation

    get_settings.cache_clear()
    generation._service = None
    from slmagent.api.main import app

    client = TestClient(app)
    response = client.post("/pipeline/run", json={"brief": {"project_name": "api_smoke"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"completed", "completed_with_warnings"}
    assert Path(payload["final_video_path"]).exists()


def test_live_generation_is_not_silently_mocked(monkeypatch):
    monkeypatch.setenv("GENERATION_BACKEND", "live")
    from slmagent.configs.settings import get_settings
    import slmagent.services.generation as generation

    get_settings.cache_clear()
    generation._service = None
    with pytest.raises(generation.GenerationBackendUnavailable):
        generation.get_generation_service()
