#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--garmentcode-root", type=Path)
    return parser.parse_args()


def main() -> None:
    args = arguments()
    repository = Path(__file__).resolve().parents[1]
    garmentcode_root = (args.garmentcode_root or repository / "upstream/garmentcode").resolve()
    inputs = args.input.resolve()
    outputs = args.output.resolve()
    outputs.mkdir(parents=True, exist_ok=True)
    job = json.loads((inputs / "job.json").read_text(encoding="utf-8"))

    body_relative = job.get("active_body")
    if not body_relative:
        raise ValueError("Bundle job.json has no active_body")
    body = inputs / body_relative
    measurements = body.with_suffix(".yaml")
    if not body.is_file() or not measurements.is_file():
        raise FileNotFoundError("Active body mesh and same-stem YAML measurements are required")

    pattern_dir = outputs / "pattern_input"
    pattern_dir.mkdir(exist_ok=True)
    pattern = pattern_dir / "agent_specification.json"
    shutil.copy2(inputs / "garmentcode.json", pattern)

    simulation_config = job.get("active_simulation_config")
    if simulation_config:
        sim_props = inputs / simulation_config
    else:
        sim_props = garmentcode_root / "assets/Sim_props/default_sim_props.yaml"
    if not sim_props.is_file():
        raise FileNotFoundError(sim_props)

    system = {
        "output": str(outputs),
        "datasets_path": "",
        "datasets_sim": "",
        "sim_configs_path": str(sim_props.parent),
        "bodies_default_path": str(body.parent),
        "body_samples_path": "",
    }
    (garmentcode_root / "system.json").write_text(
        json.dumps(system, indent=2) + "\n", encoding="utf-8"
    )
    sys.path.insert(0, str(garmentcode_root))
    os.chdir(garmentcode_root)

    import pygarment.data_config as data_config
    import trimesh
    from pygarment.meshgen.boxmeshgen import BoxMesh
    from pygarment.meshgen.sim_config import PathCofig
    from pygarment.meshgen.simulation import run_sim

    props = data_config.Properties(str(sim_props))
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
    paths = PathCofig(
        in_element_path=pattern_dir,
        out_path=outputs,
        in_name="agent",
        body_name=body.stem,
        smpl_body=False,
        add_timestamp=False,
    )
    garment_mesh = BoxMesh(paths.in_g_spec, props["sim"]["config"]["resolution_scale"])
    garment_mesh.load()
    garment_mesh.serialize(
        paths,
        store_panels=False,
        uv_config=props["render"]["config"]["uv_texture"],
    )
    props.serialize(paths.element_sim_props)
    run_sim(
        garment_mesh.name,
        props,
        paths,
        save_v_norms=False,
        store_usd=True,
        optimize_storage=False,
        verbose=False,
    )
    if paths.g_sim.is_file():
        trimesh.load_mesh(paths.g_sim).export(paths.g_sim_glb)
    props.serialize(paths.element_sim_props)
    (outputs / "diagnostics.json").write_text(
        json.dumps(
            {
                "project_id": job["project_id"],
                "revision": job["revision"],
                "body": body_relative,
                "sim_config": str(sim_props),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
