# SLMAgent 完整开发日志与验证记录

日期：2026-08-07
项目：SLMAgent（Simple Local Media Agent）
仓库：`https://github.com/Bamzzo/SimpleLocalMediaAgent`
记录范围：本地阶段 A（Mock 工程与 DeepSeek 结构化输出）及 AutoDL 云端 MiniMax-H3 原生 FL2VA 最小验证。
文档目的：作为后续开发、复现、交接与验收的单一事实入口。

## 0. 阅读口径与结论摘要

本记录严格区分四类内容：

- **已验证事实**：有代码、测试、日志、产物、哈希或命令记录支撑。
- **已确认决策**：针对当前项目或当前服务器约束作出的选择，不等于通用最佳实践。
- **当前实例配置**：路径、端口、GPU 编号、会话变量等，换机器不能直接照抄。
- **未验证事项与计划**：不得描述为现有能力或性能承诺。

截至本记录完成时，项目已得到两个彼此独立的结论：

1. 在 **Mock** 条件下，SLMAgent 已完成并验证了从 Brief/剧本、参考图到可追踪项目目录、可播放占位媒体的应用链路；DeepSeek 在三个小样本中可输出通过当前 Pydantic 合约的创意与分镜 JSON。
2. 在一台 AutoDL 三卡 RTX 6000D 实例上，MiniMax-H3 的官方 FL2VA 最小原生路径已产出一个可解码的真实 MP4；该结果**尚未**接入 SLMAgent，也不包含 FLUX、端到端成片或 Docker 验证。

因此，当前不能宣称“SLMAgent 真实端到端视频生成已完成”。正确表述是：**应用骨架与 H3 原生推理分别已验证，真实 FLUX、真实服务适配和端到端集成仍待完成。**

## 1. 项目目标、P0 边界与总体架构

### 1.1 产品目标

SLMAgent 中的 Local 指图像与视频模型运行在团队可控的自托管服务器，不等同于个人电脑运行或完全离线。第一版文本模型仍通过 DeepSeek API 调用。

P0 目标为：用户输入 Brief 或完整剧本，可选上传参考图；系统完成需求理解、创意规划、单镜头分镜、图像与视频提示词、首尾关键帧、基础质量检查、约 5 秒的 16:9 / 768p 视频、导出及完整项目记录。首个演示案例为“智影 AIGC 创作平台宣传镜头”。

P0 验收重点是链路完整、过程可追溯、输出满足基础技术检查；不预先承诺商业级画质、固定成功率、固定推理时长或生产级吞吐。

### 1.2 P0 明确不包含

- 多用户高并发、生产队列与计费审计；
- 一分钟长片、短剧/漫剧批量生产、复杂数字人与口型；
- 专业配音、音乐和复杂音频工作流；
- H3 Ref2VA、官方托管 2K 增强；
- 多智能体协商；
- 无上限自动重试；
- 已验证的 Docker 生产部署。

### 1.3 已确认架构决策

```text
Gradio UI → FastAPI → LangGraph 主编排
                         ├─ DeepSeek：CreativePlan / Storyboard
                         ├─ FLUX：首帧、尾帧（当前为 Mock）
                         ├─ MiniMax-H3：视频（当前应用内为 Mock）
                         └─ 文件、manifest、质量检查、导出
```

- **单主 Agent + 显式状态图**：P0 是顺序创作流水线；避免过早引入多角色协商的上下文传递、合并和排错成本。
- **LangGraph**：负责节点状态、分支、有限重试和恢复。
- **FastAPI**：是应用与后续模型服务的稳定边界，便于本地/云端拆分。
- **Gradio**：负责用户表单、参考图上传及结果预览。
- **DeepSeek**：负责语言理解和结构化 JSON；通过 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 配置，不在业务逻辑中写死模型名。
- **FLUX.2 Klein 9B 与 MiniMax-H3 Base FL2VA**：分别是规划中的真实图像与视频后端；本记录不把它们写作本地阶段 A 的既有能力。

## 2. 本地阶段 A：Mock 工程骨架

### 2.1 目标与范围

阶段 A 的目标是在不租用 GPU、不下载大型权重的条件下，先验证产品工程结构：输入、编排、接口边界、项目落盘、媒体预览与验收证据是否完整。它不是对真实 FLUX 或 H3 的性能测试。

### 2.2 已落地模块

