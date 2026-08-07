# SLMAgent — Simple Local Media Agent

简易本地化智能视听创作智能体（MVP / P0 验证）

> **Local** 指图像与视频模型运行在团队可控制的自托管服务器中，不等于必须跑在个人电脑，也不等于完全离线。首版文本模型仍通过 DeepSeek API。

完整决策基线见 [`docs/PROJECT_BASELINE.md`](docs/PROJECT_BASELINE.md)。

## 当前状态（务必区分）

| 状态 | 说明 |
|------|------|
| 已确认设计 | LangGraph + FastAPI + Gradio；DeepSeek；FLUX.2 Klein 9B；MiniMax-H3 Base FL2VA；三 Skill |
| **阶段 A（进行中）** | 本地 Mock：假图/假视频跑通端到端，不依赖 GPU |
| 尚未完成 | 云服务器租用、真实 FLUX/H3 部署、阈值校准、生产级画质承诺 |

**不要把计划能力写成已实现功能，也不要虚构推理速度、显存、成功率。**

## 快速开始（Phase A Mock）

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env

# 端到端 Mock（CLI）
python scripts/run_mock_pipeline.py

# 测试
pytest -q

# FastAPI
python -m slmagent.api.main

# Gradio
# Keep FastAPI running, then open a second terminal:
python -m slmagent.apps.gradio_app
```

可选：在 `.env` 中设置 `LLM_API_KEY` 与 `LLM_MODE=live`，用 DeepSeek 生成真实结构化 JSON；未设置时自动走 deterministic mock。

阶段 A 的验收与后续交接见 [`docs/PHASE_A_ACCEPTANCE_AND_HANDOFF.md`](docs/PHASE_A_ACCEPTANCE_AND_HANDOFF.md)。

## 架构（P0）

```
Gradio → FastAPI → LangGraph 主 Agent
                 ├── DeepSeek API / mock LLM
                 ├── Skills
                 ├── generate_image / generate_video / get_generation_job
                 ├── quality checks
                 └── FFmpeg export
```

状态流：

`RECEIVE_INPUT → PLAN_CREATIVE → BUILD_STORYBOARD → PREPARE_IMAGE_PROMPT → GENERATE_IMAGE → CHECK_IMAGE → PREPARE_VIDEO_PROMPT → GENERATE_VIDEO → CHECK_VIDEO → POSTPROCESS → COMPLETE`

## 目录

```
slmagent/
  apps/           Gradio
  api/            FastAPI
  orchestrator/   LangGraph
  services/       LLM / FLUX / H3 / quality / postprocess
  skills/         三个自有 Skill
  contracts/      Pydantic 数据结构
  configs/        配置与默认选项
runs/             每次运行的项目目录
docs/             决策基线
```

## 演示案例（推荐）

智影 AIGC 创作平台产品宣传镜头：5 秒、16:9、768p、首尾帧生视频。Phase A 输出为占位媒体，仅验证链路。

## 许可与模型注意

公开发布或商业使用前，重新核对 FLUX 9B、MiniMax-H3 与依赖许可证。本仓库 P0 仅做技术验证。
