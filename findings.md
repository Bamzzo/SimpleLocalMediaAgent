# Findings

## Confirmed Baseline
- Project: SLMAgent — Simple Local Media Agent
- P0: 全自动 5 秒、16:9、768p 宣传镜头验证
- Stack: Gradio → FastAPI → LangGraph → DeepSeek + FLUX + H3 + FFmpeg
- Tools: generate_image / generate_video / get_generation_job
- Skills: creative-storyboard, flux-image-production, h3-video-production

## Constraints
- Do not invent metrics (VRAM, latency, success rate, quality thresholds)
- Local ≠ offline; DeepSeek via API; media models self-hosted when ready
- Max 2 retries per generation stage
- `GENERATION_BACKEND=live` proves media adapters, not full LLM-live planning
- OpenCLIP / first-last frame similarity thresholds remain uncalibrated until measured

## Resources
- FLUX.2 Klein 9B: https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
- MiniMax-H3: https://huggingface.co/MiniMaxAI/MiniMax-H3

## Phase A Acceptance Evidence (2026-08-07)
- Mock end-to-end, playable placeholder mp4 via imageio-ffmpeg, Gradio→API boundary, upload persistence
- DeepSeek live JSON probe (generation still mock): `docs/DEEPSEEK_LIVE_JSON_PROBE.md`
- `.env` is gitignored; do not commit secrets

## P10 Real Media Evidence (2026-08-08)
- Run: `runs/20260808_090019_AIGC_f25501`
- `backend=live`, `llm_mode=mock`
- Jobs: FLUX first/last frames (`live_flux_http`) + H3 video (`live_h3_http`) succeeded
- Final media: ~1344x768, ~5.18s, audio present
- Warnings remain for uncalibrated OpenCLIP and frame-similarity checks
- Historical gap: this manifest’s `created_at`/`completed_at` were both wrap-up timestamps; newer code adds `started_at` and aligns `created_at` to run start (legacy files remain readable)

## P10 Wrap-up Fixes (local)
- Gradio UI must label media `live` when `GENERATION_BACKEND=live`
- Manifest timing fields: `started_at`, `created_at` (start), `completed_at` (finish)
- Still pending: orchestration LLM live, quality threshold calibration, deployment stability, archival

## What Must Not Be Claimed Yet
- Full DeepSeek-live planning in the P10 Gradio/API run (it was mock)
- Calibrated automatic semantic quality gates
- Production multi-tenant stability, fixed success rate, or commercial license clearance
