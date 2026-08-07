#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

command -v nvidia-smi >/dev/null || { echo "An NVIDIA runtime is required"; exit 1; }
command -v conda >/dev/null || { echo "AutoDL Miniconda is required"; exit 1; }
git lfs install
git lfs pull --include="upstream/nvidia-warp-garmentcode/**"
uv sync --extra worker

if [ ! -x .conda/garmentcode/bin/python ]; then
  conda create --prefix "$repo_dir/.conda/garmentcode" python=3.10 pip -y
fi
.conda/garmentcode/bin/pip install -r environments/autodl/requirements.lock.txt
if [ ! -f upstream/nvidia-warp-garmentcode/warp/bin/warp.so ]; then
  (
    cd upstream/nvidia-warp-garmentcode
    "$repo_dir/.conda/garmentcode/bin/python" build_lib.py
  )
fi
.conda/garmentcode/bin/pip install -e upstream/nvidia-warp-garmentcode
.conda/garmentcode/bin/pip install --no-deps -e upstream/garmentcode

echo "Build the vendored Warp fork according to upstream/nvidia-warp-garmentcode/README.md."
echo "Set GARMENTCAD_SIM_COMMAND='.conda/garmentcode/bin/python scripts/autodl-runner.py --input {input} --output {output}'"
echo "Then run scripts/start-worker.sh."
