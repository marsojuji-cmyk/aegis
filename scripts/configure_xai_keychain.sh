#!/bin/bash
# Stores an existing xAI API key in the logged-in user's macOS Keychain, then
# reloads the local AEGIS router. It cannot create an xAI account or API key.
set -euo pipefail

printf 'Store an existing xAI API key in this Mac user Keychain? [y/N] '
read -r AEGIS_CONFIRM
if [ "$AEGIS_CONFIRM" != "y" ] && [ "$AEGIS_CONFIRM" != "Y" ]; then
  echo "Cancelled."
  exit 0
fi

read -r -s -p "xAI API key: " AEGIS_XAI_KEY
printf '\n'
if [ -z "$AEGIS_XAI_KEY" ]; then
  echo "No key entered; nothing changed." >&2
  exit 1
fi

/usr/bin/security add-generic-password -U \
  -a "$USER" -s "aegis.xai.api-key" -w "$AEGIS_XAI_KEY"
unset AEGIS_XAI_KEY

python3 -m aegis daemon install-login
python3 -m aegis daemon status
echo "Key stored and router reloaded. Run a bounded calibration before live use."
