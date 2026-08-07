#!/usr/bin/env python3
"""Pinned GarmentCode/Warp mesh, simulation, and programmable multi-view runner."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
GARMENTCODE = REPOSITORY / "upstream/garmentcode"
WARP = REPOSITORY / "upstream/nvidia-warp-garmentcode"
sys.path[:0] = [str(GARMENTCODE), str(WARP)]
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def _load_mapping(path: Path) -> dict:
    if path.suffix.lower() == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        import yaml

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def _safe_input(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise FileNotFoundError(f"Bundle input is missing or unsafe: {relative}")
    return path


def _deep_update(target: dict, source: dict) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _camera_pose(center, eye):
    import numpy as np

    forward = center - eye
    forward = forward / np.linalg.norm(forward)
    world_up = np.array([0.0, 1.0, 0.0])
    if abs(float(np.dot(forward, world_up))) > 0.98:
        world_up = np.array([0.0, 0.0, 1.0])
    right = np.cross(forward, world_up)
    right = right / np.linalg.norm(right)
    up = np.cross(right, forward)
    pose = np.eye(4)
    pose[:3, 0] = right
    pose[:3, 1] = up
    pose[:3, 2] = -forward
    pose[:3, 3] = eye
    return pose


def _render_views(
    garment_path: Path, body_path: Path, camera_config: dict, output: Path
) -> list[str]:
    import numpy as np
    import pyrender
    import trimesh
    from PIL import Image

    garment = trimesh.load(garment_path, force="mesh", process=False)
    body = trimesh.load(body_path, force="mesh", process=False)
    garment.vertices = garment.vertices / 100.0
    body.vertices = body.vertices / 100.0
    combined_min = np.minimum(garment.bounds[0], body.bounds[0])
    combined_max = np.maximum(garment.bounds[1], body.bounds[1])
    center = (combined_min + combined_max) / 2.0
    diagonal = float(np.linalg.norm(combined_max - combined_min))
    width, height = camera_config.get("resolution", [800, 800])
    render_root = output / "renders"
    render_root.mkdir(parents=True, exist_ok=True)
    rendered = []
    for view in camera_config["views"]:
        scene = pyrender.Scene(bg_color=(1.0, 1.0, 1.0, 1.0), ambient_light=(0.25, 0.25, 0.25))
        garment_material = pyrender.MetallicRoughnessMaterial(
            baseColorFactor=(0.85, 0.85, 0.88, 1.0), roughnessFactor=0.8, doubleSided=True
        )
        body_material = pyrender.MetallicRoughnessMaterial(
            baseColorFactor=(0.12, 0.12, 0.14, 1.0), roughnessFactor=0.7
        )
        scene.add(pyrender.Mesh.from_trimesh(garment, material=garment_material, smooth=True))
        scene.add(pyrender.Mesh.from_trimesh(body, material=body_material, smooth=True))
        if view.get("camera_location_mm") is not None:
            eye = np.asarray(view["camera_location_mm"], dtype=float) / 1000.0
        else:
            azimuth = float(view.get("azimuth_deg", 180 if view.get("side") == "back" else 0))
            elevation = float(view.get("elevation_deg", 0))
            azimuth_rad = math.radians(azimuth)
            elevation_rad = math.radians(elevation)
            direction = np.array(
                [
                    math.sin(azimuth_rad) * math.cos(elevation_rad),
                    math.sin(elevation_rad),
                    math.cos(azimuth_rad) * math.cos(elevation_rad),
                ]
            )
            distance = max(diagonal, 0.1) * float(view.get("distance_scale", 1.6))
            eye = center + direction * distance
        pose = _camera_pose(center, eye)
        scene.add(pyrender.PerspectiveCamera(yfov=math.radians(50)), pose=pose)
        scene.add(pyrender.DirectionalLight(color=np.ones(3), intensity=4.0), pose=pose)
        renderer = pyrender.OffscreenRenderer(
            viewport_width=int(width), viewport_height=int(height)
        )
        try:
            color, _ = renderer.render(scene, flags=pyrender.RenderFlags.RGBA)
        finally:
            renderer.delete()
        target = render_root / f"{view['name']}.png"
        Image.fromarray(color).save(target, "PNG")
        rendered.append(str(target.relative_to(output)))
    return rendered


def _preflight() -> dict:
    import warp as wp

    wp.init()
    revisions = json.loads((REPOSITORY / ".upstream-revisions.json").read_text(encoding="utf-8"))
    return {
        "ok": bool(wp.is_cuda_available()),
        "cuda": bool(wp.is_cuda_available()),
        "device": str(wp.get_device()),
        "upstream_revisions": {name: item["revision"] for name, item in revisions.items()},
    }


def run(input_root: Path, output: Path) -> dict:
    import trimesh
    import warp as wp
    from pygarment.data_config import Properties
    from pygarment.meshgen.boxmeshgen import BoxMesh
    from pygarment.meshgen.sim_config import PathCofig
    from pygarment.meshgen.simulation import run_sim

    wp.init()
    if not wp.is_cuda_available() and os.environ.get("GARMENTCAD_ALLOW_CPU_SIM") != "1":
        raise RuntimeError(
            "Pinned Warp did not detect CUDA; refusing an accidental CPU production run"
        )
    task = _load_mapping(input_root / "job.json")
    inputs = task["inputs"]
    body_source = _safe_input(input_root, inputs["body_mesh"])
    body_measurements = _safe_input(input_root, inputs["body_measurements"])
    simulation_config = _safe_input(input_root, inputs["simulation_config"])
    fabric_config = _safe_input(input_root, inputs["fabric"])
    camera_path = _safe_input(input_root, inputs["camera_config"])
    camera_config = _load_mapping(camera_path)
    expected_views = [view.get("name") for view in camera_config.get("views", [])]
    if not expected_views or expected_views != task.get("expected_views"):
        raise ValueError("Camera config views do not match the signed simulation task")
    output.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="garmentcad-autodl-") as temporary:
        work = Path(temporary)
        bodies = work / "bodies"
        element = work / "element"
        bodies.mkdir()
        element.mkdir()
        body_name = "body"
        body_obj = bodies / f"{body_name}.obj"
        trimesh.load(body_source, force="mesh", process=False).export(body_obj)
        shutil.copy2(body_measurements, bodies / f"{body_name}.yaml")
        segmentation_source = _safe_input(input_root, inputs["body_segmentation"])
        shutil.copy2(segmentation_source, bodies / "ggg_body_segmentation.json")
        shutil.copy2(input_root / "garmentcode.json", element / "garment_specification.json")
        (element / "design_params.yaml").write_text("design: {}\n", encoding="utf-8")
        system = {
            "output": str(work / "native-output"),
            "datasets_path": "",
            "datasets_sim": "",
            "sim_configs_path": str(simulation_config.parent),
            "bodies_default_path": str(bodies),
            "body_samples_path": "",
        }
        (work / "system.json").write_text(json.dumps(system), encoding="utf-8")
        props = Properties(str(simulation_config))
        fabric = _load_mapping(fabric_config)
        material = fabric.get("material", fabric)
        props.properties.setdefault("sim", {}).setdefault("config", {}).setdefault("material", {})
        _deep_update(props.properties["sim"]["config"]["material"], material)
        props.set_section_stats(
            "sim",
            fails={},
            sim_time={},
            spf={},
            fin_frame={},
            body_collisions={},
            self_collisions={},
        )
        props.set_section_stats("render", render_time={})
        props.properties.setdefault("render", {}).setdefault("config", {})["sides"] = []
        texture = GARMENTCODE / "assets/img/fabric_texture.png"
        props.properties["render"]["config"].setdefault("uv_texture", {})[
            "fabric_grain_texture_path"
        ] = str(texture)

        previous = Path.cwd()
        try:
            os.chdir(work)
            paths = PathCofig(
                in_element_path=element,
                out_path=work / "native-output",
                in_name="garment",
                body_name=body_name,
                add_timestamp=False,
            )
            resolution = props.properties["sim"]["config"].get("resolution_scale", 1.0)
            box_mesh = BoxMesh(paths.in_g_spec, resolution)
            box_mesh.load()
            box_mesh.serialize(
                paths,
                store_panels=False,
                uv_config=props.properties["render"]["config"]["uv_texture"],
            )
            props.serialize(paths.element_sim_props)
            run_sim(
                box_mesh.name,
                props,
                paths,
                save_v_norms=False,
                store_usd=False,
                optimize_storage=False,
                verbose=False,
            )
        finally:
            os.chdir(previous)

        fail_count, failures = props.count_fails()
        if fail_count:
            raise RuntimeError(f"GarmentCode simulation quality checks failed: {failures}")
        shutil.copy2(paths.g_sim, output / "garment-simulated.obj")
        rendered = _render_views(paths.g_sim, body_obj, camera_config, output)
        props.serialize(output / "simulation-metrics.yaml")
        diagnostics = {
            "runner": "pinned-garmentcode-warp",
            "cuda": bool(wp.is_cuda_available()),
            "device": str(wp.get_device()),
            "elapsed_seconds": time.monotonic() - started,
            "views": rendered,
            "mesh": "garment-simulated.obj",
        }
        (output / "diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2), encoding="utf-8"
        )
        return diagnostics


def main() -> int:
    args = _arguments()
    if args.preflight:
        report = _preflight()
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    if args.input is None or args.output is None:
        raise SystemExit("--input and --output are required unless --preflight is used")
    try:
        report = run(args.input.resolve(), args.output.resolve())
        print(json.dumps(report))
        return 0
    except Exception as error:
        args.output.mkdir(parents=True, exist_ok=True)
        diagnostics = {
            "runner": "pinned-garmentcode-warp",
            "error_type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(limit=20),
        }
        (args.output / "diagnostics.json").write_text(
            json.dumps(diagnostics, indent=2), encoding="utf-8"
        )
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
