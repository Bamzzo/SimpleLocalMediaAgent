# SLMAgent - 简易本地化智能视听创作智能体

SLMAgent 是一个面向短宣传镜头的可追溯创作工作流验证项目。用户提供 Brief 或剧本和可选参考图，系统完成创意规划、单镜头分镜、首尾关键帧、首尾帧视频生成、基础技术检查、导出与运行记录落盘。

> 本项目中的“本地化”指图像和视频模型可运行在团队可控制的自托管服务器上，不等同于个人电脑运行或完全离线。文本规划可配置为 DeepSeek API；P10 已验证的媒体模型运行在受 SSH 隧道保护的云端实例。

## 项目状态

| 能力 | 状态 | 证据或边界 |
|---|---|---|
| Gradio -> FastAPI -> LangGraph 工作流 | 已实现 | 本地测试与浏览器验证 |
| Mock 图像、视频和可播放 MP4 | 已实现 | Phase A / A.1 |
| DeepSeek 结构化 JSON | 小样本验证 | 3 个输入通过；不是长期稳定性承诺 |
| 真实 FLUX.2 Klein 9B 首尾帧 | 已验证 | P9/P10，1024x576 PNG |
| 真实 MiniMax-H3 FL2VA 视频 | 已验证 | P9/P10，约 5 秒、16:9、短边 768 |
| Gradio 端到端真实媒体链路 | 已验证 | P10: FLUX -> H3 -> 本地 MP4 |
| 全程 DeepSeek live | 未验证 | P10 使用 llm_mode=mock |
| 质量阈值校准、并发、OOM、自动恢复 | 未完成 | 不应视为生产能力 |
| Docker/Compose 真实部署 | 未完成 | 仅有设计与归档说明 |

P10 的真实运行状态为 completed_with_warnings：技术媒体检查通过，但 OpenCLIP 与首尾帧相似度阈值尚未校准。不要将此项目描述为生产级视频生成服务或已完成画质验收。

## P10 已验证链路

~~~text
Gradio
  -> FastAPI /pipeline/run
  -> LangGraph 状态图
  -> Mock 或 DeepSeek 结构化规划
  -> FluxHttpBackend (SSH: localhost:18001 -> cloud 127.0.0.1:8001)
  -> 云端首帧 / 尾帧工作区
  -> H3HttpBackend (SSH: localhost:13011 -> cloud 127.0.0.1:30010)
  -> 本地下载 MP4、质量检查、FFmpeg 导出、final_manifest.json
~~~

P10 项目 ID：20260808_090019_AIGC_f25501

- FLUX 首尾帧：1024x576 RGB
- H3 任务：ff616cd3-4ca1-463e-95e0-782e0ad945f5
- 视频：1344x768、约 5.18 秒、有视频和音频
- H3 推理时间：约 824 秒
- 本地运行证据：runs/20260808_090019_AIGC_f25501/
- 云端证据包：archives/p10_evidence_20260808_090019_AIGC_f25501.tar

完整技术记录见：

- [项目全过程中文日志](docs/PROJECT_HISTORY_20260808_ZH.md)
- [P10 真实运行与归档记录](docs/P10_LIVE_E2E_AND_ARCHIVE_20260808.md)
- [归档、恢复与部署指南](docs/ARCHIVE_AND_DEPLOYMENT_GUIDE_ZH.md)
- [原始设计基线](docs/PROJECT_BASELINE.md)

## 架构与职责

| 层 | 组件 | 职责 |
|---|---|---|
| 交互层 | Gradio | 收集 Brief/剧本/参考图，预览首帧、尾帧与成片 |
| API 层 | FastAPI | pipeline/run 与生成工具边界；返回本次实际 backend/LLM 模式 |
| 编排层 | LangGraph | 顺序状态图、有限重试、状态与错误归档 |
| 规划层 | Mock LLM / DeepSeek | 输出 CreativePlan、Storyboard |
| 图像层 | Mock FLUX / FluxHttpBackend | 生成首尾帧；live 时记录云端工件路径 |
| 视频层 | Mock H3 / H3HttpBackend | 首尾帧 FL2VA；live 时轮询并下载 MP4 |
| 质量与导出 | media tools / FFmpeg | 基础存在性、尺寸、时长、音频与可播放性检查 |
| 记录层 | ProjectStore / FinalManifest | 每个 run 的输入、提示词、任务、媒体、质量报告与错误 |

状态流：

~~~text
RECEIVE_INPUT
  -> PLAN_CREATIVE
  -> BUILD_STORYBOARD
  -> PREPARE_IMAGE_PROMPT
  -> GENERATE_IMAGE
  -> CHECK_IMAGE
  -> PREPARE_VIDEO_PROMPT
  -> GENERATE_VIDEO
  -> CHECK_VIDEO
  -> POSTPROCESS
  -> COMPLETE
~~~

### 跨机器适配思路

Windows 本地路径不能直接作为云端 H3 的 file URI 输入。因此 live 模式采用云端工件工作区：

