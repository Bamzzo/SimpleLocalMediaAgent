"""Run one end-to-end Phase A mock pipeline from CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slmagent.contracts.models import Brief
from slmagent.orchestrator.graph import run_pipeline


def main() -> None:
    brief = Brief(
        project_name="智影AIGC创作平台宣传镜头",
        mode="free",
        description="智影是面向创作团队的 AIGC 视听创作平台。",
        selling_points="结构化分镜, 首尾帧约束, 本地化视频生成",
        audience="高校创新团队与小型内容工作室",
        constraints="单镜头5秒, 16:9, 768p",
    )
    result = run_pipeline(brief)
    summary = {
        "project_id": result.get("project_id"),
        "status": result.get("status"),
        "first_frame_path": result.get("first_frame_path"),
        "last_frame_path": result.get("last_frame_path"),
        "final_video_path": result.get("final_video_path"),
        "warnings": result.get("warnings"),
        "llm_mode": result.get("llm_mode"),
        "backend": result.get("backend"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
