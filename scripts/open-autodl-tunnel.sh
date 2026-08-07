#!/usr/bin/env bash
set -euo pipefail

: "${GARMENTCAD_AUTODL_HOST:?Set GARMENTCAD_AUTODL_HOST}"
: "${GARMENTCAD_AUTODL_USER:?Set GARMENTCAD_AUTODL_USER}"

ssh_port="${GARMENTCAD_AUTODL_SSH_PORT:-22}"
remote_port="${GARMENTCAD_REMOTE_WORKER_PORT:-8765}"
local_port="${GARMENTCAD_LOCAL_WORKER_PORT:-8765}"
identity_args=()
if [ -n "${GARMENTCAD_AUTODL_IDENTITY_FILE:-}" ]; then
  identity_args=(-i "$GARMENTCAD_AUTODL_IDENTITY_FILE")
fi

echo "Opening http://127.0.0.1:$local_port -> AutoDL worker 127.0.0.1:$remote_port" >&2
exec ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -p "$ssh_port" \
  "${identity_args[@]}" \
  -L "127.0.0.1:$local_port:127.0.0.1:$remote_port" \
  "$GARMENTCAD_AUTODL_USER@$GARMENTCAD_AUTODL_HOST"
