#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
build_dir="$repo_dir/build/valentina-qbs"

for app_name in Valentina Tape Puzzle; do
  app="$(find "$build_dir/release" -type d -path "*/$app_name.*/*.app" -print -quit)"
  if [ -z "$app" ]; then
    echo "$app_name is not built" >&2
    exit 1
  fi

  executable="$app/Contents/MacOS/$app_name"
  output="$(QT_QPA_PLATFORM=offscreen "$executable" --version 2>&1)"
  printf '%s\n' "$output"
  grep -q "$app_name 1.1.0" <<<"$output"

  if otool -L \
    "$app/Contents/Frameworks/VPropertyExplorerLib.framework/Versions/1/VPropertyExplorerLib" \
    "$app/Contents/Frameworks/QMUParserLib.framework/Versions/2/QMUParserLib" |
    grep -q '/opt/homebrew/.*/lib/Qt'; then
    echo "$app_name contains mixed Homebrew and bundled Qt references" >&2
    exit 1
  fi

  test -f "$app/Contents/PlugIns/platforms/libqcocoa.dylib"
  test -f "$app/Contents/PlugIns/platforms/libqoffscreen.dylib"
  test -f "$app/Contents/PlugIns/imageformats/libqtiff.dylib"
  codesign --verify --deep --strict "$app"
done
