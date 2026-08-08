# SLMAgent 从本地原型到真实媒体链路的开发记录

## 1. 文档用途与记录规则

本文按实际工作顺序，记录从本地 Mock 工程、DeepSeek 合约验证、云端 H3 原生验证，到 FLUX/H3 跨机适配、界面端到端运行、证据归档和云端停服的全过程。

它不是部署操作手册，也不替代各阶段的原始证据。其职责是把决策、变更、失败、复验和可定位的证据串成一条时间线，使后续维护者能够回答四个问题：当时试图证明什么、实际做了什么、结果如何确认、哪些结论仍然不能作出。异地恢复部署的步骤另见 `README.md` 和 `docs/ARCHIVE_AND_DEPLOYMENT_GUIDE_ZH.md`。

记录严格区分四类信息：

1. 已验证事实：由代码、测试、媒体、哈希、日志或命令结果支持。
2. 工程决策：对本项目或当时实例作出的选择，不写成通用最优实践。
3. 实例配置：端口、路径、GPU、版本和会话变量，只能作为复现线索。
4. 未验证事项：必须保留为限制或下一步计划，不能宣传为现有能力。

本文中的 Windows 路径以本仓库工作区为准，云端路径以当时的 AutoDL 实例为准。端口、PID、GPU 编号、时间和会话环境变量都是一次实例的观测记录；它们能够帮助排错和复现，但不是复制到任意机器即可成立的部署配方。文中不会记录 API 密钥、SSH 私钥、代理凭据、`.env` 内容或 shell 历史。

### 1.1 阅读顺序与结论层级

阅读时可沿着“先把应用跑通，再逐层替换为真实后端”的顺序理解。以下三个结论的证据强度不同，不能互相替代：

| 结论层级 | 已验证事实 | 不可推导的结论 |
|---|---|---|
| 阶段 A | Mock 管线可产生可探测、可预览的占位媒体和完整运行目录 | 不代表调用了真实图像/视频模型 |
| 原生模型 | H3 官方 FL2VA 在指定云端实例产出一次可解码 MP4 | 不代表 SLMAgent 已接入，更不代表生产稳定 |
| P10 集成 | 从 Gradio 发起的一次 run 实际经过 live FLUX 与 live H3，并把结果回收至本地 | 不代表 DeepSeek 全程 live、质量阈值已校准或具备并发/容灾能力 |

本日志中出现的“成功”均指相应层级已经由其证据支持；没有“成功”一词可以自动升级为生产可用、画质达标或成本可控。

## 2. 先明确要解决的问题和边界

SLMAgent 的 P0 目标是接收 Brief、完整剧本和可选参考图，自动形成创意规划、单镜头分镜、图像提示词、视频提示词、首尾关键帧、约 5 秒的视频、基础技术质量检查、最终导出和完整项目记录。

目标样例是“智影 AIGC 创作平台宣传镜头”：16:9、短边 768、单镜头、约 5 秒、首尾帧生视频。验收重点是流程完整、输出可播放、工件可追溯，不承诺商业画质、固定时延、固定成功率、成本或生产吞吐。

初始架构决策如下：

~~~text
Gradio UI
  -> FastAPI
  -> LangGraph 单主 Agent 状态图
       -> Mock LLM / DeepSeek: CreativePlan、Storyboard
       -> Mock FLUX / FluxHttpBackend: 首帧、尾帧
       -> Mock H3 / H3HttpBackend: FL2VA 视频
       -> 质量检查、FFmpeg 导出、ProjectStore、FinalManifest
~~~

选择单主 Agent 而不是多智能体，是因为 P0 是顺序创作管线；过早引入协商、上下文合并和角色调度会增加故障面而不直接改善验收目标。

明确不在 P0 范围内的事项包括：多用户高并发、消息队列、生产审计、长片批量生产、复杂数字人/口型、Ref2VA/V2V/T2VA、自动无限重试、生产级容器化和 SLA。

## 3. 第一步：先搭建可运行、可追溯的本地骨架

### 3.1 已建立的工程结构

本地仓库建立了以下模块：

| 目录/模块 | 作用 |
|---|---|
| slmagent/apps | Gradio 表单、文件上传、媒体预览 |
| slmagent/api | FastAPI 管线与生成工具接口 |
| slmagent/orchestrator | LangGraph 图与各阶段节点 |
| slmagent/contracts | Brief、Plan、Shot、Job、QualityReport、Manifest 等 Pydantic 合约 |
| slmagent/services | LLM、Mock/Live 后端、质量检查、导出、媒体工具和项目存储 |
| slmagent/skills | creative-storyboard、flux-image-production、h3-video-production |
| scripts | CLI、手工验收、DeepSeek 和 live 烟测 |
| tests | 编排、API、上传、后端合约和交接测试 |

状态图被固定为：

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

每次运行创建 runs/<project_id>/。典型工件包括 brief.json、creative_plan.json、storyboard.json、prompts/、uploads/、images/、videos/、final/result.mp4、jobs.json、quality_report.json、errors.json 和 final_manifest.json。

`project_id` 只使用 ASCII 安全字符，`ProjectStore.path` 对路径进行校验，避免调用方借项目名写到运行目录外。`final_manifest.json` 是一次 run 的总账：它关联输入、生成任务、质量报告、文件路径、错误与结束状态。最初的 P10 历史 run 发生在 `started_at` 字段引入之前，因此该 run 的 `created_at` 和 `completed_at` 都接近收尾时刻；这不是一次异常耗时为零的运行。之后的合约规定：进入 `RECEIVE_INPUT` 时写入 `started_at`，`created_at=started_at`，收尾时再写入 `completed_at`，同时保持旧 manifest 可解析。

