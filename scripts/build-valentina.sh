#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
profile=garmentcad-qt6
build_dir="$repo_dir/build/valentina-qbs"

command -v qbs >/dev/null || { echo "Qbs is required"; exit 1; }
qbs setup-toolchains /usr/bin/clang garmentcad-clang >/dev/null
qbs setup-qt "$(command -v qmake)" "$profile" >/dev/null
qbs config "profiles.$profile.baseProfile" garmentcad-clang
qbs resolve \
  -d "$build_dir" \
  -f "$repo_dir/upstream/valentina/valentina.qbs" \
  profile:"$profile" \
  config:release \
  modules.buildconfig.runMacDeployQt:false \
  projects.Valentina.enableSigning:false
qbs build \
  --no-install \
  -d "$build_dir" \
  -f "$repo_dir/upstream/valentina/valentina.qbs" \
  profile:"$profile" \
  config:release \
  modules.buildconfig.runMacDeployQt:false \
  projects.Valentina.enableSigning:false

property_framework="$(find "$build_dir/release" -type d -path '*VPropertyExplorerLib.*/*VPropertyExplorerLib.framework' -print -quit)"
parser_framework="$(find "$build_dir/release" -type d -path '*QMUParserLib.*/*QMUParserLib.framework' -print -quit)"
plugin_dir="$(qmake -query QT_INSTALL_PLUGINS)"
for app_name in Valentina Tape Puzzle; do
  app="$(find "$build_dir/release" -type d -path "*/$app_name.*/*.app" -print -quit)"
  test -n "$app"
  mkdir -p "$app/Contents/Frameworks"
  ditto "$property_framework" "$app/Contents/Frameworks/VPropertyExplorerLib.framework"
  ditto "$parser_framework" "$app/Contents/Frameworks/QMUParserLib.framework"
  mkdir -p "$app/Contents/PlugIns/imageformats"
  ditto \
    "$plugin_dir/imageformats/libqtiff.dylib" \
    "$app/Contents/PlugIns/imageformats/libqtiff.dylib"
  macdeployqt "$app" \
    -no-strip \
    -no-plugins \
    -no-codesign \
    -libpath="$app/Contents/Frameworks"

  # The two Valentina frameworks are built before macdeployqt runs.  Unlike the
  # app executables, macdeployqt does not rewrite their Homebrew dependencies,
  # which otherwise loads a second copy of Qt and aborts in Objective-C startup.
  while IFS= read -r binary; do
    while IFS= read -r dependency; do
      relative_dependency="${dependency#*/lib/}"
      install_name_tool \
        -change "$dependency" \
        "@loader_path/../../../$relative_dependency" \
        "$binary"
    done < <(
      otool -L "$binary" |
        awk '$1 ~ /^\/opt\/homebrew\/.*\/lib\// { print $1 }'
    )
  done < <(
    find "$app/Contents/Frameworks" -type f \
      \( -name VPropertyExplorerLib -o -name QMUParserLib \)
  )

  # macdeployqt's -no-plugins mode is intentional: ship the TIFF writer used
  # by the export contract plus the two platform backends required by desktop
  # use and headless smoke tests.
  mkdir -p "$app/Contents/PlugIns/platforms"
  for platform_plugin in libqcocoa.dylib libqoffscreen.dylib; do
    ditto \
      "$plugin_dir/platforms/$platform_plugin" \
      "$app/Contents/PlugIns/platforms/$platform_plugin"
    install_name_tool \
      -add_rpath "@loader_path/../../Frameworks" \
      "$app/Contents/PlugIns/platforms/$platform_plugin"
  done

  codesign --force --deep --sign - "$app"
done
