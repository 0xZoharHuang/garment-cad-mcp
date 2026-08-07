#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
venv_dir="$repo_dir/build/garmentcode-venv"
python="$venv_dir/bin/python"
test -x "$python" || {
  echo "GarmentCode environment is missing; run ./scripts/bootstrap-macos.sh" >&2
  exit 69
}
export PYTHONPATH="$repo_dir/upstream/garmentcode"
exec "$python" "$repo_dir/scripts/garmentcode-native-host.py"