阶段 A 的真实编码策略也有明确边界：Mock FLUX 只负责用 Pillow 生成标记性关键帧，Mock H3 只负责生成可播放的占位视频；即使占位 MP4 能被 FFmpeg 解码，也不能称为 FLUX 或 H3 推理结果。任务的 `queued/running/succeeded/failed` 形态用于验证应用合约和编排等待逻辑，尚不是消息队列、持久化调度器或生产级异步系统。

### 3.2 服务边界与参考图持久化

早期 Gradio 直接执行 LangGraph。这不符合 UI/API/编排分层，也不便于未来拆分部署。后续改为 Gradio 向 FastAPI 的 pipeline/run 提交 Brief，API 再调用编排。

参考图最初位于临时目录，服务重启后不可靠。修复后 Gradio 先写入 RUNS_DIR/_uploads，RECEIVE_INPUT 再把文件复制到当前 run 的 uploads/，并更新 brief 的 reference_image_paths。这样引用、manifest 和归档都指向项目内部路径。

### 3.3 可播放 Mock 视频问题

最初系统没有可用 ffmpeg/ffprobe，早期 MP4 只有约 89 字节，只是容器占位，不能证明视频可播放。系统级安装曾因网络超时失败，最终使用 imageio-ffmpeg 携带的二进制作为回退。

修复包括：

- 新建媒体工具定位可用 FFmpeg。
- Mock H3 与导出阶段使用真实编码生成 H.264 MP4。
- 去除不可播放的小文件回退。
- 质量检查必须通过媒体探测，不能只检查路径存在。

阶段 A.1 的验收脚本 scripts/manual_phase_a_accept.py 成功，样例 runs/20260807_050513_AIGC_bf60a9/ 的结果视频约 16 KB、时长约 5 秒，浏览器中也确认首帧、尾帧和视频可预览。

这次修复的验收口径不是“页面有视频控件”，而是同时满足文件存在、媒体探测返回视频流、时长合理，并可在浏览器预览。证据文件为 `runs/_manual_accept/phase_a1_evidence.json`；在该样例中，`h3_raw.mp4` 和 `final/result.mp4` 都来自实际编码，而非 89 字节的占位容器。

### 3.4 live 模式曾经的防误导约束

在 HTTP 适配器尚未实现的阶段，`GENERATION_BACKEND=live` 若静默转回 Mock，用户会得到可播放媒体却误以为它来自云端模型。这种降级对演示很危险，因此阶段 A 明确让 live 配置抛出 `GenerationBackendUnavailable`，并将“live 不得静默 Mock”写入测试。这个临时保护在 P9 真正实现 `FluxHttpBackend`、`H3HttpBackend` 后由真实适配器替代，但“不能把 Mock 伪装成 live”的原则持续保留。

### 3.5 阶段 A 的测试基线与可追溯点

阶段 A 收尾时，`pytest -q` 为 `4 passed`，覆盖 CLI/编排 Mock 端到端、参考图复制、`/pipeline/run` 冒烟及 live 防静默降级。基线提交为 `c77bb1c feat: establish phase A mock workflow`。相关入口为：

| 目的 | 入口或证据 |
|---|---|
| CLI Mock run | `scripts/run_mock_pipeline.py` |
| API 与 Gradio 手工验收 | `scripts/manual_phase_a_accept.py` |
| 阶段验收交接 | `docs/PHASE_A_ACCEPTANCE_AND_HANDOFF.md` |
| 运行证据 | `runs/20260807_050513_AIGC_bf60a9/`、`runs/_manual_accept/phase_a1_evidence.json` |

`.gitignore` 已覆盖 `.env`；本阶段的日志与归档没有读取或写入密钥。早期验收文档中“DeepSeek live 未验收”的表述后来被第 4 节的小样本结果更新，阅读时应以时间更晚的 probe 证据为准。

## 4. 第二步：单独验证 DeepSeek 能否满足结构化合约

为了不混淆文本模型与真实媒体模型，验证时设置 LLM_MODE=live，同时保持 GENERATION_BACKEND=mock。脚本 scripts/deepseek_live_json_probe.py 检查三类输入：

1. 默认 Brief。
2. 剧本驱动模式。
3. 带参考图的 Brief。

首次运行中 CreativePlan 都能解析，但 Storyboard 失败：DeepSeek 返回数字型 shot_id，例如 1，而合约期望字符串。修复方式是对 Shot.shot_id 做兼容转换，并在提示词中明确要求 shot_01 格式。修复后 3 个样例均通过。

此结果只说明有限输入可输出当前 Pydantic 合约可接受的 JSON；它不是对长时间稳定性、成本、提示词质量、真实媒体后端或生产可用性的承诺。验证结束后 LLM_MODE 已恢复为 mock。

证据位于 docs/DEEPSEEK_LIVE_JSON_PROBE.md 和 runs/_deepseek_live_probe/。

更具体地说，probe 将原始模型输出先进行 JSON 解析，再按 `CreativePlan` 和 `Storyboard` 的 Pydantic 合约校验，而不是只检查 HTTP 200 或自然语言看似合理。使用的三类输入是 `default_brief`、`script_mode`、`brief_with_reference`；证据文件是 `runs/_deepseek_live_probe/probe_20260807_051043.json`。当时的接口配置记录为 `deepseek-chat @ https://api.deepseek.com`，保存的 API 证据曾报告 `deepseek-v4-flash`。

