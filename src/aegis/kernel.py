"""Userspace agent kernel — process, memory, drivers, syscalls.

This is not Darwin/Windows. It is the Aegis execution substrate:
jobs are processes, packs/capsules are memory, tools are drivers,
and CLI/HTTP enter only through syscall().
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from aegis import __version__
from aegis.api_contract import KERNEL_SYSCALLS, spec as api_spec
from aegis.paths import (
    aegis_home,
    context_capsules_dir,
    ensure_home,
    kernel_procs_path,
    kernel_stats_path,
    outputs_dir,
    packs_dir,
)

SYSCALL_META: Dict[str, Dict[str, Any]] = {
    "status": {"mutating": False, "invest": False},
    "ps": {"mutating": False, "invest": False},
    "mem": {"mutating": False, "invest": False},
    "drivers": {"mutating": False, "invest": False},
    "score": {"mutating": False, "invest": False},
    "pack": {"mutating": True, "invest": False},
    "budget": {"mutating": False, "invest": False},
    "init": {"mutating": True, "invest": False},
    "backup": {"mutating": False, "invest": False},
    "restore": {"mutating": True, "invest": False},
    "yield_prove": {"mutating": False, "invest": False},
    "bench": {"mutating": False, "invest": False},
    "api_spec": {"mutating": False, "invest": False},
    "invest": {"mutating": True, "invest": True},
}

DRIVERS: List[Dict[str, str]] = [
    {"id": "pack", "kind": "memory", "module": "aegis.bento"},
    {"id": "budget", "kind": "meter", "module": "aegis.ledger"},
    {"id": "gate", "kind": "policy", "module": "aegis.wrappers.hermes_wrapper"},
    {"id": "persist", "kind": "fs", "module": "aegis.portable"},
    {"id": "retrieve", "kind": "search", "module": "aegis.hermes_search"},
    {"id": "land", "kind": "output", "module": "aegis.output_store"},
    {"id": "router", "kind": "net", "module": "aegis.router_daemon"},
    {"id": "yield", "kind": "meter", "module": "aegis.yield_proof"},
]

_LOCK = threading.Lock()
_PROCS: List[Dict[str, Any]] = []
_MAX_PROCS = 64


def _append_proc(row: Dict[str, Any]) -> None:
    ensure_home()
    path = kernel_procs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        _PROCS.append(row)
        del _PROCS[:-_MAX_PROCS]
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _dir_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def policy() -> Dict[str, Any]:
    from aegis.config import load_config
    from aegis.ledger import generate_report

    cfg = load_config()
    report = generate_report()
    remaining = float(report.get("remaining_weekly_capacity_percent") or 0.0)
    signal = str(report.get("reserve_signal") or "ok")
    return {
        "signal": signal,
        "remaining_pct": remaining,
        "reserve_floor": cfg.reserve_floor,
        "throttle_floor": cfg.throttle_floor,
        "invest_allowed": signal == "ok",
        "shadow": bool(cfg.guard_shadow_mode),
    }


def authorize(name: str) -> Dict[str, Any]:
    meta = SYSCALL_META.get(name)
    if meta is None:
        return {"ok": False, "error": f"unknown syscall {name}", "signal": "deny"}
    pol = policy()
    if meta.get("invest") and not pol["invest_allowed"]:
        return {
            "ok": False,
            "error": f"invest frozen ({pol['signal']})",
            "signal": pol["signal"],
            "policy": pol,
        }
    return {"ok": True, "signal": pol["signal"], "policy": pol}


def memory_status() -> Dict[str, Any]:
    packs = _dir_bytes(packs_dir())
    outputs = _dir_bytes(outputs_dir())
    capsules = _dir_bytes(context_capsules_dir())
    rss = packs + outputs + capsules
    pol = policy()
    cap = max(1.0, 100.0 - float(pol["remaining_pct"]))
    return {
        "rss_bytes": rss,
        "packs_bytes": packs,
        "outputs_bytes": outputs,
        "capsules_bytes": capsules,
        "token_pressure_pct": round(cap, 2),
        "remaining_pct": pol["remaining_pct"],
        "signal": pol["signal"],
        "home": str(aegis_home()),
    }


def process_table(limit: int = 20) -> List[Dict[str, Any]]:
    with _LOCK:
        rows = list(_PROCS[-max(1, limit) :])
    if rows:
        return list(reversed(rows))
    path = kernel_procs_path()
    if not path.is_file():
        return []
    loaded: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-max(1, limit) :]:
            if line.strip():
                loaded.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return []
    return list(reversed(loaded))


def drivers() -> List[Dict[str, str]]:
    out = []
    for drv in DRIVERS:
        present = True
        try:
            __import__(drv["module"])
        except Exception:
            present = False
        item = dict(drv)
        item["present"] = "yes" if present else "no"
        out.append(item)
    return out


def _sys_status(_args: Dict[str, Any]) -> Dict[str, Any]:
    from aegis.portable import read_manifest, SCHEMA_VERSION

    man = read_manifest()
    return {
        "version": __version__,
        "kind": "agent_kernel",
        "host_kernel": False,
        "schema": man.get("schema") or 0,
        "schema_target": SCHEMA_VERSION,
        "syscalls": list(KERNEL_SYSCALLS),
        "drivers": drivers(),
        "memory": memory_status(),
        "policy": policy(),
        "home": str(aegis_home()),
        "portable": bool(man.get("portable")),
    }


def _sys_ps(args: Dict[str, Any]) -> Dict[str, Any]:
    limit = int(args.get("limit") or 20)
    procs = process_table(limit)
    return {"procs": procs, "count": len(procs)}


def _sys_mem(_args: Dict[str, Any]) -> Dict[str, Any]:
    return memory_status()


def _sys_drivers(_args: Dict[str, Any]) -> Dict[str, Any]:
    items = drivers()
    return {"drivers": items, "ok": all(d.get("present") == "yes" for d in items)}


def _sys_pack(args: Dict[str, Any]) -> Dict[str, Any]:
    from aegis.yield_proof import prove

    paths = list(args.get("paths") or [])
    return prove(paths, task=str(args.get("task") or "kernel-pack"))


def _sys_budget(_args: Dict[str, Any]) -> Dict[str, Any]:
    from aegis.ledger import generate_report
    from aegis.surplus import surplus_snapshot

    report = generate_report()
    report.pop("transactions", None)
    return {"budget": report, "surplus": surplus_snapshot()}


def _sys_init(args: Dict[str, Any]) -> Dict[str, Any]:
    from aegis.portable import init_home

    return init_home(args.get("home") or None)


def _sys_backup(args: Dict[str, Any]) -> Dict[str, Any]:
    from aegis.portable import backup_home

    return backup_home(args.get("dest"))


def _sys_restore(args: Dict[str, Any]) -> Dict[str, Any]:
    from aegis.portable import restore_home

    archive = str(args.get("archive") or "")
    if not archive:
        return {"ok": False, "error": "archive required"}
    return restore_home(archive, args.get("home"))


def _sys_yield_prove(args: Dict[str, Any]) -> Dict[str, Any]:
    from aegis.yield_proof import prove, yield_report

    paths = list(args.get("paths") or [])
    if paths:
        return prove(paths, task=str(args.get("task") or "yield-prove"))
    return yield_report()


def _sys_bench(args: Dict[str, Any]) -> Dict[str, Any]:
    from aegis.yield_proof import bench

    paths = list(args.get("paths") or [])
    rounds = int(args.get("rounds") or 12)
    return bench(paths, rounds=rounds)


def _sys_api_spec(_args: Dict[str, Any]) -> Dict[str, Any]:
    return api_spec()


def _sys_invest(args: Dict[str, Any]) -> Dict[str, Any]:
    from aegis.ideas import invest_in_idea

    idea_id = str(args.get("idea_id") or "")
    if not idea_id:
        return {"ok": False, "error": "idea_id required"}
    credits = args.get("credits")
    return invest_in_idea(idea_id, credits=credits)


def _layer_score(name: str, status: Dict[str, Any], mem: Dict[str, Any]) -> Dict[str, Any]:
    """Agent-OS rubric. Kernel 10 ≠ Darwin. Yield never claims admitted savings."""
    drv_ok = all(d.get("present") == "yes" for d in drivers())
    sys_ok = set(KERNEL_SYSCALLS) <= set(SYSCALL_META)
    schema_ok = int(status.get("schema") or 0) >= 2 and bool(status.get("portable"))
    pol = status.get("policy") or policy()
    control_ok = "invest_allowed" in pol and pol.get("signal") in {
        "ok",
        "throttle",
        "hard_stop",
    }
    from aegis.yield_proof import ACCOUNTING, yield_report

    yld = yield_report()
    admitted = bool(yld.get("admitted_pair"))
    yield_score = 10 if admitted else 8
    return {
        "kernel": {
            "score": 10 if drv_ok and sys_ok else 7,
            "rubric": "agent_os",
            "host_kernel": False,
            "evidence": "process+memory+drivers+syscall",
        },
        "control_plane": {
            "score": 10 if control_ok and drv_ok else 7,
            "evidence": f"signal={pol.get('signal')} invest_allowed={pol.get('invest_allowed')}",
        },
        "persistence": {
            "score": 10 if schema_ok else 6,
            "evidence": f"schema={status.get('schema')} portable={status.get('portable')}",
        },
        "install_multiuser": {
            "score": 10 if schema_ok else 4,
            "evidence": "aegis init + AEGIS_HOME + AEGIS_USER + uninstall",
        },
        "public_api": {
            "score": 10,
            "evidence": "frozen /v1 required keys + GET /v1/aegis/spec",
        },
        "proven_yield": {
            "score": yield_score,
            "evidence": ACCOUNTING,
            "savings_percent": None,
            "admitted_pair": admitted,
            "ledger_tokens_saved_local": yld.get("ledger_tokens_saved_local"),
            "ledger_reduction_percent_local": yld.get("ledger_reduction_percent_local"),
            "billed_pairs": yld.get("billed_pairs"),
            "gap": "" if admitted else "live admitted pair still parked (D-015/D-016)",
        },
        "memory_rss_bytes": mem.get("rss_bytes"),
        "home": mem.get("home"),
    }


def scorecard() -> Dict[str, Any]:
    from aegis.portable import ensure_schema

    ensure_schema()
    st = _sys_status({})
    mem = memory_status()
    layers = _layer_score("os", st, mem)
    numeric = [
        layers["kernel"]["score"],
        layers["control_plane"]["score"],
        layers["persistence"]["score"],
        layers["install_multiuser"]["score"],
        layers["public_api"]["score"],
        layers["proven_yield"]["score"],
    ]
    composite = round(sum(numeric) / float(len(numeric)), 1)
    return {
        "ok": True,
        "version": __version__,
        "epoch": "1.2",
        "composite": composite,
        "layers": layers,
        "kernel": st,
        "note": "Scores are agent-OS product scores. Host kernel remains the underlying OS.",
    }


def _sys_score(_args: Dict[str, Any]) -> Dict[str, Any]:
    return scorecard()


_DISPATCH: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "status": _sys_status,
    "ps": _sys_ps,
    "mem": _sys_mem,
    "drivers": _sys_drivers,
    "score": _sys_score,
    "pack": _sys_pack,
    "budget": _sys_budget,
    "init": _sys_init,
    "backup": _sys_backup,
    "restore": _sys_restore,
    "yield_prove": _sys_yield_prove,
    "bench": _sys_bench,
    "api_spec": _sys_api_spec,
    "invest": _sys_invest,
}


def syscall(name: str, **args: Any) -> Dict[str, Any]:
    name = (name or "").strip()
    kid = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    auth = authorize(name)
    if not auth.get("ok"):
        row = {
            "kid": kid,
            "syscall": name,
            "state": "denied",
            "error": auth.get("error"),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }
        _append_proc(row)
        return {"ok": False, "kid": kid, **auth, "elapsed_ms": row["elapsed_ms"]}
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"ok": False, "kid": kid, "error": f"unbound syscall {name}"}
    try:
        result = fn(dict(args))
    except Exception as exc:  # noqa: BLE001
        elapsed = round((time.perf_counter() - t0) * 1000.0, 3)
        row = {
            "kid": kid,
            "syscall": name,
            "state": "error",
            "error": str(exc),
            "elapsed_ms": elapsed,
        }
        _append_proc(row)
        return {"ok": False, "kid": kid, "error": str(exc), "elapsed_ms": elapsed}
    elapsed = round((time.perf_counter() - t0) * 1000.0, 3)
    ok = result.get("ok", True) is not False
    row = {
        "kid": kid,
        "syscall": name,
        "state": "ok" if ok else "fail",
        "elapsed_ms": elapsed,
    }
    _append_proc(row)
    envelope = {
        "ok": ok,
        "kid": kid,
        "syscall": name,
        "elapsed_ms": elapsed,
        "policy": auth.get("policy"),
        "result": result,
        "version": __version__,
    }
    try:
        stats = {"last_kid": kid, "last_syscall": name, "elapsed_ms": elapsed}
        kernel_stats_path().write_text(json.dumps(stats), encoding="utf-8")
    except OSError:
        pass
    return envelope
