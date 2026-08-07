#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/"; exit 1; }
command -v cmake >/dev/null || { echo "CMake is required"; exit 1; }
command -v qbs >/dev/null || { echo "Qbs is required (brew install qbs)"; exit 1; }
uv sync --extra dev --extra worker
garmentcode_venv="$repo_dir/build/garmentcode-venv"
UV_PROJECT_ENVIRONMENT="$garmentcode_venv" uv sync \
  --project "$repo_dir/environments/garmentcode" --frozen

warp_library="$repo_dir/upstream/nvidia-warp-garmentcode/warp/bin/libwarp.dylib"
if [ ! -f "$warp_library" ]; then
  echo "Building the pinned Warp CPU library for GarmentCode..."
  "$garmentcode_venv/bin/python" \
    "$repo_dir/upstream/nvidia-warp-garmentcode/build_lib.py" \
    --mode release --no_standalone --no_verbose
fi
cmake --preset macos-arm64-debug

echo "Python/MCP and GarmentCode compatibility environments are ready."
echo "Valentina GUI uses its upstream Qt build; see docs/SETUP.md."