- `slmagent/apps`：Gradio 界面；
- `slmagent/api`：FastAPI 入口和工具接口；
- `slmagent/orchestrator`：LangGraph 状态图和管线节点；
- `slmagent/contracts`：Pydantic 输入、任务、质量和 manifest 合约；
- `slmagent/services`：LLM、Mock FLUX、Mock H3、generation 门面、质量检查、导出、媒体工具、项目存储；
- `slmagent/skills`：creative-storyboard、flux-image-production、h3-video-production 的提示词和说明；
- `scripts`：CLI Mock、手工验收和 DeepSeek live probe；
- `tests`：回归测试；
- `docs`：决策基线、阶段验收和探测记录。

核心合约包括 `Brief`、`CreativePlan`、`Shot`、`Storyboard`、`ImagePrompt`、`VideoPrompt`、`ImageJob`、`VideoJob`、`QualityReport`、`ErrorRecord`、`FinalManifest`。错误信息包含 `code`、`message`、`retryable`、`suggested_action`，供编排做有限恢复。

### 2.3 已实现并验证的编排流程

```text
RECEIVE_INPUT
  → PLAN_CREATIVE
  → BUILD_STORYBOARD
  → PREPARE_IMAGE_PROMPT
  → GENERATE_IMAGE
  → CHECK_IMAGE
  → PREPARE_VIDEO_PROMPT
  → GENERATE_VIDEO
  → CHECK_VIDEO
  → POSTPROCESS
  → COMPLETE
```

Mock FLUX 使用 Pillow 生成首帧、尾帧占位图；Mock H3 通过后台任务生成视频。可用 `ffmpeg`（优先系统版本，否则使用 `imageio-ffmpeg` 捆绑二进制）时，产出的是可被媒体探测的静音 H.264 MP4，而非只含路径的伪文件。每个阶段的最大重试次数结构上限制为两次。

对外工具形态为 `generate_image`、`generate_video`、`get_generation_job`，以 `queued/running/succeeded/failed` 管理 `img_*` / `vid_*` 任务。这里的异步形态仅验证了应用协议；并不等于已经实现生产级消息队列或真实模型的异步服务。

### 2.4 运行目录与可追溯性

每次运行创建 `runs/<project_id>/`。典型内容包括：

```text
brief.json
creative_plan.json
storyboard.json
prompts/
uploads/
images/first_frame.png
images/last_frame.png
videos/h3_raw.mp4
final/result.mp4
jobs.json
quality_report.json
errors.json
final_manifest.json
```

`project_id` 使用 ASCII 安全字符，`ProjectStore.path` 对路径进行校验，降低目录穿越风险。`final_manifest.json` 是每次产物追溯的落点。

## 3. 本地阶段 A 的关键修复与验收

### 3.1 服务边界与参考图持久化

早期 Gradio 曾直接导入和执行 LangGraph，这与既定服务边界不一致，也不利于未来部署拆分。已改为 Gradio 向 FastAPI 的 `/pipeline/run` 提交 Brief，再由 API 调用 LangGraph；`API_BASE_URL` 与 `API_PIPELINE_TIMEOUT_SEC` 可配置。

参考图若仅停留在系统临时目录，重启服务后不可靠，也无法归档。修复后，Gradio 先写入 `RUNS_DIR/_uploads`，`RECEIVE_INPUT` 再复制到本次运行的 `uploads/`，并回填 `brief.reference_image_paths`。样例运行证明参考图保存在项目目录内，而非临时目录。

### 3.2 A.1：不可播放 Mock 视频

**问题。** 无系统 `ffmpeg/ffprobe` 时，早期示例的 MP4 约 89 字节，只是兜底容器；Gradio 可打开不代表视频真实可播放。

**修复。** 引入 `imageio-ffmpeg`，新增 `media_tools` 统一定位 ffmpeg；Mock H3 和导出阶段都走真实编码；删除不可播放兜底；质量检查改为媒体探测失败即不通过。

**验证。** `scripts/manual_phase_a_accept.py` 通过。`runs/20260807_050513_AIGC_bf60a9/` 的 `h3_raw.mp4` 与 `result.mp4` 约 16KB，探测结果为 `duration=5.0s`、`has_video=true`；证据为 `runs/_manual_accept/phase_a1_evidence.json`。用户已在浏览器中确认首帧、尾帧和视频可预览。

### 3.3 live 模式防误导

