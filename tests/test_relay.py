"""Tests for observability relay."""

import json

import pytest

from aegis.guard import GUARD_LOG_PATH
from aegis.paths import continuity_events_path, ledger_path
from aegis.relay import append_continuity_event, correlate, export_redacted, tail


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_tail_continuity_events(aegis_tmp):
    append_continuity_event({"kind": "capsule", "fingerprint": "abc123"})
    rows = tail("continuity", limit=5)
    assert len(rows) == 1
    assert rows[0]["kind"] == "capsule"


def test_correlate_by_request_id(aegis_tmp):
    rid = "req_test_001"
    GUARD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GUARD_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"request_id": rid, "rule": "budget", "action": "allow"}) + "\n")
    append_continuity_event({"kind": "hermes_outcome", "request_id": rid, "decision": "allow"})
    out = correlate(rid)
    assert out["count"] >= 2
    assert out["guard"]
    assert out["continuity"]


def test_export_redacted(aegis_tmp, tmp_path):
    append_continuity_event({"kind": "capsule", "content": "x" * 600})
    dest = tmp_path / "export.json"
    count = export_redacted(dest, source="continuity", limit=10)
    assert count == 1
    payload = json.loads(dest.read_text(encoding="utf-8"))
    assert payload[0]["content"].endswith("…")
