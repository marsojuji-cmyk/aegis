"""Hermes note_graph / project_context skills against synthetic trees."""

import json
from pathlib import Path

from aegis.doctor import COMPLEMENTARY_LABS
from aegis.hermes_index import DEFAULT_ROOT
from aegis.hermes_notes import NOTES_VERSION, build_graph, set_active_graph
from aegis.paths import hermes_index_graph_path, hermes_index_notes_path
from aegis.hermes_skills import (
    SKILL_CATALOG,
    SKILL_NAMES,
    SKILL_REGISTRY,
    catalogued_in_wrapper,
    dispatch,
    invoke,
    list_skills,
    skill_dir,
)
from aegis.wrappers.hermes_wrapper import HermesWrapper, classify_tool
from aegis.config import AegisConfig
from aegis.guard import AegisGuard


def _write_tree(root):
    notes = root / "notes"
    notes.mkdir(parents=True)
    (root / "PROJECT.md").write_text(
        "---\nproject: aegis\n---\n# Goals\nKeep the gate fail-closed.\n\n"
        "## Constraints\n- Shadow on\n\n## Decisions\n- Empty root is valid\n",
        encoding="utf-8",
    )
    (notes / "Hermes Brain.md").write_text(
        "---\ntitle: Hermes Brain\ntags: [hermes]\nproject: aegis\n---\n# Hermes Brain\nLinks to [[Aegis Gate]].\n",
        encoding="utf-8",
    )
    (notes / "Aegis Gate.md").write_text(
        "---\ntitle: Aegis Gate\ntags: [aegis]\nproject: aegis\n---\n# Aegis Gate\nSee [[Hermes Brain]].\n",
        encoding="utf-8",
    )
    (notes / "orphan.md").write_text("# Lonely\nNo links.\n", encoding="utf-8")


def test_skill_files_exist():
    names = {row["name"] for row in list_skills()}
    assert names == set(SKILL_NAMES)
    assert names == {row["name"] for row in SKILL_CATALOG}
    for name in SKILL_NAMES:
        path = skill_dir() / name / "SKILL.md"
        assert path.is_file()
        text = path.read_text(encoding="utf-8")
        assert f"name: {name}" in text
    current = [row for row in list_skills() if not row["legacy"]]
    assert {row["name"] for row in current} == set(SKILL_REGISTRY)
    for row in current:
        assert row["args"]
        assert row["use"]
    get_row = next(row for row in current if row["name"] == "hermes_note_get")
    assert get_row["aliases"]["title"] == "note_id"
    neighbors = next(row for row in current if row["name"] == "hermes_graph_neighbors")
    assert neighbors["aliases"]["depth"] == "hops"


def test_dispatch_unknown_skill_fails_closed():
    out = dispatch("launch_missiles")
    assert out["ok"] is False
    assert out["persisted_to_memory"] is False


