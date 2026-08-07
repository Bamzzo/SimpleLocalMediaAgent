"""LangGraph state for the single main agent pipeline."""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from slmagent.contracts.models import (
    Brief,
    CreativePlan,
    ErrorRecord,
    ImagePrompt,
    QualityReport,
    Storyboard,
    VideoPrompt,
)


class AgentState(TypedDict, total=False):
    project_id: str
    project_root: str
    brief: Brief
    creative_plan: Optional[CreativePlan]
    storyboard: Optional[Storyboard]
    image_prompt: Optional[ImagePrompt]
    video_prompt: Optional[VideoPrompt]
    first_frame_path: Optional[str]
    last_frame_path: Optional[str]
    raw_video_path: Optional[str]
    final_video_path: Optional[str]
    jobs: list[dict[str, Any]]
    quality_reports: list[QualityReport]
    errors: list[ErrorRecord]
    image_attempts: int
    video_attempts: int
    status: str
    current_node: str
    warnings: list[str]
    timings_sec: dict[str, float]
    backend: str
    llm_mode: str
