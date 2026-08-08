"""Run one audited local-to-cloud MiniMax-H3 FL2VA tunnel smoke test.

The cloud H3 worker and an SSH local forward must already be running. This
script submits exactly one task, never resubmits it, and downloads a completed
MP4 into one local run directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from slmagent.contracts.models import JobStatus
from slmagent.services.h3.live_backend import H3HttpBackend
from slmagent.services.media_tools import probe_media

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-url", default="http://127.0.0.1:13011")
    parser.add_argument(
        "--first-frame-remote-path",
        required=True,
        help="Cloud /root/autodl-tmp/slmagent-live-runs/... first-frame PNG path.",
    )
    parser.add_argument(
        "--last-frame-remote-path",
        required=True,
        help="Cloud /root/autodl-tmp/slmagent-live-runs/... last-frame PNG path.",
    )
    parser.add_argument(
        "--prompt",
        default="Continue naturally between the supplied endpoint frames with synchronized ambient sound.",
    )
    parser.add_argument("--seed", type=int, default=2101)
    parser.add_argument("--timeout-sec", type=float, default=1800.0)
    parser.add_argument("--poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--phase", default="P8F")
    parser.add_argument("--output-name", default="h3_p8f.mp4")
    parser.add_argument("--evidence-name", default="h3_p8f_result.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = args.run_id or f"p8f_h3_tunnel_{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    output_path = ROOT / "runs" / run_id / "videos" / args.output_name
    evidence_path = ROOT / "runs" / run_id / "evidence" / args.evidence_name

    backend = H3HttpBackend(args.service_url, timeout_sec=30.0)
    submitted = backend.generate_video(
        prompt=args.prompt,
        output_path=output_path,
        output_name=output_path.name,
        first_frame_remote_path=args.first_frame_remote_path,
        last_frame_remote_path=args.last_frame_remote_path,
        seed=args.seed,
    )
    job = submitted
    deadline = time.monotonic() + args.timeout_sec
    while job.status in {JobStatus.QUEUED, JobStatus.RUNNING} and time.monotonic() < deadline:
        time.sleep(args.poll_interval_sec)
        job = backend.get_job(job.job_id)

    result: dict[str, object] = {
        "phase": args.phase,
        "service_url": args.service_url,
        "submitted_job": submitted.model_dump(mode="json"),
        "final_job": job.model_dump(mode="json"),
    }
    if job.status == JobStatus.SUCCEEDED and output_path.is_file():
        result["local_mp4"] = {
            "path": str(output_path),
            "bytes": output_path.stat().st_size,
            "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "probe": probe_media(output_path),
        }
    else:
        result["failure"] = {
            "reason": "Job did not complete with a downloaded local MP4 before the timeout.",
            "timeout_sec": args.timeout_sec,
        }

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if "local_mp4" in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
