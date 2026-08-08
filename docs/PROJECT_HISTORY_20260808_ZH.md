# SLMAgent 项目全过程记录（中文）

## 记录原则

本文按已验证事实、工程决策、实例相关配置、未验证事项四类内容记录。已验证事实必须有代码、测试、日志、媒体、哈希或命令结果支撑；计划和猜测不应写成现有能力。

## 项目目标与 P0 边界

P0 的目标是根据 Brief/剧本生成一个约 5 秒、16:9、短边 768 的宣传镜头，并保存完整项目记录。产品关注链路完整性、可追溯性和基础技术检查，不承诺商业级画质、固定成功率、固定时延或生产吞吐。

P0 不包括多用户高并发、消息队列、长片批量生产、复杂口型/音频制作、Ref2VA/V2V/T2VA、生产容器化和自动无限重试。

## 阶段 A：本地 Mock 骨架（2026-08-07）

### 已完成

- 建立 slmagent 包、Pydantic 合约、LangGraph 状态图、FastAPI、Gradio 和三类 Skill。
- 建立每个项目独立的 runs/<project_id>/ 记录目录。
- Mock FLUX 生成首尾帧，Mock H3 生成可播放的 MP4。
- Gradio 经 FastAPI 调用编排，而不是直接调用状态图。
- 参考图从临时目录复制到对应 run 的 uploads/，使运行可归档。
- 通过 imageio-ffmpeg 解决没有系统 FFmpeg 时的可播放 MP4 问题。

### 关键问题与修复

早期 Mock 视频只有约 89 字节，不能作为真实播放证据。修复后统一使用可用 FFmpeg 编码并通过媒体探测；Phase A.1 的手工验收确认首帧、尾帧和视频可在浏览器预览。

证据：

- docs/PHASE_A_ACCEPTANCE_AND_HANDOFF.md
- runs/20260807_050513_AIGC_bf60a9/
- runs/_manual_accept/phase_a1_evidence.json

## 阶段 A.2：DeepSeek 结构化 JSON 小样本（2026-08-07）

在 LLM_MODE=live、GENERATION_BACKEND=mock 下，对默认 Brief、剧本模式和带参考图输入进行了三组结构化输出验证。

首次失败原因是模型返回数字型 shot_id，而合约期望字符串。通过合约兼容转换和提示词收紧后，三组样例均通过 Pydantic 校验。该结果仅说明这三组输入可解析，不构成长期稳定性、成本、质量或真实媒体后端验证。

证据：

- docs/DEEPSEEK_LIVE_JSON_PROBE.md
- runs/_deepseek_live_probe/

## 阶段 B：MiniMax-H3 原生 FL2VA 验证（2026-08-07）

### 工程决策

在连接 SLMAgent 前，先独立验证 H3 原生路径，以避免把网络、CUDA、SGLang、权重、FFmpeg 和应用逻辑的问题混在一次排错里。

### 已验证事实

- AutoDL 三卡 RTX 6000D 实例上，GPU 1/2 运行 H3 的双卡 FL2VA 路径。
- 使用固定的 SGLang、MiniMax-H3 和权重 revision 记录。
- FlashInfer 对 SM12 的编译要求导致系统 CUDA 12.8 不足；在数据盘安装独立 CUDA 13 toolkit，未替换系统 driver。
- 首次推理已生成 MP4，但服务端因缺失 ffprobe 将任务标记失败；补齐 FFmpeg 后重跑成功。
- 成功样例产生可解码约 5 秒、16:9、短边 768 的 H.264 MP4，并记录环境、请求、资源与哈希。

### 归档

slmagent-h3-cloud-adaptation-20260807.tar.gz 保存脚本、版本锁定、日志、媒体样例和恢复说明；不含模型权重、CUDA、完整环境或凭据。

## 阶段 C/D：FLUX、H3 适配与真实串行集成（2026-08-08）

### 适配难点

H3 在云端执行，不能读取 Windows 本地路径。live 模式因此引入云端工件路径：

~~~text
FLUX -> /root/autodl-tmp/slmagent-live-runs/<run_id>/images/*.png
H3    -> 使用上述云端绝对路径作为首尾帧条件
Local -> 下载已完成 PNG/MP4 到 runs/<project_id>/
~~~

### 已完成

- FluxHttpBackend 与 H3HttpBackend。
- 任务类型路由，避免 H3 UUID 被误轮询到 FLUX。
- FLUX 首帧、尾帧串行生成；H3 只在 FLUX 停服并释放 GPU 后启动。
- 两类 HTTP 适配器、跨模型路径交接和 smoke 脚本测试。
- P9 真实 FLUX 首尾帧和真实 H3 视频联调。

## 阶段 P10：Gradio 真实端到端验证（2026-08-08）

| 项目 | 结果 |
|---|---|
| 项目 ID | 20260808_090019_AIGC_f25501 |
| 媒体后端 | live |
| LLM 模式 | mock |
| FLUX | 两张 1024x576 RGB PNG |
| H3 任务 | ff616cd3-4ca1-463e-95e0-782e0ad945f5 |
| 视频 | 1344x768、约 5.18 秒、含音频 |
| FLUX 阶段 | 27.023 秒 |
| H3 阶段 | 823.713 秒 |
| 错误记录 | 无 |
| 最终状态 | completed_with_warnings |

告警来自未校准的 OpenCLIP/首尾帧相似度，不是媒体生成失败。

### P10 收尾修复

- 新 manifest 写入 started_at，并明确 created_at/completed_at 的语义；历史 manifest 保持兼容。
- API 返回本次实际 backend 和 llm_mode。
- Gradio 将页面配置与本次 API 实际结果明确分开，避免把真实媒体错误标注为 Mock。

测试基线更新为 21 passed，另有一个 Starlette/httpx 弃用告警。

## P10 云端证据归档与停服

P10 云端证据包已在本地保存：

~~~text
archives/p10_evidence_20260808_090019_AIGC_f25501.tar
SHA-256: fad70402b3e9d90140a6a8a51535c933d8b6bfe82315daf1ef627fd237b43611
~~~

包内 14 项文件校验通过，包含 P10 媒体、服务日志/PID、接口契约和环境摘要；不包含模型、缓存、完整环境或凭据。归档验证后，FLUX 与 H3 服务均使用 SIGTERM 停止，GPU 0/1/2 均回到 0 MiB。

## 当前能力边界

项目已经验证真实媒体端到端链路，但尚未验证全程 DeepSeek live、质量阈值校准、失败恢复、并发、安全、多用户、Docker/Compose 或生产 SLA。后续工作必须继续区分 Mock、独立模型验证和端到端 live 验证。
