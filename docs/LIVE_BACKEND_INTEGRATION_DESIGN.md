# Live Backend Integration Design

Status: proposed implementation contract.
Scope: connect the local SLMAgent application to cloud-hosted FLUX.2 Klein 9B and MiniMax-H3 services after their independent native validation.

## 1. Preconditions

The following native validations are complete and remain separate from this design:

- FLUX.2 Klein 9B produced one real 1024x1024 PNG on the cloud GPU 0 using local Diffusers weights.
- MiniMax-H3 FL2VA produced one real 5-second 768p video on cloud GPUs 1 and 2 using SGLang.

This design does not claim that SLMAgent can already call either model. It defines the interfaces required before that claim can be made.

## 2. Boundary Decision

SLMAgent runs locally. The model workers run on the cloud instance and bind only to `127.0.0.1`. SSH local port forwarding exposes each worker to the local application as a different localhost URL.

```text
Local SLMAgent                         SSH tunnel                 Cloud instance
----------------                      ------------               -----------------------
FluxHttpBackend  -> localhost:18001 -> 127.0.0.1:8001 -> FLUX worker (GPU 0)
H3HttpBackend    -> localhost:13011 -> 127.0.0.1:30010 -> SGLang H3 (GPU 1,2)
```

The cloud service ports must never be opened on a public interface.

## 3. Artifact Boundary

The existing Mock API accepts local `output_path`, `first_frame_path`, and `last_frame_path`. Those paths cannot be sent unchanged to a cloud service: a cloud `file://` URI resolves on the cloud instance, not on the Windows workstation.

For live mode, the authoritative media handoff is a cloud-side artifact workspace, for example:

```text
/root/autodl-tmp/slmagent-live-runs/<remote_run_id>/
  images/first_frame.png
  images/last_frame.png
  videos/h3_raw.mp4
```

The FLUX worker creates the frame artifacts in this workspace. The H3 worker receives their cloud-local paths. The local adapters download completed artifacts into the normal local `runs/<project_id>/` structure before quality checks and manifest writing.

This avoids relying on remote access to local paths, adding public object storage, or copying media through chat/terminal sessions.

## 4. Worker Contract

### 4.1 FLUX worker

The cloud FLUX worker will be a small local-only task service. It is not the public Hugging Face inference API.

Required endpoints:

| Endpoint | Request / behavior | Response |
|---|---|---|
| `GET /health` | Reports readiness without loading a new model. | `{ "ok": true, "service": "flux" }` |
| `POST /v1/images/generations` | Accepts one prompt, seed, dimensions, and a `remote_run_id` / output name. | Image job JSON |
| `GET /v1/images/{job_id}` | Returns current job status. | Image job JSON |
| `GET /v1/images/{job_id}/content` | Streams the completed PNG. | `image/png` |

The returned image job must contain a stable `id`, status (`queued`, `running`, `completed`, or `failed`), and a cloud-side `artifact_path` only for worker-to-worker handoff. It must never contain credentials.

### 4.2 H3 worker

SGLang already exposes a video job API. The integration wrapper must map SLMAgent's FL2VA request to the verified SGLang request format:

- submit to the existing video generation endpoint;
- use cloud-local first and last frame artifact paths;
- poll the returned video ID;
- download the completed MP4 using the video content endpoint.

The first integration supports only `FL2VA`, five seconds, 768p, and 16:9. Ref2VA, V2V, T2VA, longer duration, higher resolution, and batch requests remain out of scope.

## 5. Local Adapter Responsibilities

### FluxHttpBackend

- submits exactly one image task to `FLUX_SERVICE_URL`;
- maps remote status to `ImageJob` and maps remote errors to `RecoverableError`;
- downloads a completed PNG into the local project run;
- records the remote job ID and artifact metadata in `ImageJob.meta`;
- never falls back to `MockFluxBackend` when `GENERATION_BACKEND=live`.

### H3HttpBackend

- submits an FL2VA request to `H3_SERVICE_URL` using cloud artifact paths;
- maps remote status to `VideoJob`;
- downloads a completed MP4 into the local project run;
- maps timeout, connection, validation, and remote job errors to structured `RecoverableError` values;
- never submits a retry without the pipeline's explicit retry policy.

## 6. Configuration

All live endpoints are environment-backed and local by default:

```text
GENERATION_BACKEND=live
FLUX_SERVICE_URL=http://127.0.0.1:18001
H3_SERVICE_URL=http://127.0.0.1:13011
LIVE_REQUEST_TIMEOUT_SEC=<validated value>
LIVE_POLL_INTERVAL_SEC=<validated value>
```

No model token, SSH password, SSH private-key path, proxy URL, or remote shell command belongs in SLMAgent configuration, source control, logs, or manifests.

On the current Windows workstation, local port 13010 was already used by an
unrelated system service. P8E therefore verified port 13011 for the H3 SSH
forward. The cloud worker remains fixed at 127.0.0.1:30010; the local port is
an environment-level choice and must be checked before opening a tunnel.

## 7. Implementation Sequence

1. Add local HTTP-client adapters and isolated contract tests using mocked HTTP responses.
2. Create the cloud FLUX worker that implements the FLUX contract and writes only under the cloud live workspace.
3. Verify the FLUX worker through its localhost endpoint; stop it and confirm GPU release.
4. Establish one SSH tunnel and run a local adapter smoke test against the FLUX worker.
5. Add the H3 wrapper / adapter path using the verified SGLang API and cloud artifact workspace.
6. Establish the H3 tunnel and test its health/status path independently.
7. Run one serial end-to-end SLMAgent sample: FLUX first and last frames, then H3 FL2VA, then local download and technical checks.

## 8. First End-to-End Gate

The first live end-to-end run must meet all of these conditions:

- one shot only;
- FLUX runs before H3; no concurrent model loading or generation;
- no automatic retry beyond the existing explicit pipeline limit;
- each request, remote job ID, downloaded output, SHA256, duration, and error is stored in the run manifest;
- a failure at either worker stops the run and preserves evidence;
- Mock and live runs remain distinguishable by `backend` in the manifest and output metadata.

## 9. Deferred Work

- model worker authentication beyond SSH tunnel isolation;
- resumable cross-machine artifact transfer outside the cloud workspace;
- persistent queue / database;
- public deployment, CORS, multi-user access, and rate limits;
- Docker / Compose;
- performance, quality, concurrency, and cost commitments.