真实 HTTP 适配器尚未实现时，若 `GENERATION_BACKEND=live` 仍退回 Mock，会使占位媒体被误认为真实推理结果。当前实现改为显式抛出 `GenerationBackendUnavailable`，并由自动化测试覆盖“live 不得静默 Mock”。

### 3.4 DeepSeek `shot_id` 类型兼容

首次 live 探测中，`CreativePlan` 均通过而 `Storyboard` 失败，因为模型给出数字型 `shot_id: 1`，合约期望字符串。已在 `Shot.shot_id` 添加前置转换，并收紧系统提示词，要求如 `shot_01` 的字符串格式。修复后重新验证通过。

### 3.5 测试与验收结果

- `pytest -q`：4 passed；
- 覆盖范围：CLI/编排端到端 Mock、参考图复制、`/pipeline/run` 冒烟、live 防静默降级；
- CLI：`scripts/run_mock_pipeline.py`；
- API + Gradio 手工验收：`scripts/manual_phase_a_accept.py`；
- Git 基线：`c77bb1c feat: establish phase A mock workflow`；
- `.gitignore` 已忽略 `.env`，本次记录未读取或输出密钥。

## 4. DeepSeek live JSON 小样本验证

### 4.1 方法与证据

验证时设置 `LLM_MODE=live`，同时保持 `GENERATION_BACKEND=mock`，以确保本次只验证文本结构化输出，不触发真实图像或视频后端。使用 `scripts/deepseek_live_json_probe.py` 对以下输入检查原始 JSON 解析和 Pydantic 校验：

- `default_brief`；
- `script_mode`；
- `brief_with_reference`。

证据路径：

- `docs/DEEPSEEK_LIVE_JSON_PROBE.md`；
- `runs/_deepseek_live_probe/probe_20260807_051043.json`。

接口配置为 `deepseek-chat @ https://api.deepseek.com`；保存的 API 证据中曾返回 `deepseek-v4-flash`。测试完成后已将 `LLM_MODE` 恢复为 mock。

### 4.2 结论与边界

三个案例中的 `CreativePlan` 与 `Storyboard` 最终全部通过。这只说明这些输入下的 JSON 可解析并符合当前合约；不说明所有输入的长期稳定性、提示词最优性、调用成本、真实图像/视频质量或真实后端可用性。

`docs/PHASE_A_ACCEPTANCE_AND_HANDOFF.md` 文首仍有“DeepSeek live 未验收”的历史表述；该处已过时，应以 `DEEPSEEK_LIVE_JSON_PROBE.md` 及最终审计记录为准：A.2 已关闭。

## 5. 云端阶段 B：MiniMax-H3 原生 FL2VA 验证

### 5.1 实验目的与隔离原则

云端验证的目标是先独立确认官方 MiniMax-H3 FL2VA 权重和官方 SGLang 路径能在当前机器生成一个约 5 秒、短边 768、16:9、首尾帧条件的视频。范围刻意限定为：**H3 原生冒烟，不是 SLMAgent 端到端，不是 FLUX，不是 Docker。**

先验证原生模型路径，再考虑 Agent 集成，是为了避免把网络、CUDA、SGLang 版本、权重下载和应用编排故障混在一次排错中。

### 5.2 实例与基础环境（当前实例事实）

- 系统：Ubuntu 22.04.5 LTS，内核 `5.15.0-78-generic`；
- GPU：3 × NVIDIA RTX 6000D，单卡约 85,651 MiB；
- 驱动：595.71.05，驱动报告 CUDA Version 13.2；
- 系统 CUDA：`/usr/local/cuda-12.8`，`nvcc 12.8.93`；
- 数据盘：`/root/autodl-tmp`，归档时约 1.1 TB 总容量、约 879 GB 可用；
- 容器内 `free` 采样：约 754 GiB 总内存；
- 实际选卡：物理 GPU 1、2；GPU 0 保持空闲。

GPU 1/2 是本机部署策略，而非跨机器的通用最优选择。`nccl_smoke.py` 在 `CUDA_VISIBLE_DEVICES=1,2` 下完成双卡 all-reduce，结果符合预期值 3.0；服务启动后也能看到 TP0/TP1 分别占用两卡。归档未完整记录 CPU 型号、核心数、NUMA 明细和系统盘布局，因此这些数值不应被补造。

### 5.3 网络与 CUDA 适配

