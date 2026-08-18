"""Note graph and project context from gated Markdown reads."""

from aegis.hermes_notes import (
    build_graph,
    build_notes,
    graph_signature,
    notes_linked_to,
    notes_tagged,
    orphan_notes,
    parse_frontmatter,
    parse_manifest_sections,
    parse_note,
    parse_wikilink_spans,
    project_context,
    resolve_context,
    resolve_note_ref,
    set_active_graph,
)
from aegis.paths import hermes_index_graph_path, hermes_index_notes_path


def test_parse_note_frontmatter_and_wikilinks():
    text = """---
title: Aegis Gate
tags: [aegis, hermes]
project: aegis
date: 2026-08-15
---
# Aegis Gate

See [[Hermes Brain]] and [[R-012]].
"""
    parsed = parse_note(text, relpath="notes/aegis.md")
    assert parsed["title"] == "Aegis Gate"
    assert parsed["tags"] == ["aegis", "hermes"]
    assert parsed["project"] == "aegis"
    assert parsed["links"] == ["Hermes Brain", "R-012"]


def test_parse_manifest_sections():
    text = """---
project: aegis
---
# Goals
Keep the gate fail-closed.

## Constraints
- Shadow on

## Decisions
- Empty root is valid
"""
    sections = parse_manifest_sections(text)
    assert sections["goals"] == ["Keep the gate fail-closed."]
    assert sections["constraints"] == ["Shadow on"]
    assert sections["decisions"] == ["Empty root is valid"]


def test_build_notes_graph_and_project_context(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    root = tmp_path / "workspace"
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

    monkeypatch.setenv("AEGIS_HERMES_NOTES_ROOT", str(root))
    out = build_notes(str(root))
    assert out["write_executed"] is True
    assert out["notes"]["note_count"] == 4
    assert out["notes"]["reads_allowed"] == 4
    assert hermes_index_notes_path().is_file()
    assert hermes_index_graph_path().is_file()

    linked = notes_linked_to("Aegis Gate")
    assert "notes/Hermes Brain.md" in linked
    assert "notes/Aegis Gate.md" in notes_tagged("aegis")
    assert "notes/orphan.md" in orphan_notes()
    ctx = project_context("aegis")
    assert ctx is not None
    assert "notes/Aegis Gate.md" in ctx["notes"]
    assert ctx["manifest"] == "PROJECT.md"
    assert "Keep the gate fail-closed." in ctx["goals"]
    assert "Shadow on" in ctx["constraints"]
    assert "Empty root is valid" in ctx["decisions"]


def test_empty_root_is_minimal(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_HERMES_NOTES_ROOT", raising=False)
    root = tmp_path / "empty"
    root.mkdir()
    out = build_notes(str(root))
    assert out["write_executed"] is False
    assert out["error"]["code"] == "PATH_NOT_ALLOWED"
    assert project_context("missing") is None


def test_frontmatter_yaml_list_tags():
    meta = parse_frontmatter(
        "---\ntitle: X\ntags:\n  - memory-utility-labs\n  - hermes\nstatus: active\n---\n"
    )
    assert meta["tags"] == ["memory-utility-labs", "hermes"]
    assert meta["status"] == "active"


def test_frontmatter_sources_related_and_canonical():
    meta = parse_frontmatter(
        "---\ntitle: X\nsources:\n  - docs/BASIN.md\nrelated:\n  - Aegis Architecture Map\ncanonical: true\nrisk: medium\n---\n"
    )
    assert meta["sources"] == ["docs/BASIN.md"]
    assert meta["related"] == ["Aegis Architecture Map"]
    assert meta["canonical"] is True
    assert meta["risk"] == "medium"


def test_frontmatter_preserves_unknown_keys_and_missing_is_ok():
    meta = parse_frontmatter("---\ntitle: X\nowner: hermes\n---\nbody\n")
    assert meta["title"] == "X"
    assert meta["owner"] == "hermes"
    assert parse_frontmatter("# No front matter\n") == {}


def test_title_fallback_filename_and_h1():
    assert parse_note("# Heading Only\n", relpath="notes/ignored.md")["title"] == "Heading Only"
    assert parse_note("no heading\n", relpath="notes/file-stem.md")["title"] == "file-stem"


def test_wikilink_spans_keep_position():
    spans = parse_wikilink_spans("See [[Alpha]] then [[Beta]].")
    assert [name for name, _ in spans] == ["Alpha", "Beta"]
    assert spans[0][1] < spans[1][1]


def _dup_tree(root):
    notes = root / "notes"
    notes.mkdir(parents=True)
    (notes / "one.md").write_text("---\ntitle: Twin\nproject: aegis\n---\n# Twin\n[[Missing]]\n", encoding="utf-8")
    (notes / "two.md").write_text("---\ntitle: Twin\nproject: aegis\n---\n# Twin\n", encoding="utf-8")
    (notes / "hub.md").write_text(
        "---\ntitle: Hub\ntags: [core]\nproject: aegis\n---\n# Hub\nSee [[Twin]].\n" + ("x" * 200),
        encoding="utf-8",
    )


def test_graph_duplicate_unresolved_stable_and_identical(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    root = tmp_path / "ws"
    _dup_tree(root)
    first = build_graph(str(root))
    second = build_graph(str(root))
    assert graph_signature(first) == graph_signature(second)
    assert any(w.startswith("AMBIGUOUS_TITLE:Twin") for w in first.warnings)
    assert first.unresolved_links
    assert first.unresolved_links[0].target_id is None
    assert list(first.notes_by_id) == sorted(first.notes_by_id)
    hub = "notes/hub.md"
    assert first.outbound_links[hub]
    nid, err = resolve_note_ref("Twin", first)
    assert nid is None
    assert err["error"]["code"] == "AMBIGUOUS_TITLE"


def test_resolve_context_hops_truncation_provenance(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    root = tmp_path / "ws"
    notes = root / "notes"
    notes.mkdir(parents=True)
    (notes / "A.md").write_text("---\ntitle: A\nproject: aegis\n---\n# A\n[[B]]\n" + ("n" * 80), encoding="utf-8")
    (notes / "B.md").write_text("---\ntitle: B\nproject: aegis\n---\n# B\n[[C]]\n", encoding="utf-8")
    (notes / "C.md").write_text("---\ntitle: C\nproject: other\n---\n# C\n", encoding="utf-8")
    index = build_graph(str(root))
    one = resolve_context("A", max_notes=8, max_hops=1, index=index)
    ids = [n["id"] for n in one.notes]
    assert "notes/A.md" in ids
    assert "notes/B.md" in ids
    assert "notes/C.md" not in ids
    assert any(p["reason"] == "exact_match" for p in one.provenance)
    assert any(p["reason"] == "outbound_link" for p in one.provenance)
    bounded = resolve_context("A", project="aegis", max_notes=1, max_hops=1, max_body_chars=10, max_total_chars=80, index=index)
    assert bounded.truncated is True
    assert "CONTEXT_LIMIT_EXCEEDED" in bounded.warnings
    assert "bounded result; not complete" in bounded.warnings
    filtered = resolve_context("", project="aegis", max_hops=0, index=index)
    assert all(n["project"] == "aegis" for n in filtered.notes)
    set_active_graph(None)
