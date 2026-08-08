# SLMAgent 开发、部署与验证全过程记录（中文）

## 1. 文档用途与记录规则

本文是截至 2026-08-08 的中文事实记录，汇总了本地工程、DeepSeek 小样本、云端 MiniMax-H3 原生验证、FLUX/H3 适配、P10 Gradio 真实端到端运行、证据归档和停服过程。

记录严格区分四类信息：

1. 已验证事实：由代码、测试、媒体、哈希、日志或命令结果支持。
2. 工程决策：对本项目或当时实例作出的选择，不写成通用最优实践。
3. 实例配置：端口、路径、GPU、版本和会话变量，只能作为复现线索。
4. 未验证事项：必须保留为限制或下一步计划，不能宣传为现有能力。

## 2. 项目目标、范围和架构起点

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

## 3. 2026-08-07：阶段 A 本地 Mock 骨架

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

## 4. 2026-08-07：DeepSeek live 结构化输出验证

为了不混淆文本模型与真实媒体模型，验证时设置 LLM_MODE=live，同时保持 GENERATION_BACKEND=mock。脚本 scripts/deepseek_live_json_probe.py 检查三类输入：

1. 默认 Brief。
2. 剧本驱动模式。
3. 带参考图的 Brief。

首次运行中 CreativePlan 都能解析，但 Storyboard 失败：DeepSeek 返回数字型 shot_id，例如 1，而合约期望字符串。修复方式是对 Shot.shot_id 做兼容转换，并在提示词中明确要求 shot_01 格式。修复后 3 个样例均通过。

此结果只说明有限输入可输出当前 Pydantic 合约可接受的 JSON；它不是对长时间稳定性、成本、提示词质量、真实媒体后端或生产可用性的承诺。验证结束后 LLM_MODE 已恢复为 mock。

证据位于 docs/DEEPSEEK_LIVE_JSON_PROBE.md 和 runs/_deepseek_live_probe/。

## 5. 2026-08-07：云端 H3 原生 FL2VA 最小验证

### 5.1 为什么先做原生验证

真实媒体接入前，H3 本体、CUDA、多卡通信、SGLang、权重下载、FFmpeg 和应用编排都是独立风险。先在云端确认官方原生路径，可避免一次端到端失败时无法判断问题来自模型、环境还是本地应用。

### 5.2 已验证实例与环境线索

验证使用 AutoDL 三卡 NVIDIA RTX 6000D 实例。单卡可见显存约 85,651 MiB；H3 使用 GPU 1/2，GPU 0 保留给随后 FLUX 任务。实例驱动报告 CUDA 13.2，系统 CUDA 为 12.8。

FlashInfer 面向 SM12 的 JIT 编译需要高于系统 CUDA 12.8 的 nvcc。为避免替换系统 driver，在数据盘单独安装 CUDA 13 toolkit，并仅在 H3 会话设置 CUDA_HOME、PATH 和 LD_LIBRARY_PATH。这个选择针对当时实例，不应直接照搬到不同平台。

网络上，GitHub/Hugging Face 在该实例多次超时；会话级使用 AutoDL network_turbo 改善访问。权重仅从官方 Hugging Face 获取；遇到 XET/CAS 传输失败后通过禁用 XET 并断点续传完成。

版本 pin 和环境证据在 H3 归档中保存，核心线索包括：

- SGLang commit：101bb2327cdebf310d5261775f00eaef13a2e168
- MiniMax-H3 commit：d8824efaf94586c0cc9ac7ad8d0723d4d6420ea
- 权重 revision：bfc8ed0353f5a9733be73e6b2c98ec0948195b86
- 环境目录：/root/autodl-tmp/envs/minimax-h3-101bb232
- 模型目录：/root/autodl-tmp/models/MiniMax-H3

### 5.3 H3 启动和首次失败

H3 使用双卡 TP、FL2VA、5 秒、短边 768、16:9、memory performance mode 和分层卸载。首次任务完成了去噪和解码，日志也显示 MP4 已写出，但 API 最终状态为 failed。根因不是模型或 GPU，而是服务端后处理要求 ffprobe，实例中没有该命令。

补齐 FFmpeg/ffprobe 后，使用相同请求重新验证成功。成功样例生成可解码 H.264 MP4，并保存请求 JSON、状态、FFprobe、帧数、资源采样和哈希。这证明 H3 原生路径可用，但当时尚不代表 SLMAgent 端到端已完成。

## 6. 2026-08-08：FLUX、H3 HTTP 适配和 P9 串行联调

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

### 6.2 P9 验证顺序

为了避免三张 GPU 同时加载大模型，P9 被拆为两段：

