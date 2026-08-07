#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

command -v uv >/dev/null || { echo "uv is required: https://docs.astral.sh/uv/"; exit 1; }
command -v cmake >/dev/null || { echo "CMake is required"; exit 1; }
uv sync --extra dev --extra worker

echo "Python/MCP environment is ready."
echo "Valentina GUI uses its upstream Qt build; see docs/SETUP.md."
