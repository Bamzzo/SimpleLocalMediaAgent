"""Run one audited local-to-cloud FLUX tunnel smoke test.

The FLUX worker must already be running on the cloud instance and exposed only
through an existing SSH local forward. This script deliberately does not start
SSH, modify environment files, or involve the H3 backend.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from slmagent.contracts.models import JobStatus
from slmagent.services.flux.live_backend import FluxHttpBackend

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-url", default="http://127.0.0.1:18001")
    parser.add_argument(
        "--prompt",
        default="A studio photograph of a compact brushed-metal desk lamp on a white table, soft daylight, clean background.",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout-sec", type=float, default=90.0)
    parser.add_argument("--poll-interval-sec", type=float, default=0.5)
    parser.add_argument("--run-id", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = args.run_id or f"p7b_flux_tunnel_{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    output_path = ROOT / "runs" / run_id / "images" / "flux_p7b.png"
    evidence_path = ROOT / "runs" / run_id / "evidence" / "flux_p7b_result.json"

    backend = FluxHttpBackend(args.service_url, timeout_sec=30.0)
    submitted = backend.generate_image(
        prompt=args.prompt,
        output_path=output_path,
        output_name=output_path.name,
        aspect_ratio="1:1",
        seed=args.seed,
        remote_run_id=run_id,
    )
    job = submitted
    deadline = time.monotonic() + args.timeout_sec
    while job.status in {JobStatus.QUEUED, JobStatus.RUNNING} and time.monotonic() < deadline:
        time.sleep(args.poll_interval_sec)
        job = backend.get_job(job.job_id)

    result: dict[str, object] = {
        "phase": "P7B",
        "service_url": args.service_url,
        "remote_run_id": run_id,
        "submitted_job": submitted.model_dump(mode="json"),
        "final_job": job.model_dump(mode="json"),
    }
    if job.status == JobStatus.SUCCEEDED and output_path.is_file():
        with Image.open(output_path) as image:
            result["local_png"] = {
                "path": str(output_path),
                "mode": image.mode,
                "width": image.width,
                "height": image.height,
                "bytes": output_path.stat().st_size,
                "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            }
    else:
        result["failure"] = {
            "reason": "Job did not complete with a downloaded local PNG before the timeout.",
            "timeout_sec": args.timeout_sec,
        }

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if "local_png" in result else 1


if __name__ == "__main__":
    raise SystemExit(main())
