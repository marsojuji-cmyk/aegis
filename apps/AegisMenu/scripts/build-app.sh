#!/usr/bin/env bash
# Build AegisMenu.app (SwiftUI menu bar) into dist/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="${ROOT}/dist"
APP="${DIST}/AegisMenu.app"
BIN_NAME="AegisMenu"

cd "$ROOT"
echo "[aegis-app] swift build -c release"
swift build -c release --product AegisMenu

BIN="$(swift build -c release --show-bin-path)/${BIN_NAME}"
if [[ ! -x "$BIN" ]]; then
  echo "missing binary: $BIN" >&2
  exit 1
fi

rm -rf "$APP"
mkdir -p "${APP}/Contents/MacOS" "${APP}/Contents/Resources"
cp "$BIN" "${APP}/Contents/MacOS/${BIN_NAME}"
chmod +x "${APP}/Contents/MacOS/${BIN_NAME}"
cp "${ROOT}/AppBundle/Info.plist" "${APP}/Contents/Info.plist"

# ad-hoc sign for local run (Gatekeeper-friendly enough for self-built)
if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP" 2>/dev/null || true
fi

echo "[aegis-app] built ${APP}"
echo "  open: open \"${APP}\""
echo "  or:   aegis app open"