第一次 probe 的失败模式很具体：`CreativePlan` 成功而 `Storyboard` 不通过，原因是服务返回 `shot_id: 1` 这样的数字，合约要求字符串。修复没有放宽所有字段的约束，而是只在 `Shot.shot_id` 的前置验证中将数字兼容转换为字符串，同时在系统提示词中要求 `shot_01` 格式。修复后重新运行三个样例全部通过。该过程说明合约对模型输出的约束确实被执行，但也说明未来模型版本、提示词或复杂输入仍可能产生新型不合规 JSON。

为了保持证据边界，probe 期间固定 `GENERATION_BACKEND=mock`，没有启动 FLUX 或 H3，也没有把这三次文本结果当作真实成片的规划质量评估。完成后 `LLM_MODE` 恢复为 `mock`；P10 也沿用了 `llm_mode=mock`，因此 P10 只能证明真实媒体链路，并非“DeepSeek live + 真实媒体”的完整组合验证。

## 5. 第三步：先独立跑通云端 H3 原生推理

### 5.1 为什么先做原生验证

真实媒体接入前，H3 本体、CUDA、多卡通信、SGLang、权重下载、FFmpeg 和应用编排都是独立风险。先在云端确认官方原生路径，可避免一次端到端失败时无法判断问题来自模型、环境还是本地应用。

### 5.2 已验证实例与环境线索

验证使用 AutoDL 三卡 NVIDIA RTX 6000D 实例。单卡可见显存约 85,651 MiB；H3 使用 GPU 1/2，GPU 0 保留给随后 FLUX 任务。实例驱动报告 CUDA 13.2，系统 CUDA 为 12.8。

当时实例的完整基础观察为 Ubuntu 22.04.5 LTS、内核 `5.15.0-78-generic`、驱动 `595.71.05`、系统 CUDA 路径 `/usr/local/cuda-12.8`、`nvcc 12.8.93`。数据盘为 `/root/autodl-tmp`，归档时约 1.1 TB 总容量、约 879 GB 可用；容器内 `free` 采样约 754 GiB 内存。CPU 型号、核心数、NUMA 拓扑和系统盘布局未被完整归档，故本记录不补造这些数据。

GPU 1/2 并不是宣称的通用最优配卡，而是为本次三卡实例保留 GPU 0 给后续 FLUX 的资源隔离策略。启动 H3 前，`nccl_smoke.py` 在 `CUDA_VISIBLE_DEVICES=1,2` 下完成双卡 all-reduce，结果为预期值 `3.0`；实际服务启动后，TP0/TP1 也分别占用这两张卡。这两个观察支持该实例的双卡通信可用，但不等同于所有 GPU 型号都可用。

FlashInfer 面向 SM12 的 JIT 编译需要高于系统 CUDA 12.8 的 nvcc。为避免替换系统 driver，在数据盘单独安装 CUDA 13 toolkit，并仅在 H3 会话设置 CUDA_HOME、PATH 和 LD_LIBRARY_PATH。这个选择针对当时实例，不应直接照搬到不同平台。

具体地，SM12 JIT 需要 `nvcc >= 12.9`，因此下载并校验了官方 CUDA 13.0 runfile（MD5：`1029f86a4565d4a814d918a6e1c7de43`），仅安装 toolkit、不安装 driver，目标路径为 `/root/autodl-tmp/cuda-13.0`。会话内临时设置 `CUDA_HOME`、`PATH`、`LD_LIBRARY_PATH` 后，`nvcc` 为 `V13.0.48`，且最小 `-arch=sm_120` 编译探针通过；系统 `/usr/local/cuda` 最终仍保持 CUDA 12.8。这一做法的意图是避免破坏云镜像的驱动依赖，而不是要求任何机器升级到 CUDA 13。

网络上，GitHub/Hugging Face 在该实例多次超时；会话级使用 AutoDL network_turbo 改善访问。权重仅从官方 Hugging Face 获取；遇到 XET/CAS 传输失败后通过禁用 XET 并断点续传完成。

实际会话级网络开关为：

```bash
source /etc/network_turbo
```

它没有写入 `.bashrc`，新 shell 需要重新启用；对部分 conda/pip 通道可能有副作用，所以没有把它改成永久全局代理。下载过程中，一份陈旧的 `refs/main` 引发 404，后续改为显式 revision；XET/CAS 在约 28 GB 处失败后设置 `HF_HUB_DISABLE_XET=1` 并续传。权重始终来自官方 Hugging Face，不使用第三方模型镜像。

版本 pin 和环境证据在 H3 归档中保存，核心线索包括：

- SGLang commit：101bb2327cdebf310d5261775f00eaef13a2e168
- MiniMax-H3 commit：d8824efaf94586c0cc9ac7ad8d0723d4d6420ea
- 权重 revision：bfc8ed0353f5a9733be73e6b2c98ec0948195b86
- 环境目录：/root/autodl-tmp/envs/minimax-h3-101bb232
- 模型目录：/root/autodl-tmp/models/MiniMax-H3

