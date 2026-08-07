# Task Plan: SLMAgent Phase A — Local Mock Skeleton

## Goal
建立可运行的 SLMAgent 阶段 A：不依赖真实 GPU，从 Brief/剧本输入走到模拟成片，并落盘项目决策基线。

## Current Phase
Phase A / A.1 / A.2 已关闭，并已完成独立复核。下一门槛为阶段 B：租机预检与 H3 优先原生验证（未开始）。

## Phases

### Phase A: Local Mock（不租 GPU）
- [x] 落盘 `docs/PROJECT_BASELINE.md` 决策基线
- [x] 建立目录与 contracts（Brief / Storyboard / Jobs / Manifest）
- [x] 实现 Mock FLUX/H3、LangGraph 状态流、FastAPI、Gradio
- [x] DeepSeek live 结构化输出实测（3/3 PASS；见 `docs/DEEPSEEK_LIVE_JSON_PROBE.md`）
- [x] 端到端 Mock 验收：输入 → runs/ → 假图假视频
- **Status:** A / A.1 / A.2 complete

### Phase A.1: 可播放媒体与最终目视验收
- [x] 确认可用 ffmpeg（系统 winget 因 GitHub 超时失败；改用 `imageio-ffmpeg` 捆绑二进制）
- [x] 重新运行 `scripts/manual_phase_a_accept.py` → ACCEPTANCE PASS
- [x] 浏览器确认首帧、尾帧和视频可预览占位媒体（用户确认）
- [x] 保存最终运行的 manifest 与终端输出（`runs/20260807_050513_AIGC_bf60a9/`、`runs/_manual_accept/phase_a1_evidence.json`）
- **Exit gate:** 已满足。

### Phase A.2: DeepSeek live JSON 小验证
- [x] 设置 `LLM_MODE=live`，保持 `GENERATION_BACKEND=mock`
- [x] 用默认 Brief、剧本模式、带参考图 Brief 各运行一次
- [x] 保存脱敏后的原始响应、Pydantic 校验结果、失败原因与修复策略
- [x] 结束后将 `LLM_MODE` 恢复为 `mock`
- **Exit gate:** 三个样例均得到可解析的 `CreativePlan` 与单镜头 `Storyboard`。首次因 `shot_id` 为 int 失败，已用 coerce + 提示词收紧修复后重跑 PASS。

### Phase B: 服务器预检与 H3 最小验证
- [ ] 筛选单机 3×48GB 或可错峰的 2×48GB 候选实例
- [ ] 在租用前确认 GPU 拓扑、NCCL、驱动/CUDA、CPU 内存、持久盘、网络和源码安装权限
- [ ] 原生克隆官方 H3 仓库并固定可运行 commit
- [ ] 先验证 FL2VA、2×48GB INT8、保守 5 秒 768p 样例
- [ ] 记录环境、命令、峰值 GPU/CPU 内存、耗时、错误和可解码输出
- **Exit gate:** 一个官方 H3 最小样例在目标实例真实完成，且记录足以复现。

### Phase C: FLUX 最小验证与异步服务封装
- [ ] 原生运行 FLUX.2 Klein 9B 官方最小示例，记录模型与许可证信息
- [ ] 生成首帧、尾帧并做基础可解码检查
- [ ] 将 FLUX 封装为 `generate_image` / `get_generation_job` 异步服务
- **Exit gate:** 真实 job_id 状态可查询，成功与可恢复失败都有持久记录。

### Phase D: H3 服务封装与真实端到端集成
- [ ] 将 H3 封装为 `generate_video` / `get_generation_job` 异步服务
- [ ] 用实测适配器替换 `GENERATION_BACKEND=live` 的显式占位报错
- [ ] 跑通 DeepSeek → FLUX 首尾帧 → H3 → FFmpeg 的一个智影样例
- [ ] 记录质量报告、重试、运行 manifest、实际资源与成本
- **Exit gate:** 产出一个真实 5 秒、16:9、768p 样例；没有未标注的 Mock 结果混入。

### Phase E: 稳定、阈值校准与容器化
- [ ] 校准 OpenCLIP、首尾帧相似度和技术检查阈值
- [ ] 验证超时、OOM、恢复和最大两次重试
- [ ] 固定依赖与镜像版本；分别容器化稳定后的服务，再使用 Compose 联调
- **Exit gate:** 新环境可按部署文档复现一个真实样例。

## Key Questions
1. 无 DeepSeek API Key 时如何验收？→ 提供 deterministic fallback，保证 Mock 链路可跑
2. Mock 媒体如何生成？→ Pillow 生成占位图；用最小合法 mp4 或 ffmpeg 合成占位视频

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 包名 `slmagent` | 与项目名一致，避免与行业 SLM 歧义 |
| `GENERATION_BACKEND=mock` 默认 | 阶段 A 不依赖 GPU |
| LLM 可切换 mock/live | 无 key 也能跑通 UI 与状态图 |
| 单主 Agent LangGraph | 符合基线已确认设计 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| winget/GitHub ffmpeg download timeout | 1 | Use imageio-ffmpeg bundle |
| DeepSeek Storyboard `shot_id` int vs str | 1 | Coerce in Pydantic + prompt tighten; re-probe PASS |

## Notes
- 不得虚构推理速度、显存、成功率
- 未实测能力不得写成已实现