该实例直连 GitHub/Hugging Face 经常超时或被拒绝。使用 AutoDL 提供的会话级网络加速：

```bash
source /etc/network_turbo
```

它未写入 `.bashrc`，新 shell 需要重新启用；并且对部分 conda/pip 通道可能有副作用，因此按访问通道切换，而非永久全局代理。权重始终从官方 Hugging Face 获取，未使用第三方镜像。

RTX 6000D 的 FlashInfer SM12 JIT 需要 `nvcc >= 12.9`，但基础镜像只有 CUDA 12.8。为避免升级系统驱动或破坏镜像，在数据盘单独安装 CUDA 13.0 toolkit：

- 官方 runfile MD5 已核对：`1029f86a4565d4a814d918a6e1c7de43`；
- 安装仅使用 toolkit，不安装 driver；
- 路径：`/root/autodl-tmp/cuda-13.0`；
- 会话级设置 `CUDA_HOME`、`PATH`、`LD_LIBRARY_PATH`；
- 最终系统 ` /usr/local/cuda` 仍恢复为 CUDA 12.8，本地 `nvcc` 为 13.0 (`V13.0.48`)；
- 最小 `-arch=sm_120` 编译探针通过。

这是降低当前实例风险的决策，不表示所有机器都需要、或应当安装 CUDA 13。

### 5.4 SGLang 与权重版本钉死

最初稳定版 `sglang==0.5.16` 不具备 H3 所需 CLI 参数和 FL2VA 支持，因而没有用于正式 serve。正式环境从源码 editable 安装并固定为：

- SGLang commit：`101bb2327cdebf310d5261775f00eaef13a2e168`；
- MiniMax-H3 仓库 commit：`8d8824efaf94586c0cc9ac7ad8d0723d4d6420ea`；
- 权重 revision：`bfc8ed0353f5a9733be73e6b2c98ec0948195b86`；
- 环境路径：`/root/autodl-tmp/envs/minimax-h3-101bb232`；
- Python 3.12.3、Torch 2.11.0+cu130、Diffusers 0.37.0、FlashInfer 0.6.15.post1、flash-attn-4 4.0.0b18；
- `SGLANG_BUILD_RUST_EXTS=none`，因为主机未提供 cargo/rustc，且 diffusion 路径可用。

`sglang serve --help` 已确认存在 `--model-variant`、`--dit-layerwise-resident-layers`、`--num-gpus`、`--tp-size`、`--ulysses-degree` 和 `--performance-mode` 等参数。

权重仅下载 FL2VA 及根配置，排除 Ref2VA 与 Diffusers 范围。完整 FL2VA 目录为 85 个文件、约 144.05 GB，位于 `/root/autodl-tmp/models/MiniMax-H3`。下载过程中，陈旧 `refs/main` 导致 404，已改为显式固定 revision；XET/CAS 下载在约 28 GB 处失败，设置 `HF_HUB_DISABLE_XET=1` 后断点续传完成。

### 5.5 实际启动与请求配置

启动脚本：`/root/autodl-tmp/h3-smoke/start_serve.sh`。关键配置如下：

```text
CUDA_VISIBLE_DEVICES=1,2
CUDA_HOME=/root/autodl-tmp/cuda-13.0
模型模式=fl2va
num-gpus=2, tp-size=2, ulysses-degree=1
performance-mode=memory
layerwise offload=dit,text_encoder,vae
dit-layerwise-resident-layers=20
host=127.0.0.1, port=30010
```

实际配方基于官方 cookbook 的 SM12 双卡 memory/offload 路径。这里采用的是 **BF16 + 双卡 TP + layerwise offload**，并非早期规划中曾设想的 INT8。该调整基于官方可复现路径和实测适配结果。

请求文件为 `request_fl2va.json`：`task=fl2va`、`seconds=5`、`short_edge=768`、`aspect_ratio=16:9`、首帧 `frame_index=0`、尾帧 `frame_index=-1`、`steps=50`、`flow_shift=12.0`、`audio_flow_shift=3.0`、`seed=2101`。测试素材为本地合成的 1280×720 几何 PNG，说明见 `media/ASSET_README.txt`，不使用第三方版权图片。

## 6. H3 推理结果、异常与复验

### 6.1 首次请求：推理成功，后处理校验失败

首次任务 ID：`ee6834b2-433d-4ff7-bbeb-325e1ef5d7f6`。

