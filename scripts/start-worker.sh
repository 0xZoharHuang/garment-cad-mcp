#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

export GARMENTCAD_WORKER_HOST="${GARMENTCAD_WORKER_HOST:-127.0.0.1}"
if [ "$GARMENTCAD_WORKER_HOST" != "127.0.0.1" ] && [ "$GARMENTCAD_WORKER_HOST" != "localhost" ]; then
  echo "Worker must bind to loopback and be reached through the SSH tunnel" >&2
  exit 64
fi
export GARMENTCAD_SIM_COMMAND="${GARMENTCAD_SIM_COMMAND:-$repo_dir/.conda/garmentcode/bin/python $repo_dir/scripts/autodl-runner.py --input {input} --output {output}}"
exec uv run garment-sim-worker
