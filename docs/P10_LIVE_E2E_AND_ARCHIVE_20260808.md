# P10 Live End-to-End Run and Archive Record

## Scope

This record consolidates the first verified Gradio-to-live-media run and its
cloud evidence archive. It is an engineering evidence record, not a claim of
production readiness or media-quality certification.

## Verified Run

| Field | Value |
|---|---|
| Local project ID | `20260808_090019_AIGC_f25501` |
| Local generation backend | `live` |
| Local LLM mode | `mock` |
| Workflow | Gradio -> FastAPI -> LangGraph -> FLUX first/last frames -> H3 FL2VA -> local postprocess |
| FLUX image jobs | `f6d2e5b6f735450d8e15a9558cf34ded`, `cf4b6e7965484036a0d8e26326ad7669` |
| H3 video job | `ff616cd3-4ca1-463e-95e0-782e0ad945f5` |
| H3 output | 1344x768, approximately 5.18 seconds, video and audio present |
| Pipeline status | `completed_with_warnings` |
| Errors | None recorded |

The local run is retained at:

```text
runs/20260808_090019_AIGC_f25501/
```

It contains the brief, plan, storyboard, prompts, job records, quality report,
final manifest, both PNG keyframes, raw H3 video, and final result video.

## P10 Timing

| Stage | Measured duration |
|---|---:|
| FLUX image generation | 27.023 seconds |
| H3 video generation | 823.713 seconds |
| Postprocess | 0.105 seconds |

The historical P10 manifest was written before `started_at` was introduced.
Its `created_at` and `completed_at` are therefore both wrap-up timestamps.
New runs record `started_at`, set `created_at` to the same start time, and
record `completed_at` at pipeline completion.

## Cloud Artifact Evidence

| Artifact | Cloud SHA-256 |
|---|---|
| First frame PNG | `ff7ec96579513dde6175f255a3a3969618be110cae58103133f2eeca2abf9827` |
| Last frame PNG | `8930b5b3578b7ac65210680cff19fd5d1fe652fbc72aaf5040b9c667be9b8670` |
| H3 MP4 | `5dba33156dca23e08b418c178956bc821b12b343677e05200cda06254b93709f` |

The cloud evidence package was created after the P10 run:

```text
archives/p10_evidence_20260808_090019_AIGC_f25501.tar
archives/p10_evidence_20260808_090019_AIGC_f25501.tar.sha256
```

| Package property | Value |
|---|---|
| Tar size | 3,072,000 bytes |
| Tar SHA-256 | `fad70402b3e9d90140a6a8a51535c933d8b6bfe82315daf1ef627fd237b43611` |
| Internal manifest | 14 entries, all verified |
| Package contents | P10 media, FLUX/H3 logs and PID records, API contract snapshots, selected environment/version records |

The package deliberately excludes model weights, model caches, full virtual
environments, credentials, shell history, IDE files, and unrelated runs.

## Cloud Shutdown Record

After archive verification, the cloud worker services were stopped with
`SIGTERM` using their active PID files:

| Service | Active PID | Result |
|---|---:|---|
| FLUX | 25393 | Stopped; port 8001 no longer listening |
| H3 SGLang | 18415 | Stopped with scheduler children; port 30010 no longer listening |

The final `nvidia-smi` result showed GPUs 0, 1, and 2 at 0 MiB with no running
compute processes. No model weight, cache, run, or log directory was deleted.
Stopping services frees GPU resources but does not itself determine cloud
instance billing; instance shutdown or release remains an operator action.

## Local Code and Validation State

The live integration and P10 usability work remain uncommitted as of this
record. The working tree includes:

- live FLUX and H3 HTTP adapters;
- cloud artifact path handoff from FLUX to H3;
- live polling timeout and route selection;
- P9 smoke scripts and isolated HTTP-contract tests;
- P10 Gradio/API truthfulness fixes;
- updated planning and evidence documentation.

The latest local suite result is:

```text
21 passed, 1 Starlette/httpx deprecation warning
```

The Gradio completion summary now displays the API-reported `backend` and
`llm_mode`; its initial page banner states only the Gradio process
configuration. This avoids representing a run with a label derived from a
different process environment.

## Known Limits

- The P10 run used `llm_mode=mock`; it is not an end-to-end live DeepSeek
  planning demonstration.
- OpenCLIP thresholds and first/last-frame similarity thresholds have not been
  calibrated, which accounts for the completed-with-warnings status.
- This was a single serial validation run, not a concurrency, retry, OOM,
  resilience, security, or production-load validation.
- Some historical Ruff findings remain outside this focused change set,
  principally `Optional[T]` style and pre-existing long-line findings.
- The cloud evidence package does not replace the local source tree or local
  run manifest; both must be retained for a complete project record.

## Recommended Next Order

1. Review and commit the local source, tests, and documentation on a dedicated
   branch.
2. Keep the P10 run directory and cloud evidence tar as immutable evidence;
   avoid committing media to normal source history unless that is an explicit
   repository policy.
3. Decide whether to run a dedicated DeepSeek-live P10 validation.
4. Calibrate quality thresholds and define retry/OOM acceptance criteria before
   treating the workflow as stable.
5. After local evidence is retained and the operator confirms provider billing
   semantics, shut down or release the cloud instance.
