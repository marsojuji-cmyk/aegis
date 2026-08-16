"""Hermes file index: gated reads/writes, ignore rules, query."""

import json

from aegis.hermes_index import build_index, query_index
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
