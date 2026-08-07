# Setup

## macOS arm64 control plane

```bash
./scripts/bootstrap-macos.sh
uv run garmentcad doctor
```

Build Valentina, Tape, and Puzzle from `upstream/valentina` with its documented Qt/CMake workflow.
Set `GARMENTCAD_VALENTINA_COMMAND` to the native JSON command host. Claude Code and compatible MCP
clients can load `.mcp.json`; commands default to preview-only.

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