补充的版本与环境事实为：Python `3.12.3`、Torch `2.11.0+cu130`、Diffusers `0.37.0`、FlashInfer `0.6.15.post1`、flash-attn-4 `4.0.0b18`。SGLang 以 editable 方式从源码安装，设置 `SGLANG_BUILD_RUST_EXTS=none`，原因是该主机没有 `cargo/rustc`，且本次 diffusion 路径不依赖 Rust 扩展。此前尝试的 `sglang==0.5.16` 缺少 H3 所需 FL2VA/CLI 支持，因而未作为正式 serve 环境。

执行 `sglang serve --help` 后确认目标提交包含 `--model-variant`、`--dit-layerwise-resident-layers`、`--num-gpus`、`--tp-size`、`--ulysses-degree`、`--performance-mode` 等本次需要的参数。只下载 FL2VA 与根配置，排除 Ref2VA 和 Diffusers 范围；最终目录 85 个文件、约 144.05 GB，位于 `/root/autodl-tmp/models/MiniMax-H3`。这些 pin 是为了让本次证据可重放，不保证相同 commit 在未来依赖生态中仍无需调整。

### 5.3 H3 启动和首次失败

H3 使用双卡 TP、FL2VA、5 秒、短边 768、16:9、memory performance mode 和分层卸载。首次任务完成了去噪和解码，日志也显示 MP4 已写出，但 API 最终状态为 failed。根因不是模型或 GPU，而是服务端后处理要求 ffprobe，实例中没有该命令。

原生启动脚本为 `/root/autodl-tmp/h3-smoke/start_serve.sh`。关键配置如下，均为当时实例设置：

```text
CUDA_VISIBLE_DEVICES=1,2
CUDA_HOME=/root/autodl-tmp/cuda-13.0
model-variant=fl2va
num-gpus=2; tp-size=2; ulysses-degree=1
performance-mode=memory
layerwise offload=dit,text_encoder,vae
dit-layerwise-resident-layers=20
host=127.0.0.1; port=30010
```

该配方是官方 cookbook 的 SM12 双卡 memory/offload 路径，即 BF16 + 双卡 TP + layerwise offload，并非早期设想的 INT8。请求文件 `request_fl2va.json` 固定 `task=fl2va`、`seconds=5`、`short_edge=768`、`aspect_ratio=16:9`、两个条件帧（`frame_index=0` 与 `-1`）、`steps=50`、`flow_shift=12.0`、`audio_flow_shift=3.0`、`seed=2101`。测试图为本地合成的 1280x720 几何 PNG，说明位于 `media/ASSET_README.txt`，不使用第三方版权素材。

补齐 FFmpeg/ffprobe 后，使用相同请求重新验证成功。成功样例生成可解码 H.264 MP4，并保存请求 JSON、状态、FFprobe、帧数、资源采样和哈希。这证明 H3 原生路径可用，但当时尚不代表 SLMAgent 端到端已完成。

首次原生任务 ID 为 `ee6834b2-433d-4ff7-bbeb-325e1ef5d7f6`。服务约 18:57 启动、19:01:31 ready、约 19:03:09 提交任务；日志记录 49 steps 去噪、解码及 `Output saved`，峰值内存约 23,830 MB、推理约 797.68 秒。最后失败的精确错误是 `ffprobe is required to validate final MiniMax H3 output`。MP4 写出不等于 API 完成：因为验证失败，该次输出没有作为最终产物保留。随后安装 `ffmpeg` 提供 `/usr/bin/ffprobe`，再按同参复验；这是一次明确记录的系统级变更。

成功任务 ID 为 `c6eeb25c-82ae-47bf-aee6-4f06142f9d33`，约 19:17:39 提交、约 19:30:58 返回 `completed`。产物路径为 `/root/autodl-tmp/h3-smoke/out/minimax-h3-fl2va-5s-768p.mp4`，大小 265,053 字节，SHA-256 为 `945c220e209e5c68b46c862d34de553becf4316230a4ff91dfa2f6dc94608c40`。FFprobe 与 null decode 均通过：mov/mp4 容器，H.264 1344x768、24 fps、124 帧、yuv420p，AAC 32,000 Hz 双声道，封装时长约 5.207 秒。API 报告 `seconds=5.166667` 与容器时长存在小差异，属于封装层时间取整，不构成矛盾。

单次资源观测为 API `peak_memory_mb=23,830`、`inference_time_s` 约 796.57 秒、墙钟约 799 秒；推理期 GPU 1/2 各约 28,125 MiB，含加载会话峰值各约 37,199 MiB，CPU 内存峰值约 220,105 MiB。它们只描述这个权重 revision、seed、offload 配方和实例的一次实验，不能被用作性能 SLA 或成本预估。

## 6. 第四步：把本地应用接到云端 FLUX 和 H3

### 6.1 跨机器工件问题

本地应用运行在 Windows，H3 运行在云端。H3 的 file URI 在云端解析，不能指向 Windows 的 runs 路径。因此仅下载本地 PNG 再传给 H3 的设计不可行。

最终适配规则是：

~~~text
FLUX cloud worker
  -> /root/autodl-tmp/slmagent-live-runs/<run_id>/images/first_frame.png
  -> /root/autodl-tmp/slmagent-live-runs/<run_id>/images/last_frame.png
H3 cloud worker
  -> 使用上述两个云端绝对路径
Local adapters
  -> 下载 PNG/MP4 到 Windows runs/<project_id>/
~~~

FluxHttpBackend 和 H3HttpBackend 分别映射云端任务状态、错误和内容下载。GenerationService 增加任务类别路由，防止 H3 UUID 状态请求错误发到 FLUX 服务。