1. FLUX 将首帧和尾帧写入 /root/autodl-tmp/slmagent-live-runs/<run_id>/images/。
2. 本地 FluxHttpBackend 下载 PNG，同时在任务元数据中保留云端绝对路径。
3. H3HttpBackend 将这两个云端路径传给 H3，而不是传入 Windows 路径。
4. H3 完成后，本地适配器通过内容接口下载 MP4，继续执行统一的本地质量检查与 manifest 写入。

服务仅监听云端 127.0.0.1；本地通过 SSH 端口转发访问。这样不需要公开模型端口、对象存储或把模型服务暴露给互联网。

## 已解决的关键问题

| 问题 | 处理方式 |
|---|---|
| Mock MP4 只是极小占位文件，无法真实播放 | 使用系统 FFmpeg 或 imageio-ffmpeg 生成并探测可播放 MP4 |
| Gradio 与编排直接耦合 | 改为 Gradio 调 FastAPI，API 再调用 LangGraph |
| 参考图只在临时目录 | 在 RECEIVE_INPUT 复制到对应 run 的 uploads/ |
| DeepSeek 返回数字 shot_id | 合约做兼容转换，并收紧提示词约束 |
| live 模式可能静默落回 Mock | live 时实例化真实 HTTP 适配器，测试覆盖客户端选择 |
| H3 无法读取 Windows 文件路径 | 使用云端 FLUX 工件路径完成跨模型交接 |
| H3 推理超过前端默认超时 | 为 live 工作流设置可配置的长轮询和 API 超时 |
| 页面文案把真实结果称作 Mock | API 返回实际 backend/LLM 模式，Gradio 结果以 API 值为准 |
| 历史 manifest 缺少真实开始时间 | 新 run 写入 started_at，并定义时间字段语义 |

## 本地开发

### 安装与 Mock 验证

Windows PowerShell：

~~~powershell
git clone https://github.com/Bamzzo/SimpleLocalMediaAgent.git
Set-Location SimpleLocalMediaAgent
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m pytest -q
python scripts/run_mock_pipeline.py
~~~

启动交互界面时使用两个终端：

~~~powershell
# 终端 1
python -m uvicorn slmagent.api.main:app --host 127.0.0.1 --port 8000

# 终端 2
python -m slmagent.apps.gradio_app
~~~

浏览器访问 http://127.0.0.1:7860。默认配置是 Mock，不会调用云端模型。

### 真实媒体模式

真实模式需要先在云端独立验证 FLUX/H3，再启动本地 SSH 隧道。不要把密码、令牌、SSH 私钥或云端命令写进 .env、日志或 Git。

~~~powershell
$env:GENERATION_BACKEND = "live"
$env:FLUX_SERVICE_URL = "http://127.0.0.1:18001"
$env:H3_SERVICE_URL = "http://127.0.0.1:13011"
$env:API_PIPELINE_TIMEOUT_SEC = "1800"
$env:LIVE_VIDEO_TIMEOUT_SEC = "1800"
~~~

之后重新启动 API 与 Gradio。详细的恢复、部署前提、资产校验和停服顺序见[归档、恢复与部署指南](docs/ARCHIVE_AND_DEPLOYMENT_GUIDE_ZH.md)。

## 资产与归档

仓库包含两个小型、可校验的工程证据包：

| 文件 | 用途 | 不包含 |
|---|---|---|
| archives/p10_evidence_20260808_090019_AIGC_f25501.tar | P10 云端媒体、日志、PID、接口与环境摘要 | 模型、缓存、完整环境、凭据 |
| slmagent-h3-cloud-adaptation-20260807.tar.gz | H3 原生 FL2VA 适配、版本锁定、烟测证据 | 约 144 GB 权重、CUDA、完整虚拟环境 |

两个归档都必须先校验 SHA-256。它们是证据与恢复线索，不是可一键部署的完整模型镜像。

## 目录

~~~text
slmagent/       Gradio、API、合约、编排、服务与 Skills
scripts/        Mock、DeepSeek、FLUX/H3 烟测脚本
tests/          合约、编排、API、Gradio 与 live handoff 测试
docs/           设计、验收、项目日志与部署说明
archives/       小型 P10 云端证据包
runs/           本机生成结果（默认忽略，不进入 Git）
~~~

## 后续计划

1. 对 DeepSeek live 做一次带真实媒体后端的独立可追溯验证。
2. 校准 OpenCLIP 与首尾帧相似度阈值，并定义人工审片标准。
3. 验证超时、失败、OOM 与有限重试的恢复策略。
4. 固定云端部署脚本、版本与启动参数，再评估 Docker/Compose。
5. 在明确模型许可、成本、并发和安全边界后，才讨论多用户或生产部署。

## 许可与安全

模型、上游依赖和生成内容的使用须分别遵守其许可证和适用政策。本仓库不保存 API Key、密码、SSH 私钥、模型权重或模型缓存。公开发布或商业使用前，请重新核对 FLUX、MiniMax-H3、DeepSeek 与依赖项的许可和使用条款。
