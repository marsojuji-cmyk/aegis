"""Hermes file index: gated reads/writes, ignore rules, query."""

import json
from pathlib import Path

from aegis.config import AegisConfig
from aegis.hermes_index import _wrapper, build_index, query_index
from aegis.hermes_notes import build_graph, set_active_graph
from aegis.paths import hermes_index_files_path


def test_build_index_gates_reads_and_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "note.md").write_text("# Hello\nsecret token=should-redact-maybe\n", encoding="utf-8")
    (root / ".env").write_text("API_KEY=nope\n", encoding="utf-8")
    (root / "skip.pyc").write_bytes(b"x")
    nested = root / "keep"
    nested.mkdir()
    (nested / "readme.txt").write_text("alpha beta\n", encoding="utf-8")

    payload = build_index(str(root))
    assert payload["write_decision"] == "allow"
    assert payload["write_executed"] is True
    assert payload["reads_allowed"] >= 2
    dest = hermes_index_files_path()
    assert dest.is_file()
    stored = json.loads(dest.read_text(encoding="utf-8"))
    rels = {row["relpath"] for row in stored["files"]}
    assert "note.md" in rels
    assert "keep/readme.txt" in rels
    assert ".env" not in rels
    assert "skip.pyc" not in rels
    note = next(row for row in stored["files"] if row["relpath"] == "note.md")
    assert note["read_decision"] == "allow"
    assert note["preview"]

    hits = query_index(keyword="alpha", dest=dest)
    assert any(row["relpath"] == "keep/readme.txt" for row in hits)


def test_indexer_reads_survive_live_mission_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(
        "aegis.hermes_index.load_config",
        lambda: AegisConfig(
            guard_require_mission_lock=True,
            guard_shadow_mode=False,
            guard_mission="Project Aegis: stay inside allowlist. Local-first. Do not wander.",
        ),
    )
    root = tmp_path / "mul"
    root.mkdir()
    mul = root / "Memory Utility Labs.md"
    graph = root / "Hermes Note Graph.md"
    mul.write_text("# MUL\n[[Hermes Note Graph]]\n" + ("corpus " * 1200), encoding="utf-8")
    graph.write_text("# Graph\n", encoding="utf-8")

    wrap = _wrapper([str(root)])
    assert wrap.config.guard_require_mission_lock is False
    assert wrap.config.guard_max_output_length >= 2_000_000
    assert wrap.config.guard_signal_shadow_mode is True
    gated = wrap.handle(
        {
            "tool_name": "read_file",
            "args": {"filepath": str(mul)},
            "identity": {"agent": "hermes", "session_id": "hermes-index"},
            "scope": {"allowed_domains": [str(root)]},
            "environment": "hermes-index",
        },
        execute_fn=lambda args: Path(args["filepath"]).read_text(encoding="utf-8"),
    )
    assert gated["decision"] == "allow"
    assert gated["executed"] is True
    assert "MUL" in str(gated.get("output") or "")

    index = build_graph(str(root))
    try:
        assert set(index.notes_by_id) == {"Memory Utility Labs.md", "Hermes Note Graph.md"}
        assert index.reads_denied == 0
        assert "corpus " * 50 in index.notes_by_id["Memory Utility Labs.md"].body
    finally:
        set_active_graph(None)