这次适配没有把远端地址硬写入管线。`FLUX_SERVICE_URL` 与 `H3_SERVICE_URL` 分别注入本地 HTTP 适配器；live 模式不允许转回 `MockFluxBackend` 或 `MockH3Backend`。FLUX 任务完成时，适配器同时取得本地下载图和 `remote_output_path` 元数据；管线把这两个远端绝对路径写入视频请求及最终 manifest。H3 完成后，适配器经 `/v1/videos/{id}/content` 下载到临时 `.part` 文件，完成后再原子替换为本地 MP4，避免中断下载留下被误判为成功的半文件。

对于隧道调用，两个适配器使用 HTTP 客户端的 `trust_env=False`，绕开工作站环境代理。这个约束来自先前的本地代理干扰：如果请求意外由系统代理接管，`127.0.0.1` 隧道可能被转发到错误位置或收到非模型服务的响应。各类连接、HTTP、远端状态、缺少输出、内容类型和下载失败都会映射为结构化可恢复错误；适配器本身不因为超时或轮询错误盲目重新提交推理任务。

### 6.2 端口与服务隔离

当时的服务拓扑如下。云端两个模型均只监听 loopback，本地通过 SSH 本地转发访问，避免模型服务暴露公网：

```text
Windows SLMAgent
  FluxHttpBackend -> 127.0.0.1:18001 -> SSH forward -> cloud 127.0.0.1:8001
  H3HttpBackend   -> 127.0.0.1:13011 -> SSH forward -> cloud 127.0.0.1:30010
```

本地 H3 端口选为 `13011`，是因为 `13010` 已被一项无关的 Windows 服务占用；这不是 H3 固定端口要求。云端 FLUX 服务预期监听 `127.0.0.1:8001`，H3 SGLang 服务监听 `127.0.0.1:30010`。本地可分别通过 `/health` 验证隧道链路，而无需让模型在公网监听。

### 6.3 P9 验证顺序、任务与证据

为了避免三张 GPU 同时加载大模型，P9 被拆为两段：

1. 启动 FLUX 于 GPU 0，经 SSH 本地端口 18001 生成同一 remote run 的首尾帧。
2. 停止 FLUX 并确认 GPU 0 释放。
3. 启动 H3 于 GPU 1/2，经 SSH 本地端口 13011 读取这两个云端路径，生成 MP4。
4. 下载本地视频，探测时长、分辨率、视频与音频，写入证据。

这次串行联调证明了真实 FLUX 到真实 H3 的工件交接。脚本 run_live_flux_pair.py、run_live_flux_smoke.py 和 run_live_h3_smoke.py 固化了烟测和证据写入逻辑。

P9 的拆分不是形式上的阶段命名，而是显存规避措施：FLUX 先独占 GPU 0 生成两帧，确认图像已落到远端共享工作区后停掉 FLUX；只有在 GPU 0 释放后才启动 H3 使用 GPU 1/2。这样不会在三张卡上同时维持两个大型模型的加载态，也使某个阶段失败时可明确定位在图像、路径交接、隧道或视频生成。

P9B-A 的本地证据文件为 `runs/p9b_flux_pair_20260808/evidence/flux_pair_p9b_result.json`。它记录 FLUX 在同一远端 run 下生成首尾帧并保存到：

```text
/root/autodl-tmp/slmagent-live-runs/p9b_flux_pair_20260808/images/first_frame.png
/root/autodl-tmp/slmagent-live-runs/p9b_flux_pair_20260808/images/last_frame.png
```

P9B-B 提交的 H3 job 为 `316ea07e-2b7e-462c-9b0c-ee117513181e`，提示词为“Continue naturally between the supplied endpoint frames with synchronized ambient sound.”，模式为“首尾帧生视频”。初始状态为 `queued`；完成后本地 `runs/p9b_flux_pair_20260808/videos/h3_raw.mp4` 大小 369,926 字节、SHA-256 `9995ef25ed6b60f6cd488233c0d5c7445537f2ebf3c31d5356bd8a676bb6b0ec`。媒体探测结果：1344x768、时长 5.18 秒、同时存在视频和音频。H3 返回远端输出 `/root/autodl-tmp/sglang/outputs/316ea07e-2b7e-462c-9b0c-ee117513181e.mp4`，推理时间约 814.513 秒、峰值内存 23,830 MB。

这份 P9 证据只证明“真实 FLUX 工件被 H3 读取并生成视频”的串行交接；它还没有覆盖 Gradio/API 用户工作流、最终 manifest 语义或页面文案一致性，这些留给 P10 验证。

## 7. 第五步：从 Gradio 页面跑通一次真实媒体链路

### 7.1 启动链路

P10 使用本地 Gradio、FastAPI 和两条 SSH 本地转发。FLUX 监听云端 127.0.0.1:8001，H3 监听云端 127.0.0.1:30010；Windows 通过 18001 和 13011 访问。服务从不绑定公网。

首次 Gradio 启动的 startup-events 请求受到本机代理影响，返回 502。设置 NO_PROXY/no_proxy 为 127.0.0.1,localhost 并禁用 Gradio analytics 后，Gradio 正常启动。FastAPI 根路径与 json/version 的 404 是未定义探测路径，不代表 API 失败；docs 页面返回 200。

