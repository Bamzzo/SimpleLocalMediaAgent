# Findings

## Confirmed Baseline
- Project: SLMAgent — Simple Local Media Agent
- P0: 全自动 5 秒、16:9、768p 宣传镜头验证
- Stack: Gradio → FastAPI → LangGraph → DeepSeek + FLUX + H3 + FFmpeg
- Tools: generate_image / generate_video / get_generation_job
- Skills: creative-storyboard, flux-image-production, h3-video-production

## Constraints
- No real model deployment yet — mock only in Phase A
- Do not invent metrics (VRAM, latency, success rate, quality thresholds)
- Local ≠ offline; DeepSeek via API; media models self-hosted when ready
- Max 2 retries per generation stage

## Resources
- FLUX.2 Klein 9B: https://huggingface.co/black-forest-labs/FLUX.2-klein-9B
- MiniMax-H3: https://huggingface.co/MiniMaxAI/MiniMax-H3

## Phase A Acceptance Evidence (2026-08-07)
- `pytest -q`: 4 passed (includes playable Mock video probe assertion).
- API health returns `generation_backend=mock`, `llm_mode=mock`.
- Gradio and API both returned HTTP 200 from `127.0.0.1:7860` and `127.0.0.1:8000`.
- Early sample `runs/20260807_044848_AIGC_4167fa/` proved upload/manifest path, but MP4s were 89-byte placeholders (no system ffmpeg).
- Phase A.1 fix: depend on `imageio-ffmpeg` (winget/GitHub system install timed out). Mock H3 now encodes real H.264 silent mp4; tiny placeholder fallback removed.
- Playable sample: `runs/20260807_050513_AIGC_bf60a9/` — `h3_raw.mp4` / `result.mp4` ≈16KB, ffmpeg probe duration=5.0s, has_video=true; ref in project `uploads/`.
- Evidence file: `runs/_manual_accept/phase_a1_evidence.json`.
- Browser final click-preview still recommended once; objective decode gate is closed.

## Phase A.2 DeepSeek Live JSON (2026-08-07)
- Endpoint/model: `https://api.deepseek.com` / `deepseek-chat` (API reported `deepseek-v4-flash`).
- Cases: default_brief, script_mode, brief_with_reference — all PASS after fix.
- Failure observed then fixed: `shot_id` returned as int; `Shot.shot_id` now coerces to string.
- Evidence: `docs/DEEPSEEK_LIVE_JSON_PROBE.md`, `runs/_deepseek_live_probe/probe_20260807_051043.json`.
- `.env` restored to `LLM_MODE=mock`. No FLUX/H3 live calls.
- Independent audit reran `pytest -q`: 4 passed. `.env` is ignored by Git; no secret was read or exposed during the audit.
