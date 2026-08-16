"""R-012 model-admission gate. Offline. Does not call models or change config.

A model is compatible only if Hermes records a native tool call and the
tool executes. Advertised tool_call metadata is not sufficient.

Do not compute token_delta unless admit_pair() returns admitted=True.
savings_percent is always None.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

MARKER = "R012-MARKER-7c3e91"
MIN_CONTEXT = 64_000
FIXTURE_DIR = "/tmp/aegis-r012-measure"
PROMPT_ID = "r012-read-marker-v1"

CHECKLIST = (
    "context_length_ge_64000",
    "metadata_advertises_tools",
    "hermes_accepts_model",
    "tool_call_count_gt_0",
    "read_file_executed",
    "exact_marker_returned",
    "gate_observed_when_gated",
    "comparable_token_metadata",
    "no_hallucinated_content",
    "no_text_imitation_tool_call",
)

# Substring tokens only. This is not a provider parser and must never
# be treated as executing DSML/XML/vendor markup.
_IMITATION = (
    "<tool_call>",
    "</tool_call>",
    "<tool_calls>",
    "<read_file>",
    "<function_call>",
    "<function_calls>",
    "<|tool_call",
    "<|tool_arg",
    "tool_call:start",
    "invoke name=",
    "dsml",
)

_PROSE_CLAIM = (
    "i read the file",
    "i have read the file",
    "the file was read",
    "the file contains",
    "file contents are",
    "read the file and",
)

_NOT_ADMITTED = (
    "No efficiency conclusion; native Hermes tool-call admission not yet proven."
)


def is_text_imitation(stdout: str) -> bool:
    text = (stdout or "").lower()
    return any(token.lower() in text for token in _IMITATION)


def is_prose_claim(stdout: str) -> bool:
    text = (stdout or "").lower()
    return any(token in text for token in _PROSE_CLAIM)


def has_comparable_tokens(usage: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(usage, dict):
        return False
    required = ("input_tokens", "output_tokens", "total_tokens")
    return all(usage.get(key) is not None for key in required)


def load_session_stats(session_id: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    path = db_path or (Path.home() / ".hermes" / "state.db")
    empty = {
        "tool_call_count": None,
        "api_call_count": None,
        "read_file_executed": False,
        "tool_names": [],
    }
    if not session_id or not path.is_file():
        return empty
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = con.execute(
            "select tool_call_count, api_call_count from sessions where id=?",
            (session_id,),
        ).fetchone()
        names = [
            name
            for (name,) in con.execute(
                "select tool_name from messages where session_id=? and tool_name is not null",
                (session_id,),
            )
        ]
        calls = [
            blob
            for (blob,) in con.execute(
                "select tool_calls from messages where session_id=? and tool_calls is not null",
                (session_id,),
            )
        ]
    finally:
        con.close()
    tool_call_count = row[0] if row else None
    read_file = any(n == "read_file" for n in names) or any(
        "read_file" in (blob or "") for blob in calls
    )
    return {
        "tool_call_count": tool_call_count,
        "api_call_count": row[1] if row else None,
        "read_file_executed": bool(read_file),
        "tool_names": names,
    }


def admit_run(
    *,
    mode: str,
    stdout: str,
    usage: Optional[Dict[str, Any]],
    context_length: Optional[int],
    metadata_advertises_tools: Optional[bool],
    hermes_accepted: bool,
    session_stats: Optional[Dict[str, Any]] = None,
    guard_records: Optional[List[Dict[str, Any]]] = None,
    session_id: str = "",
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Score one run. mode is 'control' or 'treatment'."""
    stats = session_stats or load_session_stats(session_id, db_path=db_path)
    tool_count = stats.get("tool_call_count")
    tool_event = isinstance(tool_count, int) and tool_count > 0
    imitation = is_text_imitation(stdout) or (
        not tool_event and is_prose_claim(stdout)
    )
    marker_ok = MARKER in (stdout or "")
    hallucinated = marker_ok is False and bool((stdout or "").strip()) and not imitation
    if MARKER not in (stdout or "") and "R012-" in (stdout or ""):
        hallucinated = True
    gate_records = list(guard_records or [])
    gate_observed = any(
        rec.get("action") in {"allow", "block"} and rec.get("rule")
        for rec in gate_records
    )
    checks = {
        "context_length_ge_64000": isinstance(context_length, int)
        and context_length >= MIN_CONTEXT,
        "metadata_advertises_tools": metadata_advertises_tools is True,
        "hermes_accepts_model": bool(hermes_accepted),
        "tool_call_count_gt_0": tool_event,
        "read_file_executed": bool(stats.get("read_file_executed")),
        "exact_marker_returned": marker_ok and not imitation and tool_event,
        "gate_observed_when_gated": True
        if mode != "treatment"
        else gate_observed,
        "comparable_token_metadata": has_comparable_tokens(usage),
        "no_hallucinated_content": not hallucinated,
        "no_text_imitation_tool_call": not imitation,
    }
    # Advertised tools never admit by themselves.
    admitted = all(
        checks[name]
        for name in CHECKLIST
        if name != "metadata_advertises_tools"
    ) and checks["tool_call_count_gt_0"]
    marker_check = bool(
        marker_ok
        and not imitation
        and tool_event
        and checks["read_file_executed"]
    )
    return {
        "admitted": admitted,
        "mode": mode,
        "marker_check": marker_check,
        "native_tool_call": bool(
            checks["tool_call_count_gt_0"] and checks["read_file_executed"]
        ),
        "tool_event_observed": tool_event,
        "hermes_tool_call_count": tool_count,
        "gate_observed": gate_observed if mode == "treatment" else False,
        "checks": checks,
        "decision": None
        if mode != "treatment"
        else next(
            (
                rec.get("action")
                for rec in gate_records
                if rec.get("action") in {"allow", "block"}
            ),
            None,
        ),
        "decision_summary": None if admitted else _NOT_ADMITTED,
        "token_delta": None,
        "savings_percent": None,
    }


