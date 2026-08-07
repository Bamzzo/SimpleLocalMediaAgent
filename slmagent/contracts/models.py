"""Pydantic contracts for SLMAgent P0 pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ContentType(str, Enum):
    PRODUCT_AD = "产品广告"
    PROJECT_PROMO = "项目宣传片"
    CONCEPT_SHORT = "概念短片"
    AI_DRAMA = "AI短剧片段"


class VisualStyle(str, Enum):
    CINEMATIC = "电影写实"
    TECH_FUTURE = "科技未来"
    FRESH_COMMERCIAL = "清新商业"
    GUOFENG = "国风"
    ART_ANIMATION = "美术动画"


class AspectRatio(str, Enum):
    R_16_9 = "16:9"
    R_9_16 = "9:16"
    R_1_1 = "1:1"


class CameraMove(str, Enum):
    STATIC = "固定"
    SLOW_PUSH = "缓慢推进"
    PULL_OUT = "拉远"
    PAN = "横移"
    ORBIT = "环绕"


class GenerationMode(str, Enum):
    T2V = "文生视频"
    I2V = "首帧生视频"
    FL2VA = "首尾帧生视频"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RecoverableError(BaseModel):
    code: str
    message: str
    retryable: bool = True
    suggested_action: str = ""


class Brief(BaseModel):
    project_name: str = "未命名项目"
    mode: Literal["free", "script"] = "free"
    content_type: ContentType = ContentType.PROJECT_PROMO
    description: str = ""
    selling_points: str = ""
    audience: str = ""
    visual_style: VisualStyle = VisualStyle.TECH_FUTURE
    aspect_ratio: AspectRatio = AspectRatio.R_16_9
    duration_sec: int = 5
    camera_move: CameraMove = CameraMove.SLOW_PUSH
    generation_mode: GenerationMode = GenerationMode.FL2VA
    constraints: str = ""
    script_text: str = ""
    reference_image_paths: list[str] = Field(default_factory=list)


class CreativePlan(BaseModel):
    title: str
    logline: str
    audience: str
    selling_points: list[str] = Field(default_factory=list)
    visual_style: str
    tone: str = ""
    constraints: list[str] = Field(default_factory=list)
    notes: str = ""


class Shot(BaseModel):
    shot_id: str = "shot_01"
    duration_sec: int = 5
    subject: str
    scene: str
    composition: str
    shot_size: str
    action: str
    camera_move: str
    lighting: str = ""
    style_notes: str = ""
    needs_first_frame: bool = True
    needs_last_frame: bool = True
    generation_mode: GenerationMode = GenerationMode.FL2VA

    @field_validator("shot_id", mode="before")
    @classmethod
    def coerce_shot_id(cls, value: Any) -> str:
        # DeepSeek often returns numeric shot_id; normalize to string.
        return str(value)


class Storyboard(BaseModel):
    project_name: str
    shots: list[Shot]
    rationale: str = ""


class ImagePrompt(BaseModel):
    first_frame_prompt: str
    last_frame_prompt: str
    negative_prompt: str = ""
    aspect_ratio: str = "16:9"
    reference_image_paths: list[str] = Field(default_factory=list)
    seed: Optional[int] = None


class VideoPrompt(BaseModel):
    prompt: str
    negative_prompt: str = ""
    mode: GenerationMode = GenerationMode.FL2VA
    duration_sec: int = 5
    resolution: str = "768p"
    aspect_ratio: str = "16:9"
    first_frame_path: Optional[str] = None
    last_frame_path: Optional[str] = None


class ImageJob(BaseModel):
    job_id: str
    kind: Literal["image"] = "image"
    status: JobStatus = JobStatus.QUEUED
    prompt: str = ""
    output_name: str = ""
    output_path: Optional[str] = None
    seed: Optional[int] = None
    error: Optional[RecoverableError] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    meta: dict[str, Any] = Field(default_factory=dict)


class VideoJob(BaseModel):
    job_id: str
    kind: Literal["video"] = "video"
    status: JobStatus = JobStatus.QUEUED
    prompt: str = ""
    mode: GenerationMode = GenerationMode.FL2VA
    output_name: str = ""
    output_path: Optional[str] = None
    error: Optional[RecoverableError] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    meta: dict[str, Any] = Field(default_factory=dict)


class QualityReport(BaseModel):
    stage: str
    passed: bool
    checks: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: str = "阈值待实测校准，Phase A 仅做确定性文件检查"


class ErrorRecord(BaseModel):
    stage: str
    attempt: int
    code: str
    message: str
    retryable: bool = False
    suggested_action: str = ""
    at: datetime = Field(default_factory=utc_now)


class FinalManifest(BaseModel):
    project_id: str
    project_name: str
    status: Literal["completed", "completed_with_warnings", "failed"]
    brief: Brief
    creative_plan: Optional[CreativePlan] = None
    storyboard: Optional[Storyboard] = None
    image_prompt: Optional[ImagePrompt] = None
    video_prompt: Optional[VideoPrompt] = None
    first_frame_path: Optional[str] = None
    last_frame_path: Optional[str] = None
    raw_video_path: Optional[str] = None
    final_video_path: Optional[str] = None
    jobs: list[dict[str, Any]] = Field(default_factory=list)
    quality_reports: list[QualityReport] = Field(default_factory=list)
    errors: list[ErrorRecord] = Field(default_factory=list)
    timings_sec: dict[str, float] = Field(default_factory=dict)
    backend: str = "mock"
    llm_mode: str = "mock"
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
