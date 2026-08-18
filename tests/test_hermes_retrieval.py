"""Read-only search + context over the living AGIS MUL corpus."""

from pathlib import Path

import pytest

from aegis.hermes_notes import build_graph, search_notes, set_active_graph
from aegis.hermes_skills import invoke
from aegis.paths import hermes_index_dir

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
NEW = (
    "MUL Surface Map.md",
    "MUL Index Provenance.md",
    "MUL Standing Binds.md",
)
FACTORY = (
    "Aegis Sovereign AI Factory.md",
    "Aegis Architecture Map.md",
    "AegisGuard Control Plane.md",
    "Aegis Tokenomics and Capacity.md",
    "Aegis Metacognition and Escalation.md",
    "Aegis Corporate Hierarchy.md",
    "Aegis Product Factory.md",
    "Aegis River Basin Governance Model.md",
    "Aegis Evidence and Provenance Ledger.md",
    "Aegis Threat Model.md",
    "Aegis Implementation Roadmap.md",
)
CORPUS_COUNT = 20
UNRESOLVED = "Hermes Embedding Index (test-unresolved)"


@pytest.fixture(scope="module")
def mul_graph():
    if not MUL_ROOT.is_dir():
        pytest.skip(f"Memory Utility Labs missing: {MUL_ROOT}")
    index = build_graph(str(MUL_ROOT))
    yield index
    set_active_graph(None)


def test_living_corpus_named_set(mul_graph):
    assert len(mul_graph.notes_by_id) == CORPUS_COUNT
    for name in REQUIRED + NEW + FACTORY:
        assert name in mul_graph.notes_by_id
    assert any(link.target_title == UNRESOLVED for link in mul_graph.unresolved_links)
    factory = mul_graph.notes_by_id["Aegis Sovereign AI Factory.md"]
    assert factory.frontmatter.get("canonical") is False
    assert factory.frontmatter.get("type") == "architecture"


def test_exact_title_ranks_first(mul_graph):
    out = invoke("hermes_notes_search", {"query": "MUL Surface Map", "project": "aegis", "limit": 10})
    assert out["ok"] is True
    assert out["hits"][0]["id"] == "MUL Surface Map.md"
    assert out["hits"][0]["reason"] == "exact_title"
    assert out["hits"][0]["score"] >= 1000
    assert out["corpus"]["algorithm"] == "lexical/index/1.0"
    assert out["corpus"]["root"]
    assert out["corpus"]["corpus_note_count"] == CORPUS_COUNT


def test_body_token_and_case_insensitive(mul_graph):
    body = invoke("hermes_notes_search", {"query": "DEC-OBS-007", "limit": 10})
    assert body["ok"] is True
    assert any(hit["id"] == "MUL Surface Map.md" for hit in body["hits"])
    folded = invoke("hermes_notes_search", {"query": "mul surface map", "limit": 5})
    assert folded["hits"][0]["id"] == "MUL Surface Map.md"


def test_project_filter_and_determinism(mul_graph):
    first = invoke("hermes_notes_search", {"query": "Hermes", "project": "aegis", "limit": 8})
    second = invoke("hermes_notes_search", {"query": "Hermes", "project": "aegis", "limit": 8})
    assert [h["id"] for h in first["hits"]] == [h["id"] for h in second["hits"]]
    assert all(h["project"] == "aegis" for h in first["hits"])
    other = search_notes("Hermes", project="no-such", index=mul_graph)
    assert other["ok"] is True
    assert other["hits"] == []


def test_limit_empty_query_and_unresolved(mul_graph):
    limited = invoke("hermes_notes_search", {"query": "Hermes", "limit": 2})
    assert limited["hit_count"] == 2
    assert limited["truncated"] is True
    empty = invoke("hermes_notes_search", {"query": "   "})
    assert empty["error"]["code"] == "INVALID_ARGUMENT"
    hidden = invoke("hermes_notes_search", {"query": "Embedding", "include_unresolved": False})
    assert all(hit.get("id") for hit in hidden["hits"])
    shown = invoke(
        "hermes_notes_search",
        {"query": "Embedding Index", "include_unresolved": True, "limit": 25},
    )
    assert any(hit["title"] == UNRESOLVED and hit["id"] is None for hit in shown["hits"])


def test_resolve_context_one_hop_and_unknown(mul_graph):
    ctx = invoke(
        "hermes_resolve_context",
        {
            "note_id": "Memory Utility Labs.md",
            "project": "aegis",
            "depth": 1,
            "max_notes": 24,
            "max_total_chars": 120000,
        },
    )
    assert ctx["ok"] is True
    ids = [n["id"] for n in ctx["context"]["notes"]]
    assert "Memory Utility Labs.md" in ids
    assert "Hermes Note Graph.md" in ids
    assert "MUL Surface Map.md" in ids
    assert "Aegis Architecture Map.md" in ids
    assert ctx["unresolved_count"] >= 1
    assert UNRESOLVED in ctx["context"]["unresolved_links"]
    assert ctx["context"]["corpus_note_count"] == CORPUS_COUNT
    missing = invoke("hermes_resolve_context", {"note_id": "no-such-note.md"})
    assert missing["error"]["code"] == "NOTE_NOT_FOUND"


def test_resolve_bounds_truncation_and_edges(mul_graph):
    tight = invoke(
        "hermes_resolve_context",
        {
            "title": "Memory Utility Labs",
            "depth": 1,
            "max_notes": 1,
            "max_body_chars": 40,
            "max_total_chars": 200,
        },
    )
    assert tight["truncated"] is True
    assert tight["target_truncated"] is True
    neighbors = invoke(
        "hermes_graph_neighbors",
        {"note_id": "Hermes Note Graph.md", "direction": "inbound", "hops": 1, "limit": 10},
    )
    assert any(row["id"] == "Memory Utility Labs.md" for row in neighbors["neighbors"])
    outbound = invoke(
        "hermes_graph_neighbors",
        {"note_id": "Memory Utility Labs.md", "direction": "outbound", "hops": 1, "limit": 20},
    )
    assert any(row["id"] == "Hermes Note Graph.md" for row in outbound["neighbors"])


def test_path_boundary_and_no_write(mul_graph):
    denied = invoke(
        "hermes_notes_search",
        {"query": "Hermes", "root": "/Users/a100/Documents/Memory Utility Labs"},
    )
    assert denied["error"]["code"] == "PATH_NOT_ALLOWED"
    traversal = invoke("hermes_resolve_context", {"note_id": "../secret.md"})
    assert traversal["error"]["code"] == "PATH_NOT_ALLOWED"
    index_dir = hermes_index_dir()
    before = {p.name: p.stat().st_mtime for p in index_dir.glob("*.json")} if index_dir.is_dir() else {}
    invoke("hermes_notes_search", {"query": "Hermes Note Graph", "limit": 5})
    invoke("hermes_resolve_context", {"note_id": "Hermes Note Graph.md", "depth": 1})
    after = {p.name: p.stat().st_mtime for p in index_dir.glob("*.json")} if index_dir.is_dir() else {}
    assert after == before
