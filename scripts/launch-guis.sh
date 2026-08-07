#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$repo_dir/build/valentina-qbs"

launch_app() {
  app_name="$1"
  app_path="$(find "$build_dir/release" -type d -path "*/$app_name.*/*.app" -print -quit 2>/dev/null || true)"
  if [ -z "$app_path" ]; then
    echo "$app_name is not built; run cmake --workflow --preset verify then cmake --build --preset valentina-guis"
    return 1
  fi
  open "$app_path"
}

case "${1:-all}" in
  valentina) launch_app Valentina ;;
  tape) launch_app Tape ;;
  puzzle) launch_app Puzzle ;;
  garmentcode) exec "$repo_dir/.conda/garmentcode/bin/python" "$repo_dir/upstream/garmentcode/gui.py" ;;
  all)
    launch_app Valentina
    launch_app Tape
    launch_app Puzzle
    ;;
  *) echo "usage: $0 [all|valentina|tape|puzzle|garmentcode]"; exit 2 ;;
esac
