#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$repo_dir/build/valentina-qbs"
app="$(find "$build_dir/release" -type d -path '*/Valentina.*/*.app' -print -quit)"
test -n "$app"

export GARMENTCAD_VALENTINA_COMMAND="$app/Contents/MacOS/Valentina"
exec uv run pytest -q \
    "$repo_dir/tests/test_native_valentina.py" \
    "$repo_dir/tests/test_corpus.py" \
    "$repo_dir/tests/test_recipes.py"