服务约 18:57 启动、19:01:31 ready；任务约 19:03:09 提交。日志记录 denoise 完成（49 steps）、解码完成和 `Output saved`，API/日志记录峰值内存 23,830 MB、推理约 797.68 秒。

最终 API 状态为 failed，错误是：`ffprobe is required to validate final MiniMax H3 output`。这不是模型、GPU、显存或去噪失败；MP4 已生成，但官方后处理验证因系统没有 `ffprobe` 而失败，随后没有保留该次输出文件。

为补齐验证，安装 `ffmpeg` 以提供 `/usr/bin/ffprobe`，随后按相同请求复验。该系统级安装是一次实际变更，应如实保留在日志中。

### 6.2 第二次请求：同参成功并保留产物

成功任务 ID：`c6eeb25c-82ae-47bf-aee6-4f06142f9d33`。约 19:17:39 以相同 JSON 提交，约 19:30:58 返回 `completed`。

最终文件：

```text
/root/autodl-tmp/h3-smoke/out/minimax-h3-fl2va-5s-768p.mp4
```

技术校验：

- 文件大小：265,053 字节；
- SHA256：`945c220e209e5c68b46c862d34de553becf4316230a4ff91dfa2f6dc94608c40`；
- 容器：mov/mp4；
- 时长：约 5.207 秒；
- 视频：H.264，1344×768，24 fps，124 帧，yuv420p；
- 音频：AAC，32,000 Hz，双声道；
- `ffmpeg` null decode：通过。

API 的 `seconds=5.166667` 与封装后约 5.207 秒并不矛盾，容器时长略长是常见封装现象。

### 6.3 单次资源观测

- API `peak_memory_mb`：23,830；
- API `inference_time_s`：约 796.57 秒；
- 墙钟：约 799 秒；
- 推理期采样：GPU 1/2 各约 28,125 MiB；
- 含加载会话峰值：GPU 1/2 各约 37,199 MiB；
- 会话 CPU 内存峰值：约 220,105 MiB；这与 layerwise offload 将权重钉在 CPU 内存有关。

这些数值只对“该实例、该权重 revision、该请求、该 seed、该 offload 配方”的单次观测负责，不构成 RTX 6000D、MiniMax-H3 或任何云平台的性能 SLA。

### 6.4 收尾状态与归档

归档时服务已经停止，30010 没有监听，三张 GPU 显存占用为 0。权重、toolkit、环境、仓库、日志、缓存、成片和首尾帧均未删除。

本地已保存云端白名单归档及校验信息：

- `slmagent-h3-cloud-adaptation-20260807.tar.gz`；
- SHA256：`a5a710718eb8d99c9737122d6a54f3e3fbfafd94b04ebc64e86a6106e778162b`；
- 大小：810,280 字节。

该归档意在保存验证证据和恢复信息，不包含模型权重、HF 缓存、完整 conda 环境、CUDA toolkit 或凭据。

## 7. 当前能力矩阵

| 能力 | 当前状态 | 证据 / 边界 |
|---|---|---|
| Gradio → FastAPI → LangGraph | 已验证 | Mock 路径和手工验收通过 |
| 参考图在运行目录中持久化 | 已验证 | `uploads/` 复制与运行样例 |
| Mock 视频可播放、可探测 | 已验证 | A.1 证据与浏览器验收 |
| DeepSeek 结构化创意/分镜 | 小样本已验证 | 3 个案例通过，不代表长期 SLA |
| H3 官方 FL2VA 最小样例 | 已验证 | 云端真实 MP4、日志、哈希 |
| FLUX.2 Klein 9B 原生推理 | 未验证 | 尚未部署与冒烟 |
| SLMAgent 接入真实 H3 | 未验证 | 应用内 live 仍显式拒绝 |
| FLUX + H3 端到端成片 | 未验证 | 尚无真实集成证据 |
| 生产级异步队列 | 未验证 | 当前是 Mock 协议形态 |
| Docker / Compose 真实后端 | 未验证 | 暂不属于已验收范围 |
| Ref2VA、V2V、T2VA、>5s、2K | 未验证 | 不应作为当前能力宣传 |

## 8. 重要证据与路径索引

### 8.1 本地仓库

