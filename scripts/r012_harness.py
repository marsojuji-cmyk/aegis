"""R-012 live probe harness — agent loop first, oneshot legacy.

Hermes on this host executes native tools in multi-turn agent sessions (desktop/cron),
not in ``hermes -z`` oneshot probes. This module runs ``hermes chat -q --max-turns``
by default and scores admission from session DB evidence plus final assistant text.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path("/tmp/aegis-r012-measure")
MARKER = "R012-MARKER-7c3e91"
HERMES = Path.home() / ".local" / "bin" / "hermes"
DEFAULT_DB = Path.home() / ".hermes" / "state.db"

PROMPT = (
    f"Read the file {ROOT}/marker.txt using the read_file tool. "
    "Your final reply must be ONLY the exact file contents and nothing else."
)


def ensure_fixture() -> Path:
    ROOT.mkdir(parents=True, exist_ok=True)
    marker_path = ROOT / "marker.txt"
    marker_path.write_text(MARKER + "\n", encoding="utf-8")
    return marker_path


def harness_mode() -> str:
    raw = os.environ.get("R012_HARNESS", "agent").strip().lower()
    return raw if raw in {"agent", "oneshot"} else "agent"


def _run(cmd: List[str], *, env: Optional[dict] = None, timeout: int = 240) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env)


def _hermes_cmd(*, env: Optional[dict] = None, usage_path: Optional[Path] = None) -> Dict[str, Any]:
    model = os.environ.get("R012_MODEL", "").strip()
    provider = os.environ.get("R012_PROVIDER", "").strip()
    mode = harness_mode()
    max_turns = int(os.environ.get("R012_MAX_TURNS", "8"))
    toolsets = os.environ.get("R012_TOOLSETS", "file").strip() or "file"
    reasoning = os.environ.get("R012_REASONING", "none").strip() or "none"

    if mode == "oneshot":
        ufile = usage_path or ROOT / "probe-usage.json"
        cmd = [
            str(HERMES),
            "-z",
            PROMPT,
            "--usage-file",
            str(ufile),
            "-t",
            toolsets,
            "--ignore-rules",
            "--reasoning",
            reasoning,
        ]
    else:
        cmd = [
            str(HERMES),
            "chat",
            "-q",
            PROMPT,
            "-t",
            toolsets,
            "--ignore-rules",
            "--reasoning",
            reasoning,
            "--max-turns",
            str(max_turns),
        ]
        if os.environ.get("R012_YOLO", "0") == "1":
            cmd.append("--yolo")
    if model:
        cmd.extend(["-m", model])
    if provider:
        cmd.extend(["--provider", provider])
    return {"cmd": cmd, "mode": mode, "max_turns": max_turns if mode == "agent" else None}


def load_session_usage(session_id: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    path = db_path or DEFAULT_DB
    if not session_id or not path.is_file():
        return {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = con.execute(
            """
            SELECT input_tokens, output_tokens, tool_call_count, api_call_count,
                   model, billing_provider, estimated_cost_usd, cost_status, cost_source
            FROM sessions WHERE id=?
            """,
            (session_id,),
        ).fetchone()
    finally:
        con.close()
    if not row:
        return {"session_id": session_id}
    inp, out, tc, ac, model, prov, est, cstat, csrc = row
    total = (inp or 0) + (out or 0)
    body: Dict[str, Any] = {
        "session_id": session_id,
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": total if total else None,
        "api_calls": ac,
        "tool_call_count": tc,
        "model": model,
        "provider": prov,
    }
    if est is not None:
        body["estimated_cost_usd"] = est
    if cstat:
        body["cost_status"] = cstat
    if csrc:
        body["cost_source"] = csrc
    return body


def final_assistant_text(session_id: str, db_path: Optional[Path] = None) -> str:
    path = db_path or DEFAULT_DB
    if not session_id or not path.is_file():
        return ""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute(
            """
            SELECT content FROM messages
            WHERE session_id=? AND role='assistant' AND content IS NOT NULL AND trim(content) != ''
            ORDER BY rowid DESC LIMIT 1
            """,
            (session_id,),
        ).fetchall()
    finally:
        con.close()
    return (rows[0][0] or "").strip() if rows else ""


def run_probe(*, env: Optional[dict] = None, usage_path: Optional[Path] = None) -> Dict[str, Any]:
    """Run one live probe. Does not score admission."""
    ensure_fixture()
    spec = _hermes_cmd(env=env, usage_path=usage_path)
    cmd = spec["cmd"]
    proc = _run(cmd, env=env, timeout=int(os.environ.get("R012_TIMEOUT", "240")))
    cli_stdout = (proc.stdout or "").strip()
    cli_stderr = (proc.stderr or "").strip()[-1000:]

    usage: Dict[str, Any] = {}
    session_id = ""
    if spec["mode"] == "oneshot":
        ufile = usage_path or ROOT / "probe-usage.json"
        if ufile.is_file():
            try:
                usage = json.loads(ufile.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                usage = {"parse_error": ufile.read_text(encoding="utf-8")[:500]}
        session_id = str(usage.get("session_id") or "")

    if not session_id:
        # Agent loop: Hermes prints "Session: <id>" on stderr/stdout footer.
        for blob in (cli_stdout, cli_stderr, proc.stdout or "", proc.stderr or ""):
            for line in blob.splitlines():
                line = line.strip()
                if line.startswith("Session:"):
                    session_id = line.split(":", 1)[1].strip()
                    break
            if session_id:
                break

    if session_id and not usage.get("session_id"):
        usage = load_session_usage(session_id)

    stdout = final_assistant_text(session_id) if session_id else cli_stdout
    if not stdout:
        stdout = cli_stdout

    return {
        "harness": spec["mode"],
        "max_turns": spec["max_turns"],
        "exit_code": proc.returncode,
        "stdout": stdout,
        "cli_stdout": cli_stdout,
        "stderr": cli_stderr,
        "usage": usage,
        "session_id": session_id,
        "cmd": cmd,
    }


def score_probe(probe_body: Dict[str, Any], *, mode: str = "control", guard_records: Optional[List[dict]] = None) -> Dict[str, Any]:
    from r012_admission_gate import admit_run, load_session_stats

    session_id = str(probe_body.get("session_id") or "")
    usage = probe_body.get("usage") if isinstance(probe_body.get("usage"), dict) else {}
    ctx_raw = os.environ.get("R012_CONTEXT_LENGTH", "")
    try:
        context_length = int(ctx_raw) if ctx_raw else None
    except ValueError:
        context_length = None
    advertised = os.environ.get("R012_ADVERTISES_TOOLS", "1") == "1"
    return admit_run(
        mode=mode,
        stdout=str(probe_body.get("stdout") or ""),
        usage=usage,
        context_length=context_length,
        metadata_advertises_tools=advertised,
        hermes_accepted=int(probe_body.get("exit_code", 2)) != 2,
        session_id=session_id,
        guard_records=guard_records or [],
    )
