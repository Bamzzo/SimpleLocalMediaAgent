# SLMAgent 阶段 A 验收与交接说明

**状态：Mock 主链路与 A.1 可播放媒体客观门槛已验收；浏览器点击预览建议再确认一次。真实模型、DeepSeek live 与云端环境均未验收。**

手工验收记录（2026-08-07）：
- 早期样例 `runs/20260807_044848_AIGC_4167fa/` 证明了 uploads/manifest，但 MP4 仅为 89 字节占位（无系统 ffmpeg）。
- A.1 修复后样例 `runs/20260807_050513_AIGC_bf60a9/`：`result.mp4` ≈16KB，ffmpeg 探测 duration=5.0s、has_video=true；证据见 `runs/_manual_accept/phase_a1_evidence.json`。
- ffmpeg 来源：`imageio-ffmpeg` 捆绑二进制（系统 winget 因 GitHub 网络失败）。
- `pytest` 4 passed；API `:8000` + Gradio `:7860` HTTP 200。

本文记录本轮对阶段 A 的完善，供 Cursor 或后续开发者继续工作时核对。它不改变 `PROJECT_BASELINE.md` 的 P0 边界，也不将 Mock 结果描述为 FLUX 或 MiniMax-H3 的真实能力。

## 本轮优化与原因

| 优化 | 为什么做 | 具体做法 |
|---|---|---|
| Gradio 经 FastAPI 调用编排 | 原界面直接导入并执行 LangGraph，与既定的 `Gradio → FastAPI → LangGraph` 架构不一致，容器化后也不利于服务边界管理。 | Gradio 将 `Brief` POST 到 `/pipeline/run`；API 地址和超时由 `API_BASE_URL`、`API_PIPELINE_TIMEOUT_SEC` 配置。 |
| 上传素材随项目落盘 | 临时目录中的参考图会失效，无法满足“每次运行可追踪、可恢复”的要求。 | Gradio 先放入共享 `RUNS_DIR/_uploads`；编排入口复制到本次运行的 `uploads/`，再写入 `brief.json`。 |
| 禁止 live 配置静默返回 Mock 结果 | `GENERATION_BACKEND=live` 过去仍创建 Mock 后端，容易误把占位媒体当成真实推理。 | 在尚未实现 FLUX/H3 HTTP 适配器前，live 模式明确抛出 `GenerationBackendUnavailable`。 |
| 扩展自动测试 | 之前仅验证 CLI 一条成功路径，无法覆盖 API 和上传追踪。 | 新增 API 冒烟测试、上传落盘测试、live 后端不得静默降级测试。 |
| 项目 ID 路径校验 | 项目状态接口会将 project_id 用于文件路径，需避免无效或穿越式路径。 | `ProjectStore.path` 仅接受字母、数字、下划线和连字符。 |

## 当前可证明的能力

- Mock LLM 生成结构化创意方案与单镜头分镜；
- Mock FLUX 生成首帧、尾帧占位图；
- Mock H3 生成占位视频，并经后处理生成最终文件；
- LangGraph 状态流、项目目录、manifest、质量检查与有限重试可运行；
- CLI 和 FastAPI 的 Mock 主路径有自动化测试；
- Gradio 已通过 API 访问后端，Docker Compose 中用共享 `runs` 卷传递运行结果和暂存上传素材。

## 仍不可宣称的事项

- 真实 DeepSeek JSON 输出稳定性；
- 真实 FLUX.2 Klein 9B 或 MiniMax-H3 推理；
- GPU/CUDA/INT8/多卡兼容性、显存、耗时、成功率和成本；
- OpenCLIP 阈值、真实视频质量和音频质量；
- 生产级异步队列。阶段 A 的 Mock 请求可以同步完成；真实模型服务必须在阶段 B/C 改为提交 job 后轮询。

## 阶段 A 验收步骤

1. 建立环境并安装依赖：`python -m venv .venv`，激活后执行 `pip install -e ".[dev]"`。
2. 复制 `.env.example` 为 `.env`，保持 `LLM_MODE=mock`、`GENERATION_BACKEND=mock`。
3. 执行 `pytest -q`：全部测试通过才算代码验收通过。
4. 执行 `python scripts/run_mock_pipeline.py`：检查新建的 `runs/<project_id>/` 中存在 `brief.json`、`creative_plan.json`、`storyboard.json`、`images/first_frame.png`、`images/last_frame.png`、`videos/h3_raw.mp4`、`final/result.mp4` 和 `final_manifest.json`。
5. 启动 API：`python -m slmagent.api.main`。另开终端启动 UI：`python -m slmagent.apps.gradio_app`。在浏览器提交默认示例和至少一张参考图。
6. 在 UI 中确认状态、两张图片和视频均显示；检查 manifest 中的 `brief.reference_image_paths` 指向该项目的 `uploads/`，而不是系统临时目录。
7. 保存测试时的 manifest 和终端输出。它们证明的是 Mock 链路，不是模型效果。

## 通过阶段 A 后的下一步

1. **DeepSeek live 小验证**：只配置 `LLM_API_KEY` 与 `LLM_MODE=live`，保持生成后端为 mock。用 3 个 Brief（默认宣传片、剧本输入、含参考图）记录原始响应、Pydantic 校验成功/失败和修复策略。该步骤通过后，才可将“DeepSeek 结构化输出已实测”标为完成。
2. **租机预检**：按 `PROJECT_BASELINE.md` 的检查表核实单机/多卡拓扑、驱动、CUDA、NCCL、持久盘、网络和镜像权限。未通过预检不下载大权重。
3. **优先 H3 最小示例**：在原生环境用官方仓库、固定 commit、FL2VA、2×48GB INT8 和保守画幅跑出一个 5 秒样本；记录完整环境、命令、GPU/CPU 内存、耗时、错误与文件可解码性。
4. **再验证 FLUX**：原生运行官方最小示例，确认 9B 权重、GPU 兼容和首尾帧输出，再封装其异步 FastAPI job 接口。
5. **替换 live 适配器并联调**：仅在上述两个最小示例都有实测证据后，实现 `GENERATION_BACKEND=live` 的 FLUX/H3 HTTP 客户端，保留 `job_id` 轮询、最多两次重试、manifest 与失败恢复。
6. **真实端到端验收后再容器化**：先完成一个智影 5 秒样片及记录，再按基线制作模型服务镜像和 Compose；不要在模型原生示例尚未稳定时排查 Docker 与模型问题的组合故障。
