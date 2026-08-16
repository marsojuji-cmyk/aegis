"""Unified search over local gated indexes. No external APIs."""

import json

from aegis.hermes_search import unified_search


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_unified_search_ranks_notes_and_projects(tmp_path):
    files = tmp_path / "files.json"
    notes = tmp_path / "notes.json"
    projects = tmp_path / "projects.json"
    _write(
        files,
        {
            "files": [
                {"relpath": "notes/Aegis Gate.md", "type": "file", "preview": "gate", "path": "x", "ext": ".md"},
                {"relpath": "keep", "type": "dir", "preview": None},
            ]
        },
    )
    _write(
        notes,
        {
            "notes": [
                {
                    "relpath": "notes/Aegis Gate.md",
                    "title": "Aegis Gate",
                    "tags": ["aegis"],
                    "project": "aegis",
                    "links": ["Hermes Brain"],
                    "excerpt": "fail-closed gate",
                }
            ]
        },
    )
    _write(
        projects,
        {"projects": [{"name": "aegis", "manifest": "PROJECT.md", "notes": ["notes/Aegis Gate.md"], "goals": []}]},
    )

    out = unified_search(
        "aegis gate",
        files_path=files,
        notes_path=notes,
        projects_path=projects,
    )
    assert out["external_search"] is False
    kinds = [hit["kind"] for hit in out["hits"]]
    assert "note" in kinds
    assert "project" in kinds
    tagged = unified_search(
        "gate",
        tag="aegis",
        kind="note",
        files_path=files,
        notes_path=notes,
        projects_path=projects,
    )
    assert tagged["hits"] and tagged["hits"][0]["kind"] == "note"


def test_unified_search_empty_index(tmp_path):
    out = unified_search("anything", files_path=tmp_path / "missing.json")
    assert out["hit_count"] == 0
    assert out["hits"] == []
    assert out["external_search"] is False
