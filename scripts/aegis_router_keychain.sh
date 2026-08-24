#!/bin/bash
# LaunchAgent entrypoint: injects an xAI key from macOS Keychain if present.
# It intentionally emits no secret and runs normally without a key.
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: aegis_router_keychain.sh PYTHON HOST PORT" >&2
  exit 64
fi

AEGIS_ROUTER_PYTHON="$1"
AEGIS_ROUTER_HOST="$2"
AEGIS_ROUTER_PORT="$3"

if AEGIS_XAI_KEY=$(/usr/bin/security find-generic-password \
  -a "$USER" -s "aegis.xai.api-key" -w 2>/dev/null); then
  export XAI_API_KEY="$AEGIS_XAI_KEY"
fi
unset AEGIS_XAI_KEY 2>/dev/null || true

exec "$AEGIS_ROUTER_PYTHON" -m aegis serve \
  --host "$AEGIS_ROUTER_HOST" --port "$AEGIS_ROUTER_PORT" --foreground
