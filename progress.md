# Progress Log

## 2026-08-07
- Received full PROJECT_BASELINE design document from user
- Workspace was empty (no git, no files)
- Persisted baseline: `docs/PROJECT_BASELINE.md`
- Scaffolded Phase A package `slmagent/` (contracts, LangGraph, FastAPI, Gradio, mock FLUX/H3, skills)
- Installed deps in `.venv`
- Later optimization round: Gradio→FastAPI boundary, upload-to-project, live-backend hard-fail, more tests; handoff at `docs/PHASE_A_ACCEPTANCE_AND_HANDOFF.md`
- `pytest -q` → **4 passed**
- Phase A manual acceptance (API + Gradio path + ref image): **PASS**
  - Sample run: `runs/20260807_044848_AIGC_4167fa/`
  - Ref copied to project `uploads/ref_product.png` (manifest paths under project, not temp)
  - Script: `scripts/manual_phase_a_accept.py`
  - Services left running for browser check: API `:8000`, Gradio `:7860`
- Still not claimed: real FLUX/H3, DeepSeek live JSON stability, performance/quality metrics

## 2026-08-07 — Independent acceptance review
- Confirmed the stated Phase A sample directory and manifest exist, including a project-local `uploads/ref_product.png`.
- Confirmed API `/health` and Gradio `/` each return HTTP 200.
- Confirmed Phase A automation remains at 4 passing tests.
- Found that ffmpeg/ffprobe are unavailable and the fallback MP4 files are only 89 bytes; added an explicit Phase A.1 gate for real Mock video playback before calling the browser visual check complete.
- Updated the next-step plan to sequence: finish Phase A.1 → DeepSeek live validation → server precheck/H3 first → FLUX → real integration → stabilization/containerization.

## 2026-08-07 — Phase A.1 playable Mock video
- winget FFmpeg / static-ffmpeg GitHub download timed out; used `imageio-ffmpeg` bundled binary instead.
- Wired `slmagent/services/media_tools.py` into Mock H3 encode, FFmpeg export, and quality probe; removed unplayable 89-byte fallback.
- `pytest -q` still 4 passed (now asserts playable final mp4).
- `scripts/manual_phase_a_accept.py` → **ACCEPTANCE PASS** with duration=5.0s / has_video / size≈16KB.
- Sample: `runs/20260807_050513_AIGC_bf60a9/`; evidence: `runs/_manual_accept/phase_a1_evidence.json`.
- API restarted with new code; Gradio+API still HTTP 200. Awaiting user browser click-preview and confirmation before A.2 (DeepSeek live).

## 2026-08-07 — Phase A.2 DeepSeek live JSON
- User confirmed browser can preview placeholder first/last frames and video → A.1 closed.
- Ran `scripts/deepseek_live_json_probe.py` with `LLM_MODE=live`, `GENERATION_BACKEND=mock`.
- First pass: CreativePlan 3/3 OK; Storyboard failed because DeepSeek returned `shot_id: 1` (int).
- Fix: coerce `shot_id` to str in `Shot` + stricter storyboard system prompt.
- Re-probe: **3/3 PASS** (`docs/DEEPSEEK_LIVE_JSON_PROBE.md`, `runs/_deepseek_live_probe/probe_20260807_051043.json`).
- Restored `.env` `LLM_MODE=mock`. `pytest -q` still 4 passed.

## 2026-08-07 — Phase A acceptance hardening
- Routed Gradio submissions through FastAPI, matching the intended service boundary.
- Persisted reference uploads inside each project run and added path validation for project reads.
- Made `GENERATION_BACKEND=live` fail explicitly until a real model adapter exists.
- Expanded automated coverage to CLI pipeline, API pipeline, upload persistence, and live-backend guard.
- Added `docs/PHASE_A_ACCEPTANCE_AND_HANDOFF.md` with acceptance steps and a gated Phase B/C sequence.

## 2026-08-07 — Phase A final audit
- Independently verified A.1 evidence: bundled ffmpeg is available, media probe reports a 5-second video, and the saved acceptance evidence records playable Mock output.
- Independently verified A.2 evidence: three DeepSeek live JSON cases pass after normalizing numeric `shot_id`; `.env` is restored to mock generation and mock LLM mode.
- Reran the automated suite: 4 passed. Phase A is formally closed.

## 2026-08-08 — P10 real media path (FLUX → H3 → Gradio)
- Evidence run: `runs/20260808_090019_AIGC_f25501`
- Manifest: `backend=live`, `llm_mode=mock` (DeepSeek planning still mock; not a full LLM-live claim)
- Real FLUX first/last frames succeeded (`live_flux_http`); real H3 video succeeded (`live_h3_http`)
- Final video probe: 1344x768, duration≈5.18s, has_audio=true; status `completed_with_warnings` (OpenCLIP / frame-similarity thresholds not calibrated)
- Phase B/C/D media minimum evidence is no longer “unstarted”

## 2026-08-08 — P10 local wrap-up fixes
- Gradio banner/media labels/footnotes now follow `GENERATION_BACKEND` (live vs mock); live results must not be labeled mock
- Manifest timing: record `started_at` at RECEIVE_INPUT; set `created_at=started_at`, `completed_at` at COMPLETE; legacy manifests without `started_at` still validate
- API `/health` note also reflects live/mock backend
- Docs updated: `task_plan.md`, `progress.md`, `findings.md`
- Remaining: LLM-live in orchestration, OpenCLIP/similarity calibration, deployment stability, archival
