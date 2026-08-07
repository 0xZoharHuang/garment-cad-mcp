#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$repo_dir/build/valentina-qbs"

launch_app() {
  app_name="$1"
  project_path="${2:-}"
  app_path="$(find "$build_dir/release" -type d -path "*/$app_name.*/*.app" -print -quit 2>/dev/null || true)"
  if [ -z "$app_path" ]; then
    echo "$app_name is not built; run cmake --workflow --preset verify then cmake --build --preset valentina-guis"
    return 1
  fi
  if [ -z "$project_path" ]; then
    open "$app_path"
    return
  fi
  case "$app_name" in
    Valentina) document="$project_path/pattern/main.val" ;;
    Puzzle) document="$project_path/layout/main.vlt" ;;
    Tape)
      document="$(find "$project_path/measurements" -maxdepth 1 -type f \( -name '*.vit' -o -name '*.vst' \) -print -quit)"
      test -n "$document" || { echo "No .vit/.vst file exists in $project_path/measurements" >&2; return 66; }
      ;;
  esac
  test -f "$document" || { echo "Project document is missing: $document" >&2; return 66; }
  exec uv run --directory "$repo_dir" scripts/gui-session.py \
    --project "$project_path" -- "$app_path/Contents/MacOS/$app_name" "$document"
}

case "${1:-all}" in
  valentina) launch_app Valentina "${2:-}" ;;
  tape) launch_app Tape "${2:-}" ;;
  puzzle) launch_app Puzzle "${2:-}" ;;
  garmentcode)
    garmentcode_python="$repo_dir/build/garmentcode-venv/bin/python"
    test -x "$garmentcode_python" || {
      echo "GarmentCode is not bootstrapped; run ./scripts/bootstrap-macos.sh" >&2
      exit 69
    }
    export PYTHONPATH="$repo_dir/src:$repo_dir/upstream/garmentcode:$repo_dir/upstream/nvidia-warp-garmentcode"
    export GARMENTCAD_PROJECT_PATH="${2:-${GARMENTCAD_PROJECT_PATH:-}}"
    cd "$repo_dir/upstream/garmentcode"
    exec "$garmentcode_python" gui.py
    ;;
  all)
    launch_app Valentina
    launch_app Tape
    launch_app Puzzle
    ;;
  *) echo "usage: $0 [all|valentina|tape|puzzle|garmentcode] [project-path]"; exit 2 ;;
esac
