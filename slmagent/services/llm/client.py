"""DeepSeek-compatible LLM client with mock fallback."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from slmagent.configs.settings import Settings, get_settings
from slmagent.contracts.models import Brief, CreativePlan, GenerationMode, Shot, Storyboard


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def mode(self) -> str:
        return self.settings.resolved_llm_mode()

    def plan_creative(self, brief: Brief) -> CreativePlan:
        if self.mode == "live":
            data = self._chat_json(self._creative_system(), self._creative_user(brief))
            return CreativePlan.model_validate(data)
        return self._mock_creative(brief)

    def build_storyboard(self, brief: Brief, creative: CreativePlan) -> Storyboard:
        if self.mode == "live":
            data = self._chat_json(self._storyboard_system(), self._storyboard_user(brief, creative))
            return Storyboard.model_validate(data)
        return self._mock_storyboard(brief, creative)

    def _chat_json(self, system: str, user: str) -> dict[str, Any]:
        url = self.settings.llm_base_url.rstrip("/") + "/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.settings.llm_model,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        return self._parse_json(content)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                raise
            return json.loads(match.group(0))

    @staticmethod
    def _creative_system() -> str:
        return (
            "你是视听创作策划。只输出合法 JSON，字段："
            "title, logline, audience, selling_points(array), visual_style, tone, constraints(array), notes。"
            "P0 仅规划单个 5 秒宣传镜头。"
        )

    @staticmethod
    def _creative_user(brief: Brief) -> str:
        return json.dumps(brief.model_dump(mode="json"), ensure_ascii=False, indent=2)

    @staticmethod
    def _storyboard_system() -> str:
        return (
            "你是分镜导演。只输出合法 JSON："
            '{"project_name": str, "rationale": str, "shots": [{...}]}。'
            "shots 只能有 1 个镜头，duration_sec 必须为数字 5。"
            "shot_id 必须是字符串，例如 \"shot_01\"，不要输出数字。"
            "每个 shot 字段：shot_id, duration_sec, subject, scene, composition, shot_size, "
            "action, camera_move, lighting, style_notes, needs_first_frame, needs_last_frame, generation_mode。"
            "generation_mode 取值只能是：文生视频 / 首帧生视频 / 首尾帧生视频。"
        )

    @staticmethod
    def _storyboard_user(brief: Brief, creative: CreativePlan) -> str:
        return json.dumps(
            {"brief": brief.model_dump(mode="json"), "creative_plan": creative.model_dump(mode="json")},
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def _mock_creative(brief: Brief) -> CreativePlan:
        points = [p.strip() for p in brief.selling_points.split(",") if p.strip()]
        if not points:
            points = ["结构化创作工作流", "关键帧到视频联动", "可复现部署"]
        title = brief.project_name or "智影宣传镜头"
        desc = brief.description or brief.script_text or "科技感产品宣传"
        return CreativePlan(
            title=title,
            logline=f"在 5 秒内展示「{title}」的核心价值：{desc[:80]}",
            audience=brief.audience or "高校与小型内容工作室",
            selling_points=points,
            visual_style=brief.visual_style.value,
            tone="自信、清晰、未来感",
            constraints=[
                "单镜头 5 秒",
                f"比例 {brief.aspect_ratio.value}",
                "768p 本地输出",
                *( [c.strip() for c in brief.constraints.split(",") if c.strip()] ),
            ],
            notes="Phase A mock creative plan — replace with live DeepSeek when LLM_MODE=live",
        )

    @staticmethod
    def _mock_storyboard(brief: Brief, creative: CreativePlan) -> Storyboard:
        mode = brief.generation_mode
        subject = creative.title
        return Storyboard(
            project_name=brief.project_name,
            rationale="P0 默认单镜头分镜，保证首尾帧与视频提示词可传递。",
            shots=[
                Shot(
                    shot_id="shot_01",
                    duration_sec=5,
                    subject=subject,
                    scene="深色科技空间，柔和体积光与细网格界面浮层",
                    composition="产品标识居中偏左，右侧为动态数据流与镜头推进空间",
                    shot_size="中景到近景",
                    action="镜头缓慢推进，界面粒子与光带向镜头汇聚，最终定格品牌标识",
                    camera_move=brief.camera_move.value,
                    lighting="冷青主光 + 边缘高光，对比清晰",
                    style_notes=creative.visual_style,
                    needs_first_frame=mode != GenerationMode.T2V,
                    needs_last_frame=mode == GenerationMode.FL2VA,
                    generation_mode=mode,
                )
            ],
        )
