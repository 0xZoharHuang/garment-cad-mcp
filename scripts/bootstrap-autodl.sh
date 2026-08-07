#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

command -v nvidia-smi >/dev/null || { echo "An NVIDIA runtime is required"; exit 1; }
command -v conda >/dev/null || { echo "AutoDL Miniconda is required"; exit 1; }
command -v nvcc >/dev/null || { echo "CUDA Toolkit with nvcc is required"; exit 1; }
if ! command -v uv >/dev/null; then
  python -m pip install "uv==0.8.12"
fi
uv sync --frozen --extra worker

if [ ! -x .conda/garmentcode/bin/python ]; then
  conda create --prefix "$repo_dir/.conda/garmentcode" python=3.10 pip -y
fi
.conda/garmentcode/bin/pip install --disable-pip-version-check \
  -r environments/autodl/requirements.lock.txt
if [ ! -f upstream/nvidia-warp-garmentcode/warp/bin/warp.so ]; then
  cuda_path="${CUDA_HOME:-${CUDA_PATH:-$(dirname "$(dirname "$(command -v nvcc)")")}}"
  "$repo_dir/.conda/garmentcode/bin/python" \
    "$repo_dir/upstream/nvidia-warp-garmentcode/build_lib.py" \
    --cuda_path "$cuda_path" --mode release --no_standalone --no_verbose
fi
.conda/garmentcode/bin/pip install -e upstream/nvidia-warp-garmentcode
.conda/garmentcode/bin/pip install --no-deps -e upstream/garmentcode
PYTHONPATH="$repo_dir/upstream/garmentcode:$repo_dir/upstream/nvidia-warp-garmentcode" \
  .conda/garmentcode/bin/python scripts/autodl-runner.py --preflight

echo "Pinned CUDA Warp and GarmentCode runner verified."
echo "Run scripts/start-worker.sh, exercise the official smoke job, then save this instance as an AutoDL private image."
