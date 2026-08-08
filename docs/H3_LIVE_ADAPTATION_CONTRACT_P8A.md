# H3 Live Adaptation Contract (P8A)

Status: verified design input; no H3 process was started in P8A.

## Purpose

Define the minimal, evidence-backed boundary between the local SLMAgent
application and the cloud-local MiniMax-H3 FL2VA worker. This document does
not enable `GENERATION_BACKEND=live`.

## Verified cloud worker facts

The archived native H3 validation proves this worker contract on the current
AutoDL class of instance:

- SGLang binds only to `127.0.0.1:30010` and uses `CUDA_VISIBLE_DEVICES=1,2`.
- `GET /health` returns HTTP 200 when the worker is ready.
- `POST /v1/videos` accepts an FL2VA JSON request and returns a queued video
  object with an `id`.
- `GET /v1/videos/{id}` returns asynchronous `queued`, `running`, `completed`,
  or `failed` status.
- `GET /v1/videos/{id}/content` returned HTTP 200 for the completed MP4.
- A verified five-second, 768p-short-edge, 16:9 job took 799 seconds from
  submit to completed. A 120-second orchestration timeout is therefore unsafe.

The local process must reach this worker only through a second SSH forward:

```text
local H3HttpBackend -> http://127.0.0.1:13011 -> SSH -> cloud 127.0.0.1:30010
```

No public H3 listener is permitted.

P8E used local port 13011 because 13010 was already occupied by an unrelated
Windows service. The cloud H3 port remains 30010; the local forward port is
configured through `H3_SERVICE_URL`.

## Fixed first-live scope

Only this request class is allowed initially:

- `task`: `fl2va`
- duration: five seconds
- `target.short_edge`: `768`
- `target.aspect_ratio`: `16:9`
- exactly two image conditions: first keyframe `frame_index=0`, last keyframe
  `frame_index=-1`
- one output, fifty inference steps, `flow_shift=12.0`,
  `audio_flow_shift=3.0`
- model path: `/root/autodl-tmp/models/MiniMax-H3`

The cloud request must use cloud-local file URIs, for example:

```json
{
  "conditions": [
    {"type": "image", "uri": "file:///root/autodl-tmp/slmagent-live-runs/<run_id>/images/first_frame.png", "role": "keyframe", "frame_index": 0},
    {"type": "image", "uri": "file:///root/autodl-tmp/slmagent-live-runs/<run_id>/images/last_frame.png", "role": "keyframe", "frame_index": -1}
  ]
}
```

Windows `runs/...` paths and `file:///D:/...` URIs are invalid H3 inputs.

## Required local adapter behavior

`H3HttpBackend` will mirror `FluxHttpBackend` without mock fallback:

1. Submit the fixed-scope request to `/v1/videos`.
2. Map H3 `queued` and `running` directly to local `JobStatus`; map
   `completed` to `succeeded` and `failed` to `failed`.
3. Preserve H3 `id`, `file_path` / `file_paths`, progress, resource fields,
   and inference time in `VideoJob.meta`.
4. On completion, download `/v1/videos/{id}/content` to the local requested
   MP4 path through a temporary `.part` file and atomically replace it.
5. Use `trust_env=False` for every tunnel request, matching the P7B FLUX
   correction that prevents workstation proxy interception.
6. Return structured `RecoverableError` values for connection, validation,
   remote HTTP, unexpected status, missing output, content type, and download
   failures. The adapter itself never resubmits a job.

## Required orchestration changes before live enablement

The current pipeline passes only local image paths into `VideoPrompt`; that is
insufficient for H3. Before enabling live mode it must add and persist:

- `first_frame_remote_path`
- `last_frame_remote_path`

These fields come from the successful FLUX jobs' `remote_output_path` metadata.
The local paths remain for image quality checks and UI display; the remote paths
are used only for the H3 request. Both must appear in the final live manifest.

The current `_wait_job(..., timeout_sec=120)` is also insufficient for video.
The live video path needs a separately configured timeout exceeding the
observed 799-second run, with no automatic resubmission merely because polling
outlasted the old mock-oriented limit.

## P8B acceptance tests (local only)

- exact `POST /v1/videos` payload, including the two cloud `file://` URIs;
- queued/running/completed/failed status mapping;
- completed MP4 content download to a local run path;
- structured 409/4xx/5xx and connection failure behavior;
- proxy bypass is asserted;
- no fallback to `MockH3Backend` when live is selected.

## P8C preflight and real-run gate

Before one H3 real task, verify on the cloud:

- `/usr/bin/ffprobe` is available;
- H3 assets and pinned environment are unchanged;
- GPU 1 and 2 are idle; GPU 0 remains free of FLUX;
- port 30010 is down before launch and binds only to 127.0.0.1 after launch;
- the remote FLUX image paths exist under `/root/autodl-tmp/slmagent-live-runs/`.

Only after P8B passes and P8C preflight is approved may one H3 FL2VA job be
submitted. FLUX and H3 remain serial: FLUX generates both frames and releases
GPU 0 before H3 begins.
