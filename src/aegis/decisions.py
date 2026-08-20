"""Decision-register health. Every D- is keep, park, repair, or superseded.

Probes are local by default. `--live` may call Hermes (Nous) for usage.
`savings_percent` stays null unless an admitted pair exists.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from aegis import __version__
from aegis.config import load_config
from aegis.paths import aegis_home, hermes_index_notes_path

# Catalog order is the operator loop, not chronology.
DECISION_IDS = (
    "D-011",
    "D-012",
    "D-013",
    "D-014",
    "D-015",
    "D-016",
    "D-017",
    "D-018",
    "D-019",
    "D-020",
    "D-021",
    "D-022",
    "D-023",
    "D-024",
    "D-025",
    "D-026",
    "D-027",
    "D-028",
    "D-029",
    "D-030",
    "D-031",
    "D-032",
)


def _ok(did: str, *, verdict: str, aligned: bool, evidence: str, action: str) -> Dict[str, Any]:
    return {
        "id": did,
        "ok": aligned,
        "verdict": verdict,
        "aligned": aligned,
        "evidence": evidence,
        "action": action,
    }


def _probe_d011() -> Dict[str, Any]:
    cfg = load_config()
    shadow = bool(cfg.guard_shadow_mode)
    return _ok(
        "D-011",
        verdict="keep",
        aligned=shadow,
        evidence=f"guard_shadow_mode={shadow}",
        action="keep shadow; Q-011 stays open until explicitly thawed",
    )


def _probe_d012() -> Dict[str, Any]:
    return _ok(
        "D-012",
        verdict="park",
        aligned=True,
        evidence="official thresholds remain unofficial; baseline archived",
        action="do not promote local counters to official thresholds",
    )


def _probe_d013() -> Dict[str, Any]:
    from aegis.wrappers.hermes_wrapper import HermesWrapper, TOOL_CAPABILITIES

    w = HermesWrapper()
    denied = w.decide(
        {
            "tool_name": "launch_missiles",
            "args": {"target": "x"},
            "identity": {"agent": "hermes", "session_id": "health"},
            "scope": {"allowed_domains": ["/tmp/aegis-hermes-allowed"]},
        }
    )
    known = "read_file" in TOOL_CAPABILITIES
    aligned = denied.decision == "deny" and known
    return _ok(
        "D-013",
        verdict="keep",
        aligned=aligned,
        evidence=f"unknown-tool={denied.decision} catalog={known}",
        action="keep single gate; unknown stays fail-closed",
    )


def _probe_d014() -> Dict[str, Any]:
    plugin = Path.home() / ".hermes" / "plugins" / "aegis-gate"
    live = plugin.exists() or plugin.is_symlink()
    return _ok(
        "D-014",
        verdict="superseded",
        aligned=live,
        evidence=f"symlink_or_plugin={live}; live enable is D-017",
        action="keep historical; do not treat as the enable path",
    )


def _probe_d015() -> Dict[str, Any]:
    from aegis.yield_proof import admitted_pair_present

    admitted = admitted_pair_present()
    return _ok(
        "D-015",
        verdict="keep",
        aligned=not admitted,
        evidence=f"admitted_pair={admitted} savings_percent=null",
        action="keep admission before token_delta",
    )


def _probe_d016() -> Dict[str, Any]:
    return _ok(
        "D-016",
        verdict="keep",
        aligned=True,
        evidence="no model hunt in health; live token runs require named provider",
        action="use named Hermes/Nous path only when the operator authorizes",
    )


def _probe_d017() -> Dict[str, Any]:
    plugin = Path.home() / ".hermes" / "plugins" / "aegis-gate"
    return _ok(
        "D-017",
        verdict="keep",
        aligned=plugin.exists() or plugin.is_symlink(),
        evidence=f"aegis-gate present={plugin.exists() or plugin.is_symlink()}",
        action="keep live plugin; probe middleware separately",
    )


def _daemon_health() -> Dict[str, Any]:
    from aegis.daemon_control import daemon_status

    return daemon_status()


def _probe_d018() -> Dict[str, Any]:
    st = _daemon_health()
    running = bool(st.get("running"))
    health = st.get("health") or {}
    reachable = bool(health.get("reachable") or health.get("ok"))
    return _ok(
        "D-018",
        verdict="keep" if running and reachable else "repair",
        aligned=running and reachable,
        evidence=f"running={running} reachable={reachable} pid={st.get('pid')}",
        action="keep bind/health contract; restart if dead",
    )


def _probe_d019() -> Dict[str, Any]:
    from aegis.yield_proof import yield_is_honest, yield_report

    rep = yield_report()
    aligned = yield_is_honest(rep) and not rep.get("admitted_pair")
    return _ok(
        "D-019",
        verdict="park",
        aligned=aligned,
        evidence=(
            f"R-014 parked admitted_pair={rep.get('admitted_pair')} "
            f"billed_savings_percent={rep.get('savings_percent')}"
        ),
        action="keep Hermes pair parked; billed USD percent is D-040 tiny-chat only",
    )


def _probe_d020() -> Dict[str, Any]:
    from aegis.wrappers.hermes_wrapper import TOOL_CAPABILITIES

    need = ("memory", "session_search", "todo", "project_list")
    missing = [n for n in need if n not in TOOL_CAPABILITIES]
    return _ok(
        "D-020",
        verdict="keep",
        aligned=not missing,
        evidence=f"missing={missing or 'none'}",
        action="keep catalog; R-015 still open on memory domain",
    )


def _probe_d021() -> Dict[str, Any]:
    st = _daemon_health()
    health = st.get("health") or {}
    ver = str(health.get("version") or "")
    match = ver == __version__
    return _ok(
        "D-021",
        verdict="keep" if match else "repair",
        aligned=match and bool(health.get("ok") or health.get("reachable")),
        evidence=f"daemon={ver} product={__version__}",
        action="restart daemon when version lags product",
    )


def _probe_d022() -> Dict[str, Any]:
    from aegis.paths import hermes_index_files_path

    path = hermes_index_files_path()
    return _ok(
        "D-022",
        verdict="keep",
        aligned=True,
        evidence=f"files_index={'present' if path.is_file() else 'empty-ok'}",
        action="keep gated indexer; empty tree is valid",
    )


def _probe_d023() -> Dict[str, Any]:
    notes = hermes_index_notes_path()
    count = 0
    if notes.is_file():
        try:
            payload = json.loads(notes.read_text(encoding="utf-8"))
            count = int(payload.get("note_count") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            count = 0
    return _ok(
        "D-023",
        verdict="keep",
        aligned=count >= 0,
        evidence=f"notes={count}",
        action="keep bounded graph; empty default root remains valid",
    )


def _probe_d024() -> Dict[str, Any]:
    from aegis.hermes_search import unified_search

    hits = unified_search("aegis", limit=3)
    n = int(hits.get("hit_count") or 0)
    return _ok(
        "D-024",
        verdict="keep",
        aligned=True,
        evidence=f"search_hits={n} (zero is success)",
        action="keep local search; no external API",
    )


def _probe_d025() -> Dict[str, Any]:
    from aegis.sprints import list_sprints

    rows = list_sprints()
    return _ok(
        "D-025",
        verdict="keep",
        aligned=isinstance(rows, list),
        evidence=f"sprints={len(rows)}",
        action="keep CLI SoT; board is the human index",
    )


def _probe_d026() -> Dict[str, Any]:
    from aegis.cursor_bridge import pack_id_from_ctx

    pid = pack_id_from_ctx({"meta": {"pack_id": "abc123"}})
    return _ok(
        "D-026",
        verdict="keep",
        aligned=bool(pid),
        evidence=f"pack_id_lookup={pid}",
        action="keep capsule pack_id + empty-pack refuse",
    )


def _probe_d027() -> Dict[str, Any]:
    from aegis.cursor_bridge import CURSOR_SKILL_NAMES, agents_skills_dir

    root = agents_skills_dir()
    present = [n for n in CURSOR_SKILL_NAMES if (root / n / "SKILL.md").is_file()]
    return _ok(
        "D-027",
        verdict="keep" if len(present) == len(CURSOR_SKILL_NAMES) else "repair",
        aligned=len(present) == len(CURSOR_SKILL_NAMES),
        evidence=f"installed={len(present)}/{len(CURSOR_SKILL_NAMES)}",
        action="aegis cursor --install if any skill is missing",
    )


def _probe_d028() -> Dict[str, Any]:
    return _ok(
        "D-028",
        verdict="keep",
        aligned=True,
        evidence="shot-caller + Cursor-only still bind; 1.1.1 git-lag clause is spent",
        action="keep authority; do not revive the version-lag freeze",
    )


def _probe_d029() -> Dict[str, Any]:
    from aegis.cursor_bridge import CURSOR_SKILL_NAMES

    return _ok(
        "D-029",
        verdict="keep",
        aligned="aegis-flow" in CURSOR_SKILL_NAMES,
        evidence="aegis-flow in CURSOR_SKILL_NAMES",
        action="keep driver/car/track; Perplexity never edits",
    )


def _probe_d030() -> Dict[str, Any]:
    notes = hermes_index_notes_path()
    count = 0
    if notes.is_file():
        try:
            payload = json.loads(notes.read_text(encoding="utf-8"))
            count = int(payload.get("note_count") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            count = 0
    claimed = 20
    aligned = count >= claimed
    return _ok(
        "D-030",
        verdict="repair" if not aligned else "keep",
        aligned=aligned,
        evidence=f"index_notes={count} claimed={claimed}",
        action="rebuild named MUL graph or stop claiming 20 until the indexer lands",
    )


def _probe_d031() -> Dict[str, Any]:
    from aegis.api_contract import spec
    from aegis.doctor import doctor_report
    from aegis.portable import SCHEMA_VERSION, read_manifest

    man = read_manifest()
    report = doctor_report()
    spec_ok = spec().get("ok") is True
    ready = bool(report.get("product_ready"))
    schema = int(man.get("schema") or 0) >= SCHEMA_VERSION
    return _ok(
        "D-031",
        verdict="keep" if ready and spec_ok and schema else "repair",
        aligned=ready and spec_ok and schema,
        evidence=f"product_ready={ready} spec={spec_ok} schema={man.get('schema')}",
        action="keep portable program SKU; overlay remains knowledge",
    )


def _probe_d032() -> Dict[str, Any]:
    from aegis.config import load_config, opt_in
    from aegis.pack_cache import covering_pack
    from aegis.yield_proof import yield_is_honest, yield_report

    cfg = load_config()
    armed = [
        n
        for n in ("auto_tick", "auto_invest", "auto_apply_fixes", "auto_memory")
        if opt_in(cfg, n)
    ]
    yld = yield_report()
    honest = yield_is_honest(yld)
    aligned = callable(covering_pack) and not armed and honest
    return _ok(
        "D-032",
        verdict="keep" if aligned else "repair",
        aligned=aligned,
        evidence=f"covering=yes armed={armed or 'none'} savings_percent={yld.get('savings_percent')} routing={yld.get('routing_scope')}",
        action="keep covering reuse + hash verify; billed USD percent only; implement routing off",
    )


PROBES = {
    "D-011": _probe_d011,
    "D-012": _probe_d012,
    "D-013": _probe_d013,
    "D-014": _probe_d014,
    "D-015": _probe_d015,
    "D-016": _probe_d016,
    "D-017": _probe_d017,
    "D-018": _probe_d018,
    "D-019": _probe_d019,
    "D-020": _probe_d020,
    "D-021": _probe_d021,
    "D-022": _probe_d022,
    "D-023": _probe_d023,
    "D-024": _probe_d024,
    "D-025": _probe_d025,
    "D-026": _probe_d026,
    "D-027": _probe_d027,
    "D-028": _probe_d028,
    "D-029": _probe_d029,
    "D-030": _probe_d030,
    "D-031": _probe_d031,
    "D-032": _probe_d032,
}


def health() -> Dict[str, Any]:
    rows = []
    for did in DECISION_IDS:
        try:
            rows.append(PROBES[did]())
        except Exception as exc:  # noqa: BLE001
            rows.append(
                _ok(
                    did,
                    verdict="repair",
                    aligned=False,
                    evidence=f"probe_error={exc}",
                    action="fix probe or mark parked",
                )
            )
    repair = [r for r in rows if r["verdict"] == "repair" or not r["aligned"]]
    return {
        "ok": not repair,
        "version": __version__,
        "home": str(aegis_home()),
        "count": len(rows),
        "repair": [r["id"] for r in repair],
        "decisions": rows,
    }


def _hermes_cmd(prompt: str, usage_path: Path, model: str, provider: str) -> Dict[str, Any]:
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "hermes",
        "-z",
        prompt,
        "--usage-file",
        str(usage_path),
        "--provider",
        provider,
        "-m",
        model,
        "--safe-mode",
        "--ignore-rules",
        "--cli",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(Path.cwd()),
        env=os.environ.copy(),
    )
    usage: Dict[str, Any] = {}
    if usage_path.is_file():
        try:
            usage = json.loads(usage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            usage = {}
    return {
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-800:],
        "stderr": (proc.stderr or "")[-400:],
        "usage": usage,
    }


def measure_naive_vs_pack(
    path: str,
    *,
    model: str = "xiaomi/mimo-v2.5-pro",
    provider: str = "nous",
) -> Dict[str, Any]:
    """One authorized Hermes pair: full file vs packed bento. savings_percent stays null."""
    from aegis.yield_proof import prove

    src = Path(path).expanduser().resolve()
    if not src.is_file():
        return {"ok": False, "error": f"not a file: {src}", "savings_percent": None}
    naive_text = src.read_text(encoding="utf-8", errors="replace")
    proof = prove([str(src)], task="decision-health-pack")
    packed = str(proof.get("pack_id") or "")
    from aegis.pack_cache import load_pack

    payload = load_pack(packed) or {}
    packed_text = json.dumps(payload, ensure_ascii=False)
    instruction = "Reply with one sentence: what does this code do? No tools."
    naive_prompt = instruction + "\n\n" + naive_text
    packed_prompt = instruction + "\n\n" + packed_text
    dest = aegis_home() / "reports"
    dest.mkdir(parents=True, exist_ok=True)
    naive_run = _hermes_cmd(naive_prompt, dest / "usage_naive.json", model, provider)
    packed_run = _hermes_cmd(packed_prompt, dest / "usage_packed.json", model, provider)

    def _usage_counts(blob: Dict[str, Any]) -> Dict[str, Any]:
        usage = blob.get("usage") or {}
        inner = usage.get("usage") if isinstance(usage.get("usage"), dict) else usage
        def _i(key: str):
            val = inner.get(key)
            try:
                return int(val) if val is not None else None
            except (TypeError, ValueError):
                return None
        return {
            "input_tokens": _i("input_tokens"),
            "output_tokens": _i("output_tokens"),
            "total_tokens": _i("total_tokens"),
            "estimated_cost_usd": inner.get("estimated_cost_usd"),
            "cost_status": inner.get("cost_status"),
        }

    naive_u = _usage_counts(naive_run)
    packed_u = _usage_counts(packed_run)
    observed_saved = None
    if naive_u["total_tokens"] is not None and packed_u["total_tokens"] is not None:
        observed_saved = naive_u["total_tokens"] - packed_u["total_tokens"]
    cost_saved = None
    try:
        if naive_u["estimated_cost_usd"] is not None and packed_u["estimated_cost_usd"] is not None:
            cost_saved = float(naive_u["estimated_cost_usd"]) - float(packed_u["estimated_cost_usd"])
    except (TypeError, ValueError):
        cost_saved = None
    return {
        "ok": naive_run["returncode"] == 0 and packed_run["returncode"] == 0,
        "provider": provider,
        "model": model,
        "path": str(src),
        "savings_percent": None,
        "admitted_pair": False,
        "counterfactual": {
            "accounting": "chars4",
            "naive_tokens": proof.get("naive_tokens"),
            "packed_tokens": proof.get("packed_tokens"),
            "saved_tokens": proof.get("tokens_saved_counterfactual"),
        },
        "observed": {
            "naive": naive_u,
            "packed": packed_u,
            "saved_tokens": observed_saved,
            "saved_usd_estimated": cost_saved,
            "naive_returncode": naive_run["returncode"],
            "packed_returncode": packed_run["returncode"],
        },
        "note": "observed usage is provider-reported. savings_percent remains null (D-015).",
    }


def fetch_spec(url: str = "http://127.0.0.1:8787/v1/aegis/spec") -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
