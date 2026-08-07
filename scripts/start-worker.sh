#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

: "${GARMENTCAD_SIM_COMMAND:?Set GARMENTCAD_SIM_COMMAND with {input} and {output} placeholders}"
exec uv run garment-sim-worker
