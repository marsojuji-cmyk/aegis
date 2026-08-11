# AegisMenu

Native **SwiftUI menu bar** app for Project Aegis (macOS 14+).

## What it does

| Surface | Role |
|---------|------|
| Menu bar extra | Live reserve signal, capacity, start/stop/restart daemon |
| Ledger window | Searchable table of `ledger.jsonl` via daemon API (local fallback) |
| Dashboard | Providers, weekly capacity, surplus credits, endpoints |

Talks to the background router:

- `GET /healthz`
- `GET /v1/aegis/status`
- `GET /v1/aegis/budget`
- `GET /v1/aegis/ledger?limit=…`

Daemon control shells out to `python3 -m aegis daemon …`.

## Build & run

```bash
# from repo
aegis app build
aegis app open

# or
cd apps/AegisMenu
./scripts/build-app.sh
open dist/AegisMenu.app
```

Requires Xcode / Swift 5.9+ toolchain.

## Layout

```
Sources/AegisMenu/
  AegisMenuApp.swift   # MenuBarExtra + windows
  MenuBarView.swift
  LedgerView.swift
  DashboardView.swift
  AegisClient.swift    # HTTP + local ledger fallback
  AegisStore.swift
  Models.swift
```
