"""Runtime settings from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_mode: Literal["mock", "live"] = "mock"

    generation_backend: Literal["mock", "live"] = "mock"
    flux_service_url: str = "http://127.0.0.1:8001"
    h3_service_url: str = "http://127.0.0.1:8002"

    runs_dir: Path = Field(default=ROOT / "runs")
    models_dir: Path = Path("/data/models")

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_base_url: str = "http://127.0.0.1:8000"
    api_pipeline_timeout_sec: float = 180.0
    gradio_host: str = "127.0.0.1"
    gradio_port: int = 7860

    max_retries_per_stage: int = 2
    mock_job_delay_sec: float = 0.3

    def resolved_llm_mode(self) -> Literal["mock", "live"]:
        if self.llm_mode == "live" and self.llm_api_key.strip():
            return "live"
        return "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