def test_dispatch_note_graph_and_project_context(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    root = tmp_path / "workspace"
    _write_tree(root)
    monkeypatch.setenv("AEGIS_HERMES_NOTES_ROOT", str(root))

    rebuilt = dispatch("note_graph", action="rebuild", root=str(root))
    assert rebuilt["ok"] is True
    assert rebuilt["note_count"] == 4
    assert rebuilt["persisted_to_memory"] is False

    linked = dispatch("note_graph", action="linked_to", target="Aegis Gate")
    assert "notes/Hermes Brain.md" in linked["hits"]
    assert dispatch("note_graph", action="tagged", tag="aegis")["hits"]
    assert "notes/orphan.md" in dispatch("note_graph", action="orphans")["hits"]

    ctx = dispatch("project_context", name="aegis")
    assert ctx["ok"] is True
    assert ctx["project"]["manifest"] == "PROJECT.md"
    assert "Keep the gate fail-closed." in ctx["project"]["goals"]
    assert ctx["persisted_to_memory"] is False


def test_dispatch_empty_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_HERMES_NOTES_ROOT", raising=False)
    root = tmp_path / "empty"
    root.mkdir()
    out = dispatch("note_graph", action="rebuild", root=str(root))
    assert out["ok"] is False
    assert out["error"]["code"] == "PATH_NOT_ALLOWED"
    missing = dispatch("project_context", name="aegis")
    assert missing["ok"] is False
    assert missing["project"] is None
    assert missing["persisted_to_memory"] is False


def test_dispatch_rebuild_rejects_labs_and_default_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_HERMES_NOTES_ROOT", raising=False)
    labs = dispatch("note_graph", action="rebuild", root=str(COMPLEMENTARY_LABS))
    assert labs["ok"] is False
    assert labs["error"]["code"] == "PATH_NOT_ALLOWED"
    assert labs["error"]["details"]["role"] == "complementary"
    empty = dispatch("note_graph", action="rebuild", root=DEFAULT_ROOT)
    assert empty["ok"] is False
    assert empty["error"]["details"]["role"] == "empty_default_not_product"
    omitted = dispatch("note_graph", action="rebuild")
    assert omitted["ok"] is False
    assert omitted["error"]["code"] == "PATH_NOT_ALLOWED"


def test_invoke_requires_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_HERMES_NOTES_ROOT", raising=False)
    set_active_graph(None)
    out = invoke("hermes_notes_search", {"query": "x"})
    assert out["error"]["code"] == "GRAPH_NOT_BUILT"


def _write_disk_index(root: str, *, version: str = NOTES_VERSION, signature: str = "sig"):
    hermes_index_notes_path().parent.mkdir(parents=True, exist_ok=True)
    note = {
        "id": "Alpha.md",
        "path": str(Path(root) / "Alpha.md"),
        "title": "Alpha",
        "excerpt": "alpha body",
        "tags": ["aegis"],
        "project": "aegis",
        "frontmatter": {},
        "content_hash": "h",
        "modified_at": "",
    }
    notes = {
        "version": version,
        "root": root,
        "signature": signature,
        "note_count": 1,
        "notes": [note],
    }
    graph = {
        "version": version,
        "root": root,
        "signature": signature,
        "nodes": [{"id": "Alpha.md", "title": "Alpha", "tags": ["aegis"], "project": "aegis"}],
        "edges": [],
        "orphans": ["Alpha.md"],
        "notes_by_title": {"Alpha": ["Alpha.md"]},
        "notes_by_project": {"aegis": ["Alpha.md"]},
        "notes_by_tag": {"aegis": ["Alpha.md"]},
        "unresolved": [],
    }
    hermes_index_notes_path().write_text(json.dumps(notes), encoding="utf-8")
    hermes_index_graph_path().write_text(json.dumps(graph), encoding="utf-8")


def test_invoke_loads_verified_pinned_disk_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    pin = tmp_path / "canonical-fixture"
    pin.mkdir()
    (pin / "Alpha.md").write_text("# Alpha\nalpha body unique-token\n", encoding="utf-8")
    monkeypatch.setenv("AEGIS_HERMES_NOTES_ROOT", str(pin))
    _write_disk_index(str(pin))
    set_active_graph(None)
    out = invoke("hermes_notes_search", {"query": "unique-token"})
    assert out["ok"] is True
    assert out["hits"][0]["id"] == "Alpha.md"
    assert out["corpus"]["root"]


def test_invoke_rejects_wrong_root_and_malformed_disk_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_HERMES_NOTES_ROOT", raising=False)
    set_active_graph(None)
    _write_disk_index(str(COMPLEMENTARY_LABS))
    labs = invoke("hermes_notes_search", {"query": "Alpha"})
    assert labs["error"]["code"] == "PATH_NOT_ALLOWED"
    set_active_graph(None)
    _write_disk_index(DEFAULT_ROOT)
    empty = invoke("hermes_notes_search", {"query": "Alpha"})
    assert empty["error"]["code"] == "PATH_NOT_ALLOWED"
    set_active_graph(None)
    hermes_index_notes_path().parent.mkdir(parents=True, exist_ok=True)
    hermes_index_notes_path().write_text("{", encoding="utf-8")
    hermes_index_graph_path().write_text("{}", encoding="utf-8")
    bad = invoke("hermes_notes_search", {"query": "Alpha"})
    assert bad["error"]["code"] == "INDEX_INVALID"
    set_active_graph(None)
    _write_disk_index(str(tmp_path / "arbitrary"), version="0.0")
    pin = tmp_path / "canonical-fixture"
    pin.mkdir()
    monkeypatch.setenv("AEGIS_HERMES_NOTES_ROOT", str(pin))
    _write_disk_index(str(pin), version="9.9")
    ver = invoke("hermes_notes_search", {"query": "Alpha"})
    assert ver["error"]["code"] == "INDEX_INVALID"
    set_active_graph(None)
    notes = {
        "version": NOTES_VERSION,
        "root": str(pin),
        "signature": "a",
        "notes": [{"id": "Alpha.md", "title": "Alpha", "path": str(pin / "Alpha.md")}],
    }
    graph = {
        "version": NOTES_VERSION,
        "root": str(pin),
        "signature": "b",
        "nodes": [],
        "edges": [],
        "orphans": [],
    }
    hermes_index_notes_path().write_text(json.dumps(notes), encoding="utf-8")
    hermes_index_graph_path().write_text(json.dumps(graph), encoding="utf-8")
    stale = invoke("hermes_notes_search", {"query": "Alpha"})
    assert stale["error"]["code"] == "INDEX_INVALID"
    set_active_graph(None)
    hermes_index_notes_path().write_text(
        json.dumps({"version": NOTES_VERSION, "files": [], "root": str(pin)}),
        encoding="utf-8",
    )
    hermes_index_graph_path().write_text(
        json.dumps({"version": NOTES_VERSION, "root": str(pin), "nodes": [], "edges": []}),
        encoding="utf-8",
    )
    files_shaped = invoke("hermes_notes_search", {"query": "Alpha"})
    assert files_shaped["error"]["code"] == "INDEX_INVALID"


def test_four_skills_search_get_neighbors_context(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    root = tmp_path / "workspace"
    _write_tree(root)
    build_graph(str(root))

    search = invoke("hermes_notes_search", {"query": "Aegis Gate", "project": "aegis", "limit": 10})
    assert search["ok"] is True
    assert any(hit["id"] == "notes/Aegis Gate.md" for hit in search["hits"])

    got = invoke("hermes_note_get", {"note_id": "notes/Aegis Gate.md", "include_body": True})
    assert got["ok"] is True
    assert "See [[Hermes Brain]]" in got["note"]["body"]

    missing = invoke("hermes_note_get", {"note_id": "notes/nope.md"})
    assert missing["error"]["code"] == "NOTE_NOT_FOUND"

    traversal = invoke("hermes_note_get", {"note_id": "../secret.md"})
    assert traversal["error"]["code"] == "PATH_NOT_ALLOWED"

    neighbors = invoke(
        "hermes_graph_neighbors",
        {"note_id": "notes/Aegis Gate.md", "direction": "both", "hops": 1, "limit": 10},
    )
    assert neighbors["ok"] is True
    assert any(row["id"] == "notes/Hermes Brain.md" for row in neighbors["neighbors"])

    ctx = invoke(
        "hermes_project_context",
        {"project": "aegis", "query": "gate", "max_notes": 8, "max_total_chars": 4000},
    )
    assert ctx["ok"] is True
    assert ctx["context"]["provenance"]
    assert "# Project: aegis" in ctx["packet"]
    assert ctx["persisted_to_memory"] is False

    missing_proj = invoke("hermes_project_context", {"project": "no-such"})
    assert missing_proj["error"]["code"] == "PROJECT_NOT_FOUND"

    empty = invoke("hermes_notes_search", {"query": "zzzz-no-hit", "limit": 5})
    assert empty["ok"] is True
    assert empty["hits"] == []

    by_title = invoke("hermes_note_get", {"title": "Aegis Gate", "include_body": True})
    assert by_title["ok"] is True
    assert by_title["note"]["id"] == "notes/Aegis Gate.md"
    titled_neighbors = invoke(
        "hermes_graph_neighbors",
        {"title": "Aegis Gate", "direction": "both", "depth": 1, "limit": 10},
    )
    assert titled_neighbors["ok"] is True
    assert any(row["id"] == "notes/Hermes Brain.md" for row in titled_neighbors["neighbors"])
    missing_ref = invoke("hermes_note_get", {})
    assert missing_ref["error"]["code"] == "INVALID_ARGUMENT"


def test_empty_graph_search_is_success(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    root = tmp_path / "empty"
    root.mkdir()
    build_graph(str(root))
    out = invoke("hermes_notes_search", {"query": "anything"})
    assert out["ok"] is True
    assert out["hits"] == []


def test_skill_registry_accepted_by_wrapper_catalog():
    assert catalogued_in_wrapper() is True
    for name in SKILL_REGISTRY:
        cap, risk = classify_tool(name)
        assert cap in {"skill.read", "project.read"}
        assert risk == "low"
    wrap = HermesWrapper(
        AegisConfig(guard_shadow_mode=False, guard_allowed_domains="/tmp/aegis-hermes-allowed"),
        AegisGuard(AegisConfig(guard_shadow_mode=False, guard_allowed_domains="/tmp/aegis-hermes-allowed")),
    )
    result = wrap.handle(
        {
            "tool_name": "hermes_notes_search",
            "args": {"query": "gate"},
            "identity": {"agent": "hermes", "session_id": "s"},
            "scope": {"allowed_domains": ["/tmp/aegis-hermes-allowed"]},
        },
        execute_fn=lambda args: {"ok": True},
    )
    assert result["decision"] == "allow"
    assert result["executed"] is True
