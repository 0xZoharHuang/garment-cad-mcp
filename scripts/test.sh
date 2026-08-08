#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"

uv run scripts/generate-schemas.py --check
uv run scripts/generate-atomic-contracts.py --check
uv run scripts/generate-assembly-contracts.py --check
uv run scripts/check-garmentcode-coverage.py
uv run ruff check src tests scripts
uv run pytest
./scripts/test-native-valentina.sh
./scripts/test-native-puzzle.sh
./scripts/test-native-garmentcode.sh
./scripts/doctor.sh
