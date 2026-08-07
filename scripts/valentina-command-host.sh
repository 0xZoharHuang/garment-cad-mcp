#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$repo_dir/build/valentina-qbs"
app="$(find "$build_dir/release" -type d -path '*/Valentina.*/*.app' -print -quit)"
if [ -z "$app" ]; then
  echo "Valentina command host is not built; run: cmake --build --preset valentina-guis" >&2
  exit 1
fi

exec "$app/Contents/MacOS/Valentina"
