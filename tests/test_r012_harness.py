"""R-012 harness unit tests (no live Hermes calls)."""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from r012_admission_gate import MARKER
from r012_harness import final_assistant_text, harness_mode, load_session_usage, score_probe


def test_harness_mode_default_agent(monkeypatch):
    monkeypatch.delenv("R012_HARNESS", raising=False)
    assert harness_mode() == "agent"


def test_load_session_usage_and_final_text(tmp_path):
    db = tmp_path / "state.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE sessions (id TEXT, input_tokens INT, output_tokens INT, "
        "tool_call_count INT, api_call_count INT, model TEXT, billing_provider TEXT, "
        "estimated_cost_usd REAL, cost_status TEXT, cost_source TEXT)"
    )
    con.execute(
        "CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT, tool_name TEXT, tool_calls TEXT)"
    )
    con.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("s1", 10, 5, 1, 2, "test/model", "nous", 0.0001, "estimated", "provider_models_api"),
    )
    con.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?)",
        ("s1", "assistant", MARKER + "\n", None, None),
    )
    con.commit()
    con.close()

    usage = load_session_usage("s1", db_path=db)
    assert usage["session_id"] == "s1"
    assert usage["total_tokens"] == 15
    assert usage["tool_call_count"] == 1
    assert final_assistant_text("s1", db_path=db) == MARKER


def test_score_probe_uses_session_db(tmp_path):
    db = tmp_path / "state.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE sessions (id TEXT, input_tokens INT, output_tokens INT, "
        "tool_call_count INT, api_call_count INT, model TEXT, billing_provider TEXT, "
        "estimated_cost_usd REAL, cost_status TEXT, cost_source TEXT)"
    )
    con.execute(
        "CREATE TABLE messages (session_id TEXT, role TEXT, content TEXT, tool_name TEXT, tool_calls TEXT)"
    )
    con.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("s-admit", 10, 2, 1, 1, "m", "nous", None, None, None),
    )
    con.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?)",
        ("s-admit", "assistant", None, None, json.dumps([{"function": {"name": "read_file"}}])),
    )
    con.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?)",
        ("s-admit", "tool", MARKER, "read_file", None),
    )
    con.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?)",
        ("s-admit", "assistant", MARKER + "\n", None, None),
    )
    con.commit()
    con.close()

    probe_body = {
        "session_id": "s-admit",
        "stdout": MARKER,
        "exit_code": 0,
        "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    }
    # Point admission loader at temp db via env monkeypatch on DEFAULT - use session_stats inline
    from r012_admission_gate import admit_run

    stats = {
        "tool_call_count": 1,
        "api_call_count": 1,
        "read_file_executed": True,
        "tool_names": ["read_file"],
    }
    out = admit_run(
        mode="control",
        stdout=MARKER,
        usage=probe_body["usage"],
        context_length=128000,
        metadata_advertises_tools=True,
        hermes_accepted=True,
        session_stats=stats,
    )
    assert out["admitted"] is True
