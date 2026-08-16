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


def test_continuity_start_records_validated_source_manifest(aegis_tmp, tmp_path, capsys):
    manifest = tmp_path / "source-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "task_id": "M01",
                "owner": "creator",
                "authority": "local reversible implementation",
                "inputs": [
                    {"path": __file__, "kind": "test", "status": "direct"},
                ],
                "excluded": ["provider telemetry"],
                "rollback": "revert the local patch",
            }
        ),
        encoding="utf-8",
    )

    assert main([
        "continuity", "start", "--task", "manifest test", "--mode", "implement",
        "--source-manifest", str(manifest), "--json", __file__,
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    source = result["source_manifest"]
    assert source["kind"] == "source_manifest"
    assert source["path"] == str(manifest.resolve())
    assert source["task_id"] == "M01"
    assert len(source["sha256"]) == 64
    assert source in result["capsule"]["artifacts"]
    pack_arts = [row for row in result["capsule"]["artifacts"] if row.get("kind") == "pack"]
    assert pack_arts
    assert pack_arts[0].get("id")
    assert result["context"].get("pack_id") == pack_arts[0]["id"]


def test_continuity_start_refuses_empty_pack(aegis_tmp, tmp_path, capsys):
    missing = tmp_path / "nope" / "absent.py"
    assert main([
        "continuity", "start", "--task", "empty pack refuse",
        "--mode", "explore", str(missing),
    ]) == 2
    assert "empty pack" in capsys.readouterr().err


def test_continuity_start_rejects_path_not_approved_by_manifest(aegis_tmp, tmp_path, capsys):
    manifest = tmp_path / "source-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "task_id": "M01",
                "owner": "creator",
                "authority": "local reversible implementation",
                "inputs": [
                    {"path": str(manifest), "kind": "record", "status": "direct"},
                ],
                "rollback": "revert the local patch",
            }
        ),
        encoding="utf-8",
    )

    assert main([
        "continuity", "start", "--task", "manifest test", "--mode", "implement",
        "--source-manifest", str(manifest), __file__,
    ]) == 2
    assert "does not approve" in capsys.readouterr().err


def test_continuity_start_rejects_missing_manifest_input(aegis_tmp, tmp_path, capsys):
    manifest = tmp_path / "source-manifest.json"
    missing = tmp_path / "missing.py"
    manifest.write_text(
        json.dumps(
            {
                "task_id": "M03",
                "owner": "creator",
                "authority": "local reversible implementation",
                "inputs": [
                    {"path": str(missing), "kind": "code", "status": "direct"},
                ],
                "rollback": "revert the local patch",
            }
        ),
        encoding="utf-8",
    )

    assert main([
        "continuity", "start", "--task", "manifest test", "--mode", "implement",
        "--source-manifest", str(manifest), __file__,
    ]) == 2
    assert "existing files" in capsys.readouterr().err


def test_continuity_start_rejects_duplicate_manifest_inputs(aegis_tmp, tmp_path, capsys):
    manifest = tmp_path / "source-manifest.json"
    source = str(Path(__file__).resolve())
    manifest.write_text(
        json.dumps(
            {
                "task_id": "M04",
                "owner": "creator",
                "authority": "local reversible implementation",
                "inputs": [
                    {"path": source, "kind": "test", "status": "direct"},
                    {"path": source, "kind": "test", "status": "direct"},
                ],
                "rollback": "revert the local patch",
            }
        ),
        encoding="utf-8",
    )

    assert main([
        "continuity", "start", "--task", "manifest test", "--mode", "implement",
        "--source-manifest", str(manifest), __file__,
    ]) == 2
    assert "duplicate input paths" in capsys.readouterr().err


def test_continuity_start_rejects_incomplete_source_manifest(aegis_tmp, tmp_path, capsys):
    manifest = tmp_path / "source-manifest.json"
    manifest.write_text("{}", encoding="utf-8")

    assert main([
        "continuity", "start", "--task", "manifest test", "--mode", "implement",
        "--source-manifest", str(manifest), __file__,
    ]) == 2
    assert "invalid source manifest" in capsys.readouterr().err


def test_embedding_pack_matches_schema(aegis_tmp):
    from aegis.embedding_schema import schema_path, validate_embedding_pack

    assert schema_path().is_file()
    bridge = generate_bridge(trigger="schema_test")
    pack = bridge["embedding_pack"]
    ok, errors = validate_embedding_pack(pack)
    assert ok, errors
