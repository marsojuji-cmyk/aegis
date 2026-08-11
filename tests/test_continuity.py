"""Continuity Bridge + embedding handoff pack."""

import json
from pathlib import Path

import pytest

from aegis.cli import main
from aegis.continuity import (
    HANDOFF_VERSION,
    build_embedding_pack,
    generate_bridge,
    maybe_auto_bridge,
    _sha256_texts,
)
from aegis.ledger import record


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_generate_bridge_writes_artifacts(aegis_tmp):
    record(kind="pack", task="t", mode="explore", raw_in=1000, processed_in=200)
    bridge = generate_bridge(trigger="test")
    assert bridge["ok"] is True
    assert bridge["handoff_version"] == HANDOFF_VERSION
    paths = bridge["paths"]
    assert Path(paths["markdown"]).is_file()
    assert Path(paths["json"]).is_file()
    assert Path(paths["embedding"]).is_file()
    assert Path(paths["latest_markdown"]).is_file()
    md = Path(paths["markdown"]).read_text(encoding="utf-8")
    assert "Continuity Bridge Report" in md
    assert "Cross-AI Next Steps" in md
    assert "Semantic Embedding Handoff Pack" in md
    assert "Atomic Actions" in md or "atomic" in md.lower()
    emb = json.loads(Path(paths["embedding"]).read_text(encoding="utf-8"))
    assert emb["integrity_hash"]
    assert emb["vectors"]
    texts = [v["canonical_text"] for v in emb["vectors"]]
    assert emb["integrity_hash"] == _sha256_texts(texts)
    # deterministic local embed
    emb2 = build_embedding_pack(bridge["sections"], session_id="x", include_vectors=True)
    assert emb2["vectors"][0]["vector"] == emb["vectors"][0]["vector"]


def test_auto_bridge_only_on_emergency(aegis_tmp):
    assert maybe_auto_bridge(band="ok") is None
    assert maybe_auto_bridge(band="adaptive") is None
    br = maybe_auto_bridge(band="emergency")
    assert br is not None and br.get("ok") is True
    assert br.get("trigger") == "emergency_band"


def test_cli_continuity(aegis_tmp):
    assert main(["intel", "continuity"]) == 0
    assert main(["intel", "continuity", "--latest"]) == 0
    assert main(["intel", "continuity", "--json"]) == 0


def test_embedding_pack_matches_schema(aegis_tmp):
    from aegis.embedding_schema import schema_path, validate_embedding_pack

    assert schema_path().is_file()
    bridge = generate_bridge(trigger="schema_test")
    pack = bridge["embedding_pack"]
    ok, errors = validate_embedding_pack(pack)
    assert ok, errors
