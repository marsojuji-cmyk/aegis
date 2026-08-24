"""Frozen /v1 HTTP contract. Additive keys allowed; required keys never drop."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Set

from aegis import __version__

API_VERSION = "v1"

# Required JSON keys per frozen endpoint. Extra keys are allowed.
REQUIRED_KEYS: Dict[str, Set[str]] = {
    "GET /healthz": {"ok", "service", "version"},
    "GET /v1/health": {"ok", "service", "version"},
    "GET /v1/aegis/status": {"providers", "version", "daemon"},
    "GET /v1/aegis/budget": {"ok", "budget", "surplus", "version"},
    "GET /v1/aegis/ledger": {"ok", "count", "transactions", "version"},
    "GET /v1/aegis/spec": {"ok", "api_version", "endpoints", "kernel_syscalls", "version"},
    "GET /v1/aegis/kernel": {"ok", "kernel", "version"},
    "GET /v1/aegis/yield": {"ok", "yield", "version"},
    "GET /v1/aegis/evidence-yield": {
        "ok",
        "active_outcome",
        "evidence_health",
        "review_queue",
        "sources",
        "paused_circuits",
        "yield",
        "calibration",
        "version",
    },
    "GET /v1/aegis/autoscan": {
        "ok", "state", "scheduler_running", "approved_sources", "failures",
        "observed_cost_usd", "quarantine_enabled", "calibration", "version",
    },
    "POST /v1/aegis/run": {"ok"},
    "POST /v1/aegis/evidence-yield/govern": {"ok", "decision_id", "decision", "version"},
    "POST /v1/aegis/evidence-yield/outcome": {"ok", "outcome", "version"},
    "POST /v1/aegis/autoscan/control": {"ok", "action", "outbound_action_authorized", "version"},
}

KERNEL_SYSCALLS = (
    "status",
    "ps",
    "mem",
    "drivers",
    "score",
    "pack",
    "budget",
    "init",
    "backup",
    "restore",
    "yield_prove",
    "bench",
    "api_spec",
    "invest",
)


def spec() -> Dict[str, Any]:
    endpoints = []
    for name, keys in REQUIRED_KEYS.items():
        method, _, path = name.partition(" ")
        endpoints.append(
            {
                "method": method,
                "path": path,
                "required": sorted(keys),
            }
        )
    return {
        "ok": True,
        "api_version": API_VERSION,
        "stability": "frozen",
        "semver": __version__,
        "version": __version__,
        "endpoints": endpoints,
        "kernel_syscalls": list(KERNEL_SYSCALLS),
        "notes": "Required keys are a floor. Additional keys are non-breaking.",
    }


def check_payload(endpoint: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    required = REQUIRED_KEYS.get(endpoint)
    if required is None:
        return {"ok": False, "error": f"unknown endpoint {endpoint}", "missing": []}
    missing = sorted(k for k in required if k not in payload)
    return {
        "ok": not missing,
        "endpoint": endpoint,
        "missing": missing,
        "required": sorted(required),
    }


def check_all(samples: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for endpoint, payload in samples.items():
        results.append(check_payload(endpoint, payload))
    failed = [r for r in results if not r.get("ok")]
    return {"ok": not failed, "checked": len(results), "failed": failed, "results": results}