- 基线与验收：`docs/PROJECT_BASELINE.md`、`docs/PHASE_A_ACCEPTANCE_AND_HANDOFF.md`、`docs/DEEPSEEK_LIVE_JSON_PROBE.md`；
- 过程记录：`task_plan.md`、`findings.md`、`progress.md`；
- API / UI / 编排：`slmagent/api/main.py`、`slmagent/apps/gradio_app.py`、`slmagent/orchestrator/graph.py`、`slmagent/orchestrator/nodes/pipeline.py`；
- 合约与服务：`slmagent/contracts/models.py`、`slmagent/services/generation.py`、`slmagent/services/media_tools.py`、`slmagent/services/quality/checks.py`、`slmagent/services/postprocess/ffmpeg_export.py`；
- 运行与验证：`scripts/run_mock_pipeline.py`、`scripts/manual_phase_a_accept.py`、`scripts/deepseek_live_json_probe.py`、`tests/test_mock_pipeline.py`；
- Mock 证据：`runs/20260807_050513_AIGC_bf60a9/`、`runs/_manual_accept/phase_a1_evidence.json`、`runs/_deepseek_live_probe/probe_20260807_051043.json`。

### 8.2 云端验证（路径记录）

- 冒烟目录：`/root/autodl-tmp/h3-smoke/`；
- 最终视频：`/root/autodl-tmp/h3-smoke/out/minimax-h3-fl2va-5s-768p.mp4`；
- 首尾帧、请求、报告：同目录下 `out/`、`request_fl2va.json`、`REPORT.md`、`SESSION_ARCHIVE.txt`；
- 日志和指标：`logs/serve.log`、下载日志、`metrics/resource_timeseries.csv`、nvidia-smi 快照；
- 正式环境：`/root/autodl-tmp/envs/minimax-h3-101bb232`；
- SGLang 源码：`/root/autodl-tmp/sglang @ 101bb232`；
- 模型权重：`/root/autodl-tmp/models/MiniMax-H3`；
- CUDA toolkit：`/root/autodl-tmp/cuda-13.0`。

## 9. 风险、合规与后续准入条件

### 9.1 已识别风险

- 多卡可见不代表 NCCL、显存和版本组合一定可用；应先做小型通信冒烟；
- H3 的分层卸载降低 GPU 压力，但会显著提高主机内存需求；
- 权重、HF 缓存、CUDA toolkit、环境和日志需要大量数据盘空间；
- 非发布版 SGLang commit、独立 CUDA 13 toolkit 与会话变量使环境复现较脆弱；
- 网络加速、HF XET 和下载缓存有平台与时间差异；
- 自动质量检查不能替代人工审片；
- 服务应默认绑定 `127.0.0.1`，密钥、SSH 和代理信息不得写入日志、脚本或归档。

MiniMax H3 使用前应再次阅读仓库的完整许可证与可接受使用政策。这里对许可证的记录仅用于工程提示，不构成法律意见。

### 9.2 推荐的下一阶段顺序

1. 保持现有 H3 权重、环境、工具链和归档证据，不做破坏性清理；
2. 独立进行 FLUX.2 Klein 9B 的原生最小验证，并记录许可证、版本、显存、内存、输出和可解码性；
3. 在启动 H3 前检查 `ffprobe` 可用，并从已固定的环境/启动脚本恢复会话变量；
4. FLUX 与 H3 均有独立真实样例后，分别实现真实 `generate_image`、`generate_video`、`get_generation_job` HTTP 适配器；
5. 用实测适配器替换应用中 `GenerationBackendUnavailable` 的 live 防护，保留最多两次重试、manifest 和错误记录；
6. 只在真实端到端样例稳定后，进行 Docker/Compose、长期运行、成本与并发评估。

真实集成时应始终分开保存 Mock 和真实产物，禁止将两者混写在同一验收结论中。

## 10. 最终收束

本地阶段 A 已完成应用工程层面的可运行、可测试、可追溯闭环；DeepSeek 已完成有限样本的结构化输出验证。云端阶段 B 已完成 H3 官方 FL2VA 的真实原生最小样例，并留下了可解码成片、资源测量、环境版本和恢复线索。

当前最重要的事实边界是：**H3 原生验证成功不等于 SLMAgent 端到端成功；Mock 工程验收成功也不等于真实 FLUX/H3 集成成功。** 下一步应先完成独立 FLUX 验证，再以现有合约接入两个真实后端，最后才评估容器化与生产化。