P10 前的最小可观测性检查分别为：本地 `http://127.0.0.1:13011/health` 返回 `status=ok`；FLUX 隧道 `http://127.0.0.1:18001/health` 返回 `status=ok`、服务标识 `flux2-klein-9b-local-task`，当时尚未加载 pipeline、GPU 空闲；本地 FastAPI `http://127.0.0.1:8000/docs` 与 Gradio `http://127.0.0.1:7860` 都返回 HTTP 200。H3 云端服务自身的 `http://127.0.0.1:30010/health` 也返回 `{"status":"ok"}`。这些结果只证明当时的健康端点和隧道可达，不表示模型已经加载或一次推理已完成。

启动本地两个进程时使用的关键会话设置为 `GENERATION_BACKEND=live`、`FLUX_SERVICE_URL=http://127.0.0.1:18001`、`H3_SERVICE_URL=http://127.0.0.1:13011`、`API_PIPELINE_TIMEOUT_SEC=1800`、`LIVE_VIDEO_TIMEOUT_SEC=1800`。长超时不是随意放宽：此前原生 H3 单任务已观测到约 799 秒，旧的 120 秒 mock 导向超时对 live H3 明显不足。`NO_PROXY` / `no_proxy` 只用于本机 loopback 绕过代理；没有把模型服务公开到公网。

P10 的实际用户路径是 Gradio 表单提交到 FastAPI `/pipeline/run`，API 调用 LangGraph，随后 FLUX 生成两帧并把远端路径交给 H3，H3 内容端点下载 MP4，最后由本地后处理和质量检查写出 run 目录。与 P9 相同，FLUX 和 H3 在云端仍是串行：不是三个 GPU 同时加载两套模型。

### 7.2 P10 结果

| 字段 | 已验证值 |
|---|---|
| 项目 ID | 20260808_090019_AIGC_f25501 |
| generation backend | live |
| llm mode | mock |
| 第一帧 FLUX job | f6d2e5b6f735450d8e15a9558cf34ded |
| 尾帧 FLUX job | cf4b6e7965484036a0d8e26326ad7669 |
| H3 job | ff616cd3-4ca1-463e-95e0-782e0ad945f5 |
| 首尾帧 | 1024x576 RGB |
| 视频 | 1344x768、约 5.18 秒、含视频和音频 |
| FLUX 阶段 | 27.023 秒 |
| H3 阶段 | 823.713 秒 |
| 错误 | 空列表 |
| 最终状态 | completed_with_warnings |

H3 日志明确记录了去噪完成、解码完成、MP4 写入和内容端点下载成功。告警来自 OpenCLIP/首尾帧相似度阈值尚未校准，而不是媒体任务失败。

本地完整工件目录是 `runs/20260808_090019_AIGC_f25501/`，应连同 `brief.json`、`creative_plan.json`、`storyboard.json`、`prompts/`、两张 `images/*.png`、`videos/h3_raw.mp4`、`final/result.mp4`、`jobs.json`、`quality_report.json` 与 `final_manifest.json` 一起理解。单独查看最终 MP4 只能证明媒体存在，不能证明其来自本次 brief 或正确走过 live 后端。

该 run 的 FLUX 首帧 job 是 `f6d2e5b6f735450d8e15a9558cf34ded`，尾帧 job 是 `cf4b6e7965484036a0d8e26326ad7669`；两图均为 1024x576 RGB。H3 job `ff616cd3-4ca1-463e-95e0-782e0ad945f5` 的云端日志记录去噪阶段约 797.854 秒、解码阶段约 16.932 秒，并在 2026-08-08 17:14:24 写出 `outputs/ff616cd3-4ca1-463e-95e0-782e0ad945f5.mp4`；随后状态与 `/content` 端点均返回 200。任务的服务端总 `inference_time_s` 为约 823.713 秒，`remote_peak_memory_mb` 为约 23,832 MB。这些时间和原生 H3 的量级一致，支持它并非 Mock 视频。

`completed_with_warnings` 必须按字面理解：任务没有错误列表，视频技术探测通过；现有质量报告因 OpenCLIP 与首尾帧相似度阈值没有经校准而产生告警。它不能写成“画质失败”，也绝不能写成“质量已验收”。需要后续以人工审片、代表性样本集和可解释阈值共同建立质量门槛。

### 7.3 P10 后的准确性修复

P10 的初始页面仍显示 Phase A Mock 和媒体标签 mock，即使底部 backend 已显示 live。修复后：

- FinalManifest 新增 started_at；新 run 的 created_at 与开始时间一致，completed_at 表示结束时间；历史 manifest 仍可解析。
- PipelineResponse 返回本次实际 backend 与 llm_mode。
- Gradio 页面横幅只表达当前页面配置；完成结果摘要和脚注以 API 返回的实际模式为准。
- API health 的说明也根据 live/mock 状态变化。

全量测试在收尾时达到 21 passed，保留一个 Starlette/httpx 弃用告警。Ruff 的本轮规则已清理；仓库仍有历史 Optional[T] 风格和长行问题，未做无关的大规模格式化。

这次修复的直接诱因是 P10 UI 初始横幅仍显示 “Phase A Mock”，并且媒体标签可能按 Gradio 进程自身环境显示 mock，即使 API 实际执行的是 live。修复将两个概念拆开：页面横幅只描述 Gradio 进程的“当前页面配置”，而一次 run 的结果摘要、脚注和 API 响应以 API 返回的实际 `backend`、`llm_mode` 为准。`PipelineResponse` 因此新增本次 run 的实际模式，管线在 `COMPLETE` 回填；`/health` 的说明也随 backend 改变。专门测试了“Gradio 环境为 mock、API 返回 live”时结果仍必须显示 live，防止跨进程配置不一致造成误导。

