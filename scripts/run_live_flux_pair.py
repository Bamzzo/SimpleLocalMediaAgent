"""Generate one serial FLUX first/last frame pair through the SSH tunnel."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from PIL import Image

from slmagent.contracts.models import ImageJob, JobStatus
from slmagent.services.flux.live_backend import FluxHttpBackend

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service-url", default="http://127.0.0.1:18001")
    parser.add_argument("--run-id", default="p9b_flux_pair_20260808")
    parser.add_argument("--seed", type=int, default=2101)
    parser.add_argument("--timeout-sec", type=float, default=180.0)
    parser.add_argument(
        "--first-prompt",
        default="A cinematic wide studio shot of a brushed-metal desk lamp on a white table, soft daylight, clean background.",
    )
    parser.add_argument(
        "--last-prompt",
        default="The same brushed-metal desk lamp now glowing warmly on the white table, cinematic studio lighting, clean background.",
    )
    return parser.parse_args()


def wait_for_job(backend: FluxHttpBackend, submitted: ImageJob, timeout_sec: float) -> ImageJob:
    job = submitted
    deadline = time.monotonic() + timeout_sec
    while job.status in {JobStatus.QUEUED, JobStatus.RUNNING} and time.monotonic() < deadline:
        time.sleep(0.5)
        job = backend.get_job(job.job_id)
    return job


def main() -> int:
    args = parse_args()
    run_root = ROOT / "runs" / args.run_id
    image_root = run_root / "images"
    evidence_path = run_root / "evidence" / "flux_pair_p9b_result.json"
    backend = FluxHttpBackend(args.service_url, timeout_sec=30.0)
    results: dict[str, object] = {
        "phase": "P9B-A",
        "service_url": args.service_url,
        "remote_run_id": args.run_id,
        "frames": [],
    }

    for label, prompt, seed_offset in (
        ("first_frame", args.first_prompt, 0),
        ("last_frame", args.last_prompt, 1),
    ):
        output_path = image_root / f"{label}.png"
        submitted = backend.generate_image(
            prompt=prompt,
            output_path=output_path,
            output_name=output_path.name,
            aspect_ratio="16:9",
            seed=args.seed + seed_offset,
            remote_run_id=args.run_id,
        )
        job = wait_for_job(backend, submitted, args.timeout_sec)
        frame: dict[str, object] = {
            "label": label,
            "submitted_job": submitted.model_dump(mode="json"),
            "final_job": job.model_dump(mode="json"),
        }
        if job.status != JobStatus.SUCCEEDED or not output_path.is_file():
            results["failure"] = frame
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(json.dumps(results, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(results, ensure_ascii=True, indent=2))
            return 1
        with Image.open(output_path) as image:
            frame["local_png"] = {
                "path": str(output_path),
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "bytes": output_path.stat().st_size,
                "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            }
        results["frames"].append(frame)

    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(results, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
