"""Live R-012 probe: Hermes plugin loader + tool_execution middleware.

Uses the Hermes runtime (discover_plugins + run_tool_execution_middleware).
Does not start a Desktop/LLM session and does not claim token savings.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

HERMES_ROOT = Path.home() / ".hermes" / "hermes-agent"
ALLOWED = "/tmp/aegis-hermes-allowed"


def _gate_payload(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _die(msg: str, **extra) -> int:
    print(json.dumps({"ok": False, "error": msg, **extra}, indent=2))
    return 2


def main() -> int:
    if not HERMES_ROOT.is_dir():
        return _die("hermes-agent not found", path=str(HERMES_ROOT))
    sys.path.insert(0, str(HERMES_ROOT))

    from hermes_cli.middleware import run_tool_execution_middleware
    from hermes_cli.plugins import discover_plugins, get_plugin_manager

    discover_plugins(force=True)
    mgr = get_plugin_manager()
    loaded = mgr._plugins.get("aegis-gate")
    if loaded is None:
        return _die("aegis-gate not discovered under ~/.hermes/plugins")
    if not loaded.enabled:
        return _die(
            "aegis-gate discovered but not enabled",
            error_detail=getattr(loaded, "error", None),
        )
    middleware = list(mgr._middleware.get("tool_execution") or [])
    names = [getattr(fn, "__name__", repr(fn)) for fn in middleware]
    if "hermes_tool_execution" not in names:
        return _die("hermes_tool_execution not registered", middleware=names)

    Path(ALLOWED).mkdir(parents=True, exist_ok=True)
    safe_path = f"{ALLOWED}/probe.txt"
    Path(safe_path).write_text("probe\n", encoding="utf-8")

    report: dict = {
        "ok": True,
        "plugin": {
            "key": "aegis-gate",
            "enabled": True,
            "error": loaded.error,
            "middleware": getattr(loaded, "middleware_registered", []),
        },
        "token_efficiency": None,
        "token_benchmark": "not-run",
        "note": "No LLM session. Do not treat probe timings as token savings.",
    }

    # 1. Allowed low-risk read through Hermes middleware.
    ran: list = []

    def allow_next(args):
        ran.append(dict(args))
        return f"read:{args.get('filepath')}"

    t0 = time.perf_counter()
    allowed = run_tool_execution_middleware(
        "read_file",
        {"filepath": safe_path},
        allow_next,
        session_id="r012-allow",
        environment="probe",
        scope={"allowed_domains": [ALLOWED]},
    )
    allow_ms = round((time.perf_counter() - t0) * 1000, 3)
    report["allowed"] = {
        "result": allowed,
        "next_call_invoked": bool(ran),
        "elapsed_ms": allow_ms,
    }
    if not ran:
        return _die("allowed call did not reach next_call", report=report)

    # 2. Unknown tool denied before next_call.
    blocked: list = []

    def deny_next(args):
        blocked.append(dict(args))
        return "should-not-run"

    t1 = time.perf_counter()
    denied = run_tool_execution_middleware(
        "launch_missiles",
        {"target": "/etc/passwd"},
        deny_next,
        session_id="r012-deny",
        environment="probe",
        scope={"allowed_domains": [ALLOWED]},
    )
    deny_ms = round((time.perf_counter() - t1) * 1000, 3)
    report["denied"] = {
        "result": denied,
        "next_call_invoked": bool(blocked),
        "elapsed_ms": deny_ms,
    }
    if blocked:
        return _die("denied call invoked next_call (bypass)", report=report)
    denied_payload = _gate_payload(denied)
    if denied_payload.get("blocked_by") != "aegis":
        return _die("denied call did not return AEGIS deny payload", report=report)

    # 3. Middleware exception fail-open: a raising callback before the gate
    # must not prevent the gate from running (Hermes skips the raiser).
    def raiser(**kwargs):
        raise RuntimeError("intentional middleware failure")

    original = list(mgr._middleware.get("tool_execution") or [])
    mgr._middleware["tool_execution"] = [raiser] + original
    try:
        still_blocked: list = []
        after_raise = run_tool_execution_middleware(
            "launch_missiles",
            {"target": "x"},
            lambda args: still_blocked.append(args) or "bypassed",
            session_id="r012-raise",
            environment="probe",
            scope={"allowed_domains": [ALLOWED]},
        )
    except Exception:
        mgr._middleware["tool_execution"] = original
        return _die(
            "middleware exception escaped the chain",
            traceback=traceback.format_exc(),
            report=report,
        )
    mgr._middleware["tool_execution"] = original
    after_raise_payload = _gate_payload(after_raise)
    report["exception_fail_open"] = {
        "result": after_raise_payload or after_raise,
        "next_call_invoked": bool(still_blocked),
        "gate_still_denied": after_raise_payload.get("blocked_by") == "aegis",
    }
    if still_blocked:
        return _die(
            "exception path invoked next_call (Hermes fail-open bypassed gate)",
            report=report,
        )
    if after_raise_payload.get("blocked_by") != "aegis":
        return _die(
            "after middleware exception, gate did not produce deny payload",
            report=report,
        )

    # 4. Our callback itself must not raise on garbage input.
    from aegis.wrappers.hermes_wrapper import hermes_tool_execution

    try:
        garbage = hermes_tool_execution(
            tool_name=None,
            args="bad",
            next_call=lambda args: (_ for _ in ()).throw(RuntimeError("nope")),
        )
    except Exception:
        return _die(
            "hermes_tool_execution raised (would fail-open to the tool)",
            traceback=traceback.format_exc(),
            report=report,
        )
    garbage_payload = _gate_payload(garbage)
    report["garbage_input"] = {
        "raised": False,
        "blocked_by": garbage_payload.get("blocked_by"),
        "decision": garbage_payload.get("decision"),
    }

    report["ok"] = True
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
