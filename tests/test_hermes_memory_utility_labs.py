"""Persistent integration: Memory Utility Labs vault notes (not tmp fixtures)."""

from pathlib import Path

import pytest

from aegis.hermes_notes import build_graph, graph_signature, resolve_context
from aegis.hermes_skills import invoke

MUL_ROOT = Path(
    "/Users/a100/Library/Mobile Documents/iCloud~md~obsidian/Documents/AGIS"
    "/AEGIS/05-Memory-Utility-Labs"
)
REQUIRED = (
    "Memory Utility Labs.md",
    "Hermes Note Ingestion.md",
    "Hermes Note Graph.md",
    "Hermes Project Context.md",
    "Hermes Skill Surface.md",
    "Hermes Graph Tests.md",
)
UNRESOLVED = "Hermes Embedding Index (test-unresolved)"


@pytest.fixture(scope="module")
def mul_index():
    if not MUL_ROOT.is_dir():
        pytest.skip(f"Memory Utility Labs missing: {MUL_ROOT}")
    return build_graph(str(MUL_ROOT))


def test_persistent_notes_exist_on_disk():
    assert MUL_ROOT.is_dir()
    for name in REQUIRED:
        assert (MUL_ROOT / name).is_file(), name


def test_persistent_graph_discovers_frontmatter_and_ids(mul_index):
    ids = set(mul_index.notes_by_id)
    for name in REQUIRED:
        assert name in ids
    for name in REQUIRED:
        rec = mul_index.notes_by_id[name]
        assert rec.project == "aegis"
        assert "memory-utility-labs" in rec.tags
        assert "hermes" in rec.tags
        assert rec.frontmatter.get("status") == "active"
        assert rec.title == Path(name).stem
        assert rec.id == name
        assert rec.content_hash


def test_persistent_project_filter_and_edges(mul_index):
    aegis = mul_index.notes_by_project.get("aegis") or []
    for name in REQUIRED:
        assert name in aegis
    out = {link.target_title for link in mul_index.outbound_links.get("Memory Utility Labs.md", [])}
    for title in (
        "Hermes Note Ingestion",
        "Hermes Note Graph",
        "Hermes Project Context",
        "Hermes Skill Surface",
        "Hermes Graph Tests",
        UNRESOLVED,
    ):
        assert title in out
    inbound_to_ingestion = {link.source_id for link in mul_index.inbound_links.get("Hermes Note Ingestion.md", [])}
    assert "Memory Utility Labs.md" in inbound_to_ingestion
    unresolved_titles = {link.target_title for link in mul_index.unresolved_links}
    assert UNRESOLVED in unresolved_titles
    assert all(link.target_id is None for link in mul_index.unresolved_links if link.target_title == UNRESOLVED)


def test_persistent_context_provenance_and_identical_rebuild(mul_index, monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    ctx = resolve_context(
        "Memory Utility Labs",
        project="aegis",
        max_notes=8,
        max_hops=1,
        max_body_chars=400,
        max_total_chars=8000,
        index=mul_index,
    )
    assert ctx.provenance
    assert any(row["reason"] == "exact_match" for row in ctx.provenance)
    assert "truncated" in ctx.as_dict()
    tight = resolve_context(
        "Memory Utility Labs",
        project="aegis",
        max_notes=1,
        max_hops=1,
        max_body_chars=40,
        max_total_chars=200,
        index=mul_index,
    )
    assert tight.truncated is True
    again = build_graph(str(MUL_ROOT))
    assert graph_signature(mul_index) == graph_signature(again)
    search = invoke("hermes_notes_search", {"query": "Hermes Note Graph", "project": "aegis", "limit": 10})
    assert search["ok"] is True
    assert any(hit["id"] == "Hermes Note Graph.md" for hit in search["hits"])
    for name in REQUIRED:
        assert (MUL_ROOT / name).is_file()
