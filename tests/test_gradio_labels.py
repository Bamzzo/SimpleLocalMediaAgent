from slmagent.apps.gradio_app import (
    backend_mode_label,
    format_run_summary,
    run_result_footnote,
    ui_status_banner,
)
from slmagent.configs.settings import get_settings


def test_backend_mode_label_follows_generation_backend():
    assert backend_mode_label("live") == "live"
    assert backend_mode_label("mock") == "mock"


def test_ui_banner_is_page_config_not_run_result():
    live_banner = ui_status_banner("live", "mock")
    assert "当前页面配置" in live_banner
    assert "Backend = live" in live_banner
    assert "以 API 返回的实际值为准" in live_banner
    assert "LLM 配置：`mock`" in live_banner

    mock_banner = ui_status_banner("mock", "mock")
    assert "当前页面配置" in mock_banner
    assert "Backend = mock" in mock_banner


def test_run_footnote_distinguishes_backends():
    live_note = run_result_footnote("live", "mock")
    assert "本次 API 运行 Generation Backend=live" in live_note
    assert "Mock 占位" not in live_note

    mock_note = run_result_footnote("mock", "mock")
    assert "本次 API 运行 Generation Backend=mock" in mock_note
    assert "Mock 占位" in mock_note


def test_format_run_summary_prefers_api_modes_over_gradio_settings(monkeypatch):
    # Gradio process thinks it is mock, but the API reported a live run.
    monkeypatch.setenv("GENERATION_BACKEND", "mock")
    monkeypatch.setenv("LLM_MODE", "mock")
    get_settings.cache_clear()
    assert get_settings().generation_backend == "mock"

    summary = format_run_summary(
        {
            "status": "completed_with_warnings",
            "project_id": "p10_mismatch",
            "warnings": ["OpenCLIP 阈值待实测校准"],
            "backend": "live",
            "llm_mode": "mock",
        }
    )
    assert "backend=live" in summary
    assert "llm_mode=mock" in summary
    assert "本次 API 运行 Generation Backend=live" in summary
    assert "Generation Backend=mock" not in summary
    assert get_settings().generation_backend == "mock"
