# Setup

## macOS arm64 control plane

```bash
./scripts/bootstrap-macos.sh
cmake --build --preset valentina-guis
uv run garmentcad doctor
```

Bootstrap creates the main uv environment, a separately locked GarmentCode compatibility environment,
and the pinned universal macOS CPU Warp library. The build produces Valentina, Tape, and Puzzle and
runs native command replay tests. For direct SDK use outside MCP, set:

```bash
export GARMENTCAD_VALENTINA_COMMAND="$PWD/scripts/valentina-command-host.sh"
export GARMENTCAD_GARMENTCODE_COMMAND="$PWD/scripts/garmentcode-command-host.sh"
```

Claude Code and compatible MCP clients load the same wrapper from `.mcp.json`; commands default to
preview-only.

Launch each upstream GUI through the reproducible wrappers:

```bash
./scripts/launch-guis.sh valentina
./scripts/launch-guis.sh tape
./scripts/launch-guis.sh puzzle
./scripts/launch-guis.sh garmentcode
```

## Valentina revision to GarmentCode

The SDK and `valentina_import_revision` MCP tool ask the native Valentina host to expand the
current `pattern/main.val`; they never parse or edit its XML in Python. Optional sewing semantics
live in `assembly/sewing-sidecar.json` and reference deterministic edge aliases from the native
snapshot:

```json
{
  "schema_version": "1.0",
  "interfaces": [
    {"alias": "front.side", "edges": ["FrontPanel.edge.0000"]},
    {"alias": "back.side", "edges": ["BackPanel.edge.0000"], "reverse": true}
  ],
  "stitches": [
    {
      "alias": "side.seam",
      "interface_a": "front.side",
      "interface_b": "back.side",
      "direction": "opposed"
    }
  ]
}
```

```python
from garmentcad.sdk import GarmentSDK

preview = GarmentSDK("./project").import_valentina_revision()
```

The contracts are generated as `schemas/pattern-snapshot.schema.json` and
`schemas/sewing-sidecar.schema.json`.

Export the current assembly through the same pinned native object model. OBJ and USDA contain the
panel initial 3D placements in millimetres; curved edges are sampled by GarmentCode before
triangulation. Repeating an export returns the same content-addressed URIs.

```python
artifacts = GarmentSDK("./project").export_garmentcode(["json", "obj", "usd"])
```

## AutoDL GPU worker

Clone this repository on AutoDL, then:

```bash
./scripts/bootstrap-autodl.sh
export GARMENTCAD_SIM_COMMAND='python /absolute/runner.py --input {input} --output {output}'
export GARMENTCAD_WORKER_HOST=127.0.0.1
./scripts/start-worker.sh
```

The runner receives an input directory containing `garmentcode.json`, `assembly.json`, and `job.json`.
It must write its mesh, structured metrics, and at least one PNG/JPEG into the output directory.
Use the vendored GarmentCode `pygarment.meshgen.simulation.run_sim` and custom Warp fork inside that
runner.

Keep the worker bound to loopback and open an SSH tunnel from the Mac:

```bash
ssh -N -L 8765:127.0.0.1:8765 user@autodl-host
export GARMENTCAD_WORKER_URL=http://127.0.0.1:8765
```