此外，`FinalManifest` 引入 `started_at`，解决历史记录把 `created_at` 写在收尾阶段、导致 created/completed 几乎相同的审计歧义。历史 P10 run 没有被篡改或重写，仍按旧语义保存；只有此后的新 run 使用新时间语义。收尾时 `pytest -q` 为 `21 passed`，新增或更新的覆盖包括 Gradio 标签和 manifest 时间；Ruff 对本轮涉及的 `UP017`、`F401`、`S110`、`RUF100`、`F841` 规则通过。未声称全仓 lint 通过：仍有约 35 处历史 `UP045`，以及既有长行/其他历史项。

## 8. 第六步：归档证据并释放模型服务资源

### 8.1 归档内容

云端 P10 证据包包含：

- 两张 P10 PNG 和 H3 MP4。
- 当前 FLUX/H3 服务日志和 PID。
- 运行时 GPU/服务/健康快照。
- FLUX OpenAPI 契约、依赖摘要、H3 环境摘要和报告。

归档刻意排除了模型权重、缓存、完整虚拟环境、CUDA 安装包、上游源码树、任何 .env、SSH 密钥、token、代理凭据和 shell history。

归档采用白名单而非整盘打包，原因是两类资产的生命周期不同：模型权重、缓存和虚拟环境体积巨大且可按版本重新取得；运行证据、服务日志、PID、契约快照和校验结果体积小但对审计不可替代。P10 包保留两张 PNG、最终 H3 MP4、FLUX/H3 当时的服务日志与 PID、GPU/端口/健康快照、FLUX OpenAPI 契约、依赖摘要、H3 环境摘要与报告。归档没有替代本地源树或完整本地 run，三者共同构成证据链。

### 8.2 哈希与本地保存

P10 证据包：

~~~text
archives/p10_evidence_20260808_090019_AIGC_f25501.tar
size: 3,072,000 bytes
sha256: fad70402b3e9d90140a6a8a51535c933d8b6bfe82315daf1ef627fd237b43611
~~~

tar 自身哈希校验通过；解压后的 MANIFEST.sha256 含 14 项，全部验证通过。该包已下载到本地并进入 Git 作为小型工程证据。

云端归档原始路径为 `/root/autodl-tmp/archives/p10_evidence_20260808_090019_AIGC_f25501.tar`，随后下载到工作区 `archives/`。校验分两层：首先对 tar 自身执行侧车 `.sha256` 校验，结果为 OK；再解压到 `/tmp/p10_tar_verify_20260808_090019_AIGC_f25501/`，对内部 `MANIFEST.sha256` 的 14 个白名单项目全部校验为 OK。校验目录在云端按要求保留，没有作为“清理”删除。

P10 云端媒体的记录哈希如下；它们是证据包内部项目的哈希，不应替代 tar 整包哈希：

| 工件 | SHA-256 |
|---|---|
| 首帧 PNG | `ff7ec96579513dde6175f255a3a3969618be110cae58103133f2eeca2abf9827` |
| 尾帧 PNG | `8930b5b3578b7ac65210680cff19fd5d1fe652fbc72aaf5040b9c667be9b8670` |
| H3 MP4 | `5dba33156dca23e08b418c178956bc821b12b343677e05200cda06254b93709f` |

H3 原生适配归档：

~~~text
slmagent-h3-cloud-adaptation-20260807.tar.gz
sha256: a5a710718eb8d99c9737122d6a54f3e3fbfafd94b04ebc64e86a6106e778162b
~~~

该 H3 原生适配归档大小为 810,280 字节，意在保存环境、版本、启动与原生验证的恢复线索，同样不包含权重、HF 缓存、完整 conda 环境、CUDA toolkit 或凭据。两个归档的用途不同：20260807 包用于解释原生 H3 如何被验证和恢复，P10 包用于证明一次 live 集成 run 与停服前状态；二者都不是一键部署镜像。

### 8.3 停服结果

归档验证后，使用活动 PID 文件向 FLUX 和 H3 发送 SIGTERM：

| 服务 | 活动 PID | 停服结果 |
|---|---:|---|
| FLUX | 25393 | 8001 关闭，GPU 0 释放 |
| H3 | 18415 | 30010 关闭，scheduler 子进程退出，GPU 1/2 释放 |

最终 nvidia-smi 显示 GPU 0/1/2 均为 0 MiB、无计算进程。没有删除模型、缓存、run 或日志。停止服务不等同于停止云实例计费；实例级关机或释放必须在确认本地归档后由操作者在云平台完成。

停服前后没有使用 `pkill`、`kill -9` 或递归删除。FLUX 的 PID `25393` 在发送 `SIGTERM` 后退出，云端 8001 不再监听，GPU 0 无计算进程；H3 的 PID `18415` 在 `SIGTERM` 后退出，其 scheduler 子进程随之退出，云端 30010 不再监听，GPU 1/2 释放。最终 `nvidia-smi` 显示三张卡利用率 0%、显存 0 MiB、`No running processes found`。云实例本身当时没有关机或释放，避免把“服务已停”误记为“账单已停”。

## 9. 现在到底做到了什么

### 9.1 能力矩阵