def admit_pair(control: Dict[str, Any], treatment: Dict[str, Any]) -> Dict[str, Any]:
    valid = bool(control.get("admitted") and treatment.get("admitted"))
    return {
        "pair_valid": valid,
        "token_delta": None,
        "savings_percent": None,
        "efficiency_result": "valid_pair" if valid else "invalid_pair",
        "note": None if valid else _NOT_ADMITTED,
        "decision_summary": None if valid else _NOT_ADMITTED,
    }


def classify_compatibility_artifact(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text())
    screened = data.get("screened") or []
    any_native = any(item.get("native_tool_call") for item in screened)
    return {
        "compatible_model": None,
        "screened_count": len(screened),
        "any_native_tool_call": bool(any_native),
        "pair_run": bool(data.get("pair_run")),
        "token_delta": data.get("token_delta"),
        "savings_percent": data.get("savings_percent"),
    }


def score_artifact(path: Path) -> Dict[str, Any]:
    """Score a saved admission/oneshot artifact. Silent import is not admission."""
    data = json.loads(path.read_text())
    nested = data.get("admission") if isinstance(data.get("admission"), dict) else None
    if nested and "admitted" in nested:
        return {
            "admitted": bool(nested.get("admitted")),
            "source": str(path),
            "token_delta": None,
            "savings_percent": None,
            "decision_summary": nested.get("decision_summary") or (
                None if nested.get("admitted") else _NOT_ADMITTED
            ),
            "checks": nested.get("checks"),
        }
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    scored = admit_run(
        mode=str(data.get("mode") or "control"),
        stdout=str(data.get("stdout") or ""),
        usage=usage,
        context_length=data.get("context_length"),
        metadata_advertises_tools=bool(data.get("metadata_advertises_tools")),
        hermes_accepted=bool(data.get("hermes_accepted")),
        session_stats=data.get("session_stats"),
        guard_records=data.get("guard_records") or data.get("hermes_guard_records"),
        session_id=str(data.get("session_id") or usage.get("session_id") or ""),
    )
    scored["source"] = str(path)
    return scored


def main(argv: Optional[List[str]] = None) -> int:
    """CLI. No args is NOT success — that was a false-positive class of error."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        report = {
            "admitted": False,
            "error": "usage: r012_admission_gate.py <admission-artifact.json>",
            "note": "Importing or running with no artifact is not admission.",
            "token_delta": None,
            "savings_percent": None,
            "decision_summary": _NOT_ADMITTED,
        }
        print(json.dumps(report, indent=2))
        return 2
    path = Path(args[0])
    if not path.is_file():
        print(json.dumps({
            "admitted": False,
            "error": f"artifact not found: {path}",
            "token_delta": None,
            "savings_percent": None,
            "decision_summary": _NOT_ADMITTED,
        }, indent=2))
        return 2
    scored = score_artifact(path)
    print(json.dumps(scored, indent=2, default=str))
    return 0 if scored.get("admitted") else 2


if __name__ == "__main__":
    raise SystemExit(main())
