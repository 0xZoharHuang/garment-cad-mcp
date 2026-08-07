#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

command -v nvidia-smi >/dev/null || { echo "An NVIDIA runtime is required"; exit 1; }
git lfs install
git lfs pull --include="upstream/nvidia-warp-garmentcode/**"
uv sync --extra worker

echo "Build the vendored Warp fork according to upstream/nvidia-warp-garmentcode/README.md."
echo "Then set GARMENTCAD_SIM_COMMAND and run scripts/start-worker.sh."
