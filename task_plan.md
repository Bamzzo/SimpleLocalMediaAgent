# Task Plan: SLMAgent

## Goal
验证从 Brief/剧本到关键帧、视频与成片记录的可复现视听创作链路；本地 Mock 已闭环，真实 FLUX→H3 媒体链路已有 P10 证据，后续补齐 LLM live、质量阈值与部署稳定性。

## Current Phase
P10 真实媒体链路（FLUX→H3→Gradio）已验证；正在做本地收尾修复（UI 标签、manifest 时间语义、文档纠偏）。未完成：编排侧 DeepSeek live 规划、OpenCLIP/首尾帧相似度校准、部署稳定性与归档。

## Phases

### Phase A: Local Mock（不租 GPU）
- [x] 落盘 `docs/PROJECT_BASELINE.md` 决策基线
- [x] 建立目录与 contracts（Brief / Storyboard / Jobs / Manifest）
- [x] 实现 Mock FLUX/H3、LangGraph 状态流、FastAPI、Gradio
- [x] DeepSeek live 结构化输出小探测（3/3 PASS；见 `docs/DEEPSEEK_LIVE_JSON_PROBE.md`）
- [x] 端到端 Mock 验收：输入 → runs/ → 假图假视频
- **Status:** complete

### Phase A.1 / A.2
- [x] 可播放 Mock 视频与浏览器预览
- [x] DeepSeek JSON 探测（GENERATION_BACKEND 保持 mock）
- **Status:** complete

### Phase B: 服务器预检与 H3 最小验证
- [x] 租用/筛选可用 GPU 实例并完成预检相关准备（已进入云端实测阶段）
- [x] 原生/服务侧跑通 MiniMax-H3 FL2VA 真实生成（见 P10 视频证据）
- [x] 记录可解码输出与关键资源线索（manifest jobs.meta / quality_reports）
- **Status:** complete for minimum H3 evidence (not a claim of production stability)

### Phase C: FLUX 最小验证与异步服务封装
- [x] 真实 FLUX 首尾帧生成（P10：`live_flux_http`）
- [x] `generate_image` / `get_generation_job` live 适配可用并写入 manifest jobs
- **Status:** complete for minimum FLUX evidence

### Phase D: H3 服务封装与真实端到端媒体集成
- [x] H3 `generate_video` / job 查询 live 适配（P10：`live_h3_http`）
- [x] 跑通 FLUX 首尾帧 → H3 → FFmpeg/导出 → Gradio 展示的真实媒体样例
- [x] 保存运行 manifest（`runs/20260808_090019_AIGC_f25501`）
- [ ] 编排侧 DeepSeek live 规划（P10 仍为 `llm_mode=mock`）
- [ ] OpenCLIP / 首尾帧相似度阈值校准
- **Status:** media path complete with warnings; full LLM-live + quality calibration pending

### Phase E: 稳定、阈值校准、归档与容器化
- [ ] 校准 OpenCLIP、首尾帧相似度阈值
- [ ] 验证超时、OOM、恢复和最大两次重试的云端稳定性
- [ ] 固定依赖与镜像版本；容器化/Compose 可复现部署
- [ ] 比赛/交接归档材料
- **Status:** pending

### P10 收尾修复（本地代码/文档）
- [x] Gradio 按 `GENERATION_BACKEND` 动态显示 live/mock，禁止 live 结果旁写 mock
- [x] manifest 增加 `started_at`；`created_at` 对齐运行开始，保留旧 manifest 兼容
- [x] 更新 task_plan / progress / findings
- **Status:** complete (`pytest -q` → 20 passed)

## Key Questions
1. 无 DeepSeek API Key 时如何验收？→ deterministic LLM mock，保证链路可跑
2. Mock 媒体如何生成？→ Pillow + imageio-ffmpeg 可播放占位视频
3. 真实媒体是否等于全真实链路？→ 否。P10 证明 FLUX/H3 live；LLM 规划仍可为 mock

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 包名 `slmagent` | 与项目名一致，避免与行业 SLM 歧义 |
| `GENERATION_BACKEND` 与 `LLM_MODE` 分离 | 可单独验证媒体 live 与 LLM live |
| 单主 Agent LangGraph | 符合基线已确认设计 |
| manifest `created_at`=run start | 避免仅有收尾时间戳；旧文件可无 `started_at` |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| winget/GitHub ffmpeg download timeout | 1 | Use imageio-ffmpeg bundle |
| DeepSeek Storyboard `shot_id` int vs str | 1 | Coerce in Pydantic + prompt tighten |
| Gradio hard-coded Phase A Mock on live runs | 1 | Dynamic labels from GENERATION_BACKEND |
| manifest created_at==completed_at at wrap-up | 1 | Record started_at in RECEIVE_INPUT |

## Notes
- 不得虚构推理速度、显存、成功率
- 未实测能力不得写成已实现
- P10 最终视频约 1344x768、~5.18s、含音频；不等于 商业级画质承诺