1. 启动 FLUX 于 GPU 0，经 SSH 本地端口 18001 生成同一 remote run 的首尾帧。
2. 停止 FLUX 并确认 GPU 0 释放。
3. 启动 H3 于 GPU 1/2，经 SSH 本地端口 13011 读取这两个云端路径，生成 MP4。
4. 下载本地视频，探测时长、分辨率、视频与音频，写入证据。

这次串行联调证明了真实 FLUX 到真实 H3 的工件交接。脚本 run_live_flux_pair.py、run_live_flux_smoke.py 和 run_live_h3_smoke.py 固化了烟测和证据写入逻辑。

## 7. 2026-08-08：P10 Gradio 真实端到端验证

### 7.1 启动链路

P10 使用本地 Gradio、FastAPI 和两条 SSH 本地转发。FLUX 监听云端 127.0.0.1:8001，H3 监听云端 127.0.0.1:30010；Windows 通过 18001 和 13011 访问。服务从不绑定公网。

首次 Gradio 启动的 startup-events 请求受到本机代理影响，返回 502。设置 NO_PROXY/no_proxy 为 127.0.0.1,localhost 并禁用 Gradio analytics 后，Gradio 正常启动。FastAPI 根路径与 json/version 的 404 是未定义探测路径，不代表 API 失败；docs 页面返回 200。

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

### 7.3 P10 后的准确性修复

P10 的初始页面仍显示 Phase A Mock 和媒体标签 mock，即使底部 backend 已显示 live。修复后：

- FinalManifest 新增 started_at；新 run 的 created_at 与开始时间一致，completed_at 表示结束时间；历史 manifest 仍可解析。
- PipelineResponse 返回本次实际 backend 与 llm_mode。
- Gradio 页面横幅只表达当前页面配置；完成结果摘要和脚注以 API 返回的实际模式为准。
- API health 的说明也根据 live/mock 状态变化。

全量测试在收尾时达到 21 passed，保留一个 Starlette/httpx 弃用告警。Ruff 的本轮规则已清理；仓库仍有历史 Optional[T] 风格和长行问题，未做无关的大规模格式化。

## 8. 证据归档、下载与云端停服

### 8.1 归档内容

云端 P10 证据包包含：

- 两张 P10 PNG 和 H3 MP4。
- 当前 FLUX/H3 服务日志和 PID。
- 运行时 GPU/服务/健康快照。
- FLUX OpenAPI 契约、依赖摘要、H3 环境摘要和报告。

归档刻意排除了模型权重、缓存、完整虚拟环境、CUDA 安装包、上游源码树、任何 .env、SSH 密钥、token、代理凭据和 shell history。

### 8.2 哈希与本地保存

P10 证据包：

~~~text
archives/p10_evidence_20260808_090019_AIGC_f25501.tar
size: 3,072,000 bytes
sha256: fad70402b3e9d90140a6a8a51535c933d8b6bfe82315daf1ef627fd237b43611
~~~

tar 自身哈希校验通过；解压后的 MANIFEST.sha256 含 14 项，全部验证通过。该包已下载到本地并进入 Git 作为小型工程证据。

H3 原生适配归档：

~~~text
slmagent-h3-cloud-adaptation-20260807.tar.gz
sha256: a5a710718eb8d99c9737122d6a54f3e3fbfafd94b04ebc64e86a6106e778162b
~~~

### 8.3 停服结果

归档验证后，使用活动 PID 文件向 FLUX 和 H3 发送 SIGTERM：

| 服务 | 活动 PID | 停服结果 |
|---|---:|---|
| FLUX | 25393 | 8001 关闭，GPU 0 释放 |
| H3 | 18415 | 30010 关闭，scheduler 子进程退出，GPU 1/2 释放 |

最终 nvidia-smi 显示 GPU 0/1/2 均为 0 MiB、无计算进程。没有删除模型、缓存、run 或日志。停止服务不等同于停止云实例计费；实例级关机或释放必须在确认本地归档后由操作者在云平台完成。

## 9. 当前结论、限制与后续工作

截至本记录，项目已经完成并保留证据的能力是：Gradio 到真实 FLUX/H3 媒体生成的单镜头串行端到端流程。这个结论不包括全程 DeepSeek live、质量阈值、长期稳定性、并发、失败恢复、安全和生产部署。

建议后续顺序：

1. 在独立 run 中验证 DeepSeek live 与真实媒体后端的组合，仍保持完整 manifest 和证据。
2. 为 OpenCLIP、首尾帧相似度和人工审片建立校准数据与明确阈值。
3. 测试连接中断、服务重启、超时、OOM 和最多两次重试的恢复行为。
4. 固定云端启动脚本、版本和部署说明，再评估 Docker/Compose。
5. 明确许可、成本、数据安全和并发边界后，再考虑产品化。