| 能力 | 状态 | 最直接证据 | 必须保留的边界 |
|---|---|---|---|
| Gradio -> FastAPI -> LangGraph | 已验证 | 阶段 A 手工验收、P10 run | 不代表高并发或多租户 |
| 参考图持久化到 run | 已验证 | `uploads/` 复制逻辑与阶段 A 样例 | 不等于通用资产管理系统 |
| Mock 视频可播放且可探测 | 已验证 | A.1 JSON 证据、FFmpeg 探测 | 不是模型推理 |
| DeepSeek 结构化 JSON | 小样本验证 | 3 个 probe 全通过 | P10 的 LLM 仍为 mock；无稳定性/SLA 结论 |
| H3 原生 FL2VA 5 秒样例 | 已验证 | 原生成功任务、MP4 哈希、FFprobe | 只针对固定实例和参数 |
| FLUX HTTP 图像后端 | 已验证 | P9/P10 FLUX job 与 PNG 工件 | 未单独建立画质/稳定性基准 |
| live FLUX -> live H3 工件交接 | 已验证 | P9B 任务 `316ea...` | 尚不覆盖 UI 与完整 API 语义 |
| Gradio 发起的 live 单镜头 E2E | 已验证一次 | P10 `20260808_090019_AIGC_f25501` | LLM mock、单次串行、阈值未校准 |
| 结果模式文案真实性 | 已验证 | API 回填模式、Gradio 回归测试 | 页面启动横幅仍只代表 Gradio 自身进程 |
| Docker/Compose、长稳运行、并发 | 未验证 | 无 | 不可宣传为已部署 |
| 质量阈值、OOM/断线恢复、安全控制 | 未验证 | 无系统性测试 | `completed_with_warnings` 不是质量验收 |

### 9.2 证据定位索引

| 类别 | 本地位置或标识 | 说明 |
|---|---|---|
| 阶段 A 基线 | `c77bb1c`、`docs/PHASE_A_ACCEPTANCE_AND_HANDOFF.md` | Mock 工程与验收边界 |
| 阶段 A 媒体证据 | `runs/20260807_050513_AIGC_bf60a9/`、`runs/_manual_accept/phase_a1_evidence.json` | 可播放 Mock 成片及探测记录 |
| DeepSeek probe | `docs/DEEPSEEK_LIVE_JSON_PROBE.md`、`runs/_deepseek_live_probe/probe_20260807_051043.json` | 结构化输出小样本 |
| H3 原生恢复资料 | `slmagent-h3-cloud-adaptation-20260807.tar.gz` 与 `.sha256` | 版本、环境、原生验证线索 |
| live 契约设计 | `docs/LIVE_BACKEND_INTEGRATION_DESIGN.md`、`docs/H3_LIVE_ADAPTATION_CONTRACT_P8A.md` | 隧道、远端路径和下载约束 |
| P9 串行联调 | `runs/p9b_flux_pair_20260808/evidence/` | FLUX 首尾帧到 H3 的工件交接 |
| P10 本地 run | `runs/20260808_090019_AIGC_f25501/` | 应用级输入、任务、质量、成片、manifest |
| P10 云端证据 | `archives/p10_evidence_20260808_090019_AIGC_f25501.tar` 与 `.sha256` | 媒体、日志、PID、环境与 14 项内部清单 |
| P10 英文原始记录 | `docs/P10_LIVE_E2E_AND_ARCHIVE_20260808.md` | 时间、哈希和停服摘要的交叉索引 |

### 9.3 仍然成立的限制

1. P10 的 `generation backend=live`，但 `llm_mode=mock`。它不证明 DeepSeek live 与真实 FLUX/H3 组合的完整链路。
2. OpenCLIP 与首尾帧相似度阈值尚未用人工标注或代表性样本校准；没有“质量通过”的产品结论。
3. 所有真实媒体结果来自单次或少量顺序运行，未覆盖并发、重复提交、服务重启、隧道断线、超时、OOM、自动恢复和成本。
4. 本地端口转发与 cloud loopback 是当前安全边界，不等于已有服务鉴权、租户隔离、审计、限流或生产级网络策略。
5. 归档证明某一时刻的选定文件和哈希；它不包含权重、完整环境或密钥，不能单独还原整个云端实例。

## 10. 下一步应该如何继续

截至本记录，项目已经完成并保留证据的能力是：Gradio 到真实 FLUX/H3 媒体生成的单镜头串行端到端流程。此结论由 P10 run、P9 交接证据、云端日志、技术探测、归档哈希和停服记录共同支持。它不包括全程 DeepSeek live、质量阈值、长期稳定性、并发、失败恢复、安全和生产部署。

建议后续顺序：

1. 在独立 run 中验证 DeepSeek live 与真实媒体后端的组合，仍保持完整 manifest 和证据。
2. 为 OpenCLIP、首尾帧相似度和人工审片建立校准数据与明确阈值。
3. 测试连接中断、服务重启、超时、OOM 和最多两次重试的恢复行为。
4. 固定云端启动脚本、版本和部署说明，再评估 Docker/Compose。
5. 明确许可、成本、数据安全和并发边界后，再考虑产品化。

建议每一次后续 real run 都采用与 P10 相同的最低审计规则：记录精确 project/job ID、输入和输出哈希、服务与 GPU 预检、任务状态、媒体探测、质量告警、manifest 语义、退出方式和归档校验；任何未完成的验证应保留为风险，而不是在 README 或日志中提前转写为能力。
