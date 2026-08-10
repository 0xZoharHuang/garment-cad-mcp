#!/usr/bin/env python3
"""Exercise the real AutoDL worker with GarmentCode's pinned official shirt assets."""

from __future__ import annotations

import argparse
import io
import json
import sys
import tarfile
import time
from pathlib import Path

import httpx

from garmentcad.storage import canonical_json, sha256_bytes

REPOSITORY = Path(__file__).resolve().parents[1]
GARMENTCODE = REPOSITORY / "upstream/garmentcode"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-url", default="http://127.0.0.1:8765")
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    return parser.parse_args()


def official_bundle() -> tuple[bytes, str]:
    assets = GARMENTCODE / "assets"
    inputs = {
        "body_mesh": "simulation/body/mean_all.obj",
        "body_measurements": "simulation/body/mean_all.yaml",
        "body_segmentation": "simulation/body/ggg_body_segmentation.json",
        "fabric": "simulation/fabric/default.json",
        "simulation_config": "simulation/config/default_sim_props.yaml",
        "camera_config": "simulation/camera/multiview.json",
    }
    camera = {
        "schema_version": "1.0",
        "resolution": [512, 512],
        "views": [
            {"name": "front", "side": "front"},
            {"name": "back", "side": "back"},
            {"name": "left", "azimuth_deg": -90},
            {"name": "right", "azimuth_deg": 90},
        ],
    }
    task = {
        "schema_version": "1.0",
        "project_id": "garmentcode-official-shirt-smoke",
        "revision": 0,
        "units": "mm",
        "body_mesh_units": "m",
        "pattern_snapshot_format": "garmentcode",
        "inputs": inputs,
        "expected_views": [view["name"] for view in camera["views"]],
    }
    garment = (assets / "Patterns/shirt_mean_specification.json").read_bytes()
    files = {
        "garmentcode.json": garment,
        "pattern_snapshot.json": garment,
        "assembly/main.garmentcode.json": canonical_json(
            {
                "schema_version": "2.0",
                "engine": "GarmentCode",
                "units": "mm",
                "source_project_id": "garmentcode-official-shirt-smoke",
                "source_revision": 0,
                "source_pattern_hash": None,
                "panels": {},
                "interfaces": {},
                "stitches": {},
                "components": {},
                "native_pattern": json.loads(garment),
            }
        ),
        "job.json": canonical_json(task),
        inputs["body_mesh"]: (assets / "bodies/mean_all.obj").read_bytes(),
        inputs["body_measurements"]: (assets / "bodies/mean_all.yaml").read_bytes(),
        inputs["body_segmentation"]: (
            assets / "bodies/ggg_body_segmentation.json"
        ).read_bytes(),
        inputs["fabric"]: canonical_json({"material": {}}),
        inputs["simulation_config"]: (
            assets / "Sim_props/default_sim_props.yaml"
        ).read_bytes(),
        inputs["camera_config"]: canonical_json(camera),
    }
    content_hash = sha256_bytes(
        b"".join(name.encode() + b"\0" + files[name] for name in sorted(files))
    )
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for name in sorted(files):
            info = tarfile.TarInfo(name)
            info.size = len(files[name])
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(files[name]))
    return stream.getvalue(), content_hash


def submit(client: httpx.Client, url: str, payload: bytes, content_hash: str) -> dict:
    response = client.post(
        f"{url}/v1/jobs",
        files={"bundle": ("official-shirt.tar.gz", payload, "application/gzip")},
        data={"content_hash": content_hash},
    )
    response.raise_for_status()
    return response.json()


def verify_completed_job(job: dict) -> set[str]:
    if job["status"] != "succeeded":
        raise RuntimeError(f"Official smoke job ended as {job['status']}")
    if job.get("diagnostics", {}).get("runner") != "pinned-garmentcode-warp":
        raise RuntimeError("Worker result was not produced by the pinned production runner")
    required = {
        f"artifacts/renders/{side}.png" for side in ("front", "back", "left", "right")
    }
    if not required <= set(job["artifacts"]):
        raise RuntimeError(f"Official smoke job omitted renders: {sorted(required)}")
    return required


def main() -> int:
    options = arguments()
    url = options.worker_url.rstrip("/")
    payload, content_hash = official_bundle()
    with httpx.Client(timeout=60.0) as client:
        health = client.get(f"{url}/health")
        health.raise_for_status()
        if not health.json().get("runner_configured"):
            raise RuntimeError(
                "Worker is healthy but its pinned simulation runner is not configured"
            )
        if health.json().get("runner_id") != "pinned-garmentcode-warp":
            raise RuntimeError(
                "Official smoke refuses an unidentified or fixture simulation runner"
            )
        first = submit(client, url, payload, content_hash)
        deadline = time.monotonic() + options.timeout_seconds
        while True:
            response = client.get(f"{url}/v1/jobs/{first['id']}")
            response.raise_for_status()
            job = response.json()
            if job["status"] in {"succeeded", "failed", "cancelled"}:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Official smoke job did not finish: {first['id']}")
            time.sleep(2)
        print(json.dumps(job, ensure_ascii=False, indent=2))
        required = verify_completed_job(job)
        for relative in sorted(required):
            artifact = client.get(
                f"{url}/v1/jobs/{job['id']}/artifacts/{relative.removeprefix('artifacts/')}"
            )
            artifact.raise_for_status()
            if not artifact.content.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError(f"Invalid PNG returned for {relative}")
        cached = submit(client, url, payload, content_hash)
        if cached["id"] != job["id"]:
            raise RuntimeError("Worker did not reuse the successful content-hash cache entry")
    print("Official GarmentCode mesh/simulation/multiview/cache smoke passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"AutoDL smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
