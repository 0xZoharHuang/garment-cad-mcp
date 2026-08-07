#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
export GARMENTCAD_VALENTINA_COMMAND="$repo_dir/scripts/valentina-command-host.sh"
export GARMENTCAD_PUZZLE_COMMAND="$repo_dir/scripts/puzzle-command-host.sh"
exec uv run pytest -q "$repo_dir/tests/test_native_puzzle.py"
