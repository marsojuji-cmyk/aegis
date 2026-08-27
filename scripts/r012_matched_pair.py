"""One matched ungated/gated Hermes oneshot pair for R-012 measurement.

Does not change shadow mode, thresholds, Hermes-agent source, or production
allowed domains. Does not publish a savings percentage.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/tmp/aegis-r012-measure")
MARKER = "R012-MARKER-7c3e91"
PROMPT = (
    f"Read the file {ROOT}/marker.txt. "
    "Reply with only the exact file contents and nothing else."
)
HERMES = Path.home() / ".local" / "bin" / "hermes"
AEGIS_HOME = ROOT / "aegis-home"


def _run(cmd: list[str], env: dict | None = None, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=env,
    )


def _oneshot(usage_path: Path, env: dict | None = None) -> dict:
    _here = Path(__file__).resolve().parent
    if str(_here) not in sys.path:
        sys.path.insert(0, str(_here))
    from r012_harness import run_probe

    t0 = time.perf_counter()
    if usage_path:
        os.environ["R012_PROBE_USAGE"] = str(usage_path)
    probe_body = run_probe(env=env, usage_path=usage_path if harness_mode() == "oneshot" else None)
    elapsed = round(time.perf_counter() - t0, 3)
    usage = probe_body.get("usage") if isinstance(probe_body.get("usage"), dict) else {}
    if usage_path and usage:
        usage_path.write_text(json.dumps(usage, indent=2) + "\n", encoding="utf-8")
    return {
        "exit_code": probe_body.get("exit_code"),
        "elapsed_s": elapsed,
        "stdout": probe_body.get("stdout") or "",
        "stderr": probe_body.get("stderr") or "",
        "success": False,
        "usage": usage,
        "harness": probe_body.get("harness"),
        "session_id": probe_body.get("session_id"),
    }


def harness_mode() -> str:
    raw = os.environ.get("R012_HARNESS", "agent").strip().lower()
    return raw if raw in {"agent", "oneshot"} else "agent"


def _guard_delta(before: list[str]) -> list[dict]:
    log = Path.home() / ".aegis" / "guard_log.jsonl"
    if not log.is_file():
        return []
    lines = log.read_text().splitlines()
    new = lines[len(before) :]
    out = []
    for line in new:
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("provider") == "hermes":
            out.append(
                {
                    "action": rec.get("action"),
                    "rule": rec.get("rule"),
                    "would_block": rec.get("would_block"),
                    "reason": rec.get("reason"),
                }
            )
    return out


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "marker.txt").write_text(MARKER + "\n", encoding="utf-8")
    AEGIS_HOME.mkdir(parents=True, exist_ok=True)
    (AEGIS_HOME / "config.toml").write_text(
        "\n".join(
            [
                "guard_shadow_mode = true",
                "guard_signal_shadow_mode = true",
                'guard_allowed_domains = "/tmp/aegis-r012-measure"',
                "guard_max_tool_calls = 20",
                "guard_max_velocity_calls_per_min = 5",
                "",
            ]
        ),
        encoding="utf-8",
    )

    disable = _run([str(HERMES), "plugins", "disable", "aegis-gate"])
    ungated = _oneshot(ROOT / "ungated-usage.json")

    enable = _run(
        [
            str(HERMES),
            "plugins",
            "enable",
            "aegis-gate",
            "--no-allow-tool-override",
        ]
    )
    log = Path.home() / ".aegis" / "guard_log.jsonl"
    before = log.read_text().splitlines() if log.is_file() else []
    env = os.environ.copy()
    env["AEGIS_HOME"] = str(AEGIS_HOME)
    gated = _oneshot(ROOT / "gated-usage.json", env=env)
    gated["hermes_guard_records"] = _guard_delta(before)

    import sys

    _here = Path(__file__).resolve().parent
    _src = _here.parent / "src"
    sys.path.insert(0, str(_here))
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
    from r012_admission_gate import admit_pair, admit_run

    ctx_raw = os.environ.get("R012_CONTEXT_LENGTH", "")
    try:
        context_length = int(ctx_raw) if ctx_raw else None
    except ValueError:
        context_length = None
    advertised = os.environ.get("R012_ADVERTISES_TOOLS", "1") == "1"
    control_adm = admit_run(
        mode="control",
        stdout=ungated.get("stdout") or "",
        usage=ungated.get("usage"),
        context_length=context_length,
        metadata_advertises_tools=advertised,
        hermes_accepted=ungated.get("exit_code") != 2,
        session_id=(ungated.get("usage") or {}).get("session_id") or "",
    )
    treat_adm = admit_run(
        mode="treatment",
        stdout=gated.get("stdout") or "",
        usage=gated.get("usage"),
        context_length=context_length,
        metadata_advertises_tools=advertised,
        hermes_accepted=gated.get("exit_code") != 2,
        session_id=(gated.get("usage") or {}).get("session_id") or "",
        guard_records=gated.get("hermes_guard_records") or [],
    )
    ungated["success"] = control_adm["admitted"]
    gated["success"] = treat_adm["admitted"]
    ungated["admission"] = control_adm
    gated["admission"] = treat_adm
    pair = admit_pair(control_adm, treat_adm)

    from aegis.wrappers.hermes_telemetry import record_pair

    telemetry = record_pair(
        task_id="r012-matched-pair",
        control_usage=ungated.get("usage"),
        treatment_usage=gated.get("usage"),
        pair_valid=bool(pair.get("pair_valid")),
        control_session_id=(ungated.get("usage") or {}).get("session_id") or "",
        treatment_session_id=(gated.get("usage") or {}).get("session_id") or "",
        model=os.environ.get("R012_MODEL") or "",
        provider=os.environ.get("R012_PROVIDER") or "",
        extra={"admission": {"control": control_adm, "treatment": treat_adm}},
    )

    report = {
        "status": "measured",
        "task": PROMPT,
        "marker": MARKER,
        "model_requested": os.environ.get("R012_MODEL")
        or "config-default + --reasoning none",
        "provider_requested": os.environ.get("R012_PROVIDER") or "config-default",
        "harness": harness_mode(),
        "toolsets": os.environ.get("R012_TOOLSETS", "file"),
        "shadow_mode": True,
        "thresholds_changed": False,
        "allowed_domains_production_changed": False,
        "gated_scope": "/tmp/aegis-r012-measure",
        "plugin_disable": {
            "exit_code": disable.returncode,
            "stdout": (disable.stdout or "").strip()[-300:],
        },
        "plugin_enable": {
            "exit_code": enable.returncode,
            "stdout": (enable.stdout or "").strip()[-300:],
        },
        "ungated": ungated,
        "gated": gated,
        "pair": pair,
        "delta": {
            "input_tokens": _sub(ungated, gated, "input_tokens")
            if pair["pair_valid"]
            else None,
            "output_tokens": _sub(ungated, gated, "output_tokens")
            if pair["pair_valid"]
            else None,
            "total_tokens": _sub(ungated, gated, "total_tokens")
            if pair["pair_valid"]
            else None,
            "api_calls": _sub(ungated, gated, "api_calls")
            if pair["pair_valid"]
            else None,
            "elapsed_s": (
                _num(ungated.get("elapsed_s")) - _num(gated.get("elapsed_s"))
                if pair["pair_valid"]
                else None
            ),
            "both_succeeded": pair["pair_valid"],
        },
        "telemetry": telemetry,
        "savings_percent": None,
        "note": (
            "ΔT is raw ungated-minus-gated totals. Not a savings percentage. "
            "Interpret only if both runs succeeded."
        ),
    }
    out = ROOT / "pair-report.json"
    out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if ungated.get("success") or gated.get("success") else 1


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sub(ungated: dict, gated: dict, key: str):
    u = (ungated.get("usage") or {}).get(key)
    g = (gated.get("usage") or {}).get(key)
    if u is None or g is None:
        return None
    try:
        return u - g
    except TypeError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
