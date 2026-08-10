#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
export GARMENTCAD_MCP_TOOL_MODE=eager
export GARMENTCAD_GARMENTCODE_COMMAND="$repo_dir/scripts/garmentcode-command-host.sh"
exec uv --directory "$repo_dir" run garmentcode-mcp
