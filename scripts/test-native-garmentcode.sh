#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
test -x "$repo_dir/build/garmentcode-venv/bin/python" || {
  echo "GarmentCode environment is missing; run ./scripts/bootstrap-macos.sh" >&2
  exit 69
}

export GARMENTCAD_GARMENTCODE_COMMAND="$repo_dir/scripts/garmentcode-command-host.sh"
exec uv run --directory "$repo_dir" pytest -q "$repo_dir/tests/test_native_garmentcode.py"
