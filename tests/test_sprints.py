"""Sprint ledger — seed, state machine, CLI, hermes search wrap."""

import json

import pytest

from aegis.cli import main
from aegis.sprints import (
    add_sprint,
    complete_sprint,
    complete_task,
    list_sprints,
    render_board,
    report,
    seed_board,
    start_sprint,
)


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_seed_is_idempotent(aegis_tmp):
    first = seed_board()
    second = seed_board()
    assert first["ok"]
    assert len(first["created"]) >= 8
    assert second["created"] == []
    assert second["total"] == first["total"]
    ids = {row["id"] for row in list_sprints()}
    assert {"SP-001", "SP-002", "SP-003", "SP-010", "SP-014"} <= ids


def test_start_complete_and_refuse_parked(aegis_tmp):
    seed_board()
    started = start_sprint("SP-001")
    assert started["ok"]
    assert started["sprint"]["status"] == "active"
    done = complete_sprint("SP-001", verified="module+CLI+tests", evidence="tests/test_sprints.py")
    assert done["ok"]
    assert done["sprint"]["status"] == "done"
    assert all(task["status"] == "done" for task in done["sprint"]["tasks"])
    parked = start_sprint("SP-010")
    assert parked["ok"] is False
    refused = complete_sprint("SP-010", verified="should fail")
    assert refused["ok"] is False
    from aegis.sprints import unpark_sprint

    opened = unpark_sprint("SP-013", reason="test")
    assert opened["ok"] is True
    assert opened["sprint"]["status"] == "planned"


def test_add_and_task(aegis_tmp):
    seed_board()
    row = add_sprint("adhoc hygiene", goal="one-off")
    assert row["id"].startswith("SP-")
    assert row["id"] not in {"SP-001", "SP-010"}
    from aegis.sprints import add_task

    added = add_task(row["id"], "touch README")
    assert added["ok"]
    finished = complete_task(row["id"], added["task"]["id"], evidence="README.md")
    assert finished["ok"]
    assert finished["task"]["status"] == "done"


def test_report_and_board(aegis_tmp, tmp_path):
    seed_board()
    start_sprint("SP-002")
    payload = report(repo=tmp_path)
    assert payload["counts"]["planned"] >= 1
    assert payload["counts"]["parked"] >= 1
    assert payload["active"][0]["id"] == "SP-002"
    text = render_board()
    assert "SP-001" in text
    assert "Sprint Board" in text


def test_cli_seed_list_report(aegis_tmp, tmp_path, capsys):
    assert main(["sprint", "seed"]) == 0
    capsys.readouterr()
    assert main(["sprint", "list", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert any(row["id"] == "SP-001" for row in rows)
    assert main(["sprint", "start", "SP-001"]) == 0
    capsys.readouterr()
    assert main([
        "sprint", "complete", "SP-001",
        "--verified", "cli smoke",
        "--evidence", "tests/test_sprints.py",
    ]) == 0
    assert main(["sprint", "start", "SP-010"]) == 2
    capsys.readouterr()
    assert main(["sprint", "report", "--repo", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["done"] >= 1
    dest = tmp_path / "board.md"
    assert main(["sprint", "board", "--write", str(dest)]) == 0
    assert dest.is_file()
    assert "SP-014" in dest.read_text(encoding="utf-8")


def test_hermes_search_cli(aegis_tmp, capsys):
    from aegis.hermes_notes import set_active_graph

    set_active_graph(None)
    index = aegis_tmp / "hermes_index"
    index.mkdir(parents=True)
    (index / "files.json").write_text(json.dumps({"files": []}), encoding="utf-8")
    (index / "notes.json").write_text(
        json.dumps(
            {
                "notes": [
                    {
                        "relpath": "Aegis Gate.md",
                        "title": "Aegis Gate",
                        "tags": ["aegis"],
                        "project": "aegis",
                        "links": [],
                        "excerpt": "fail-closed gate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (index / "projects.json").write_text(json.dumps({"projects": []}), encoding="utf-8")
    (index / "graph.json").write_text(json.dumps({"nodes": [], "edges": []}), encoding="utf-8")
    assert main(["hermes", "search", "gate", "--kind", "note"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["external_search"] is False
    assert payload["hit_count"] >= 1
    assert payload["hits"][0]["title"] == "Aegis Gate"
    assert main(["hermes", "resolve", "Aegis Gate"]) == 0
    resolved = json.loads(capsys.readouterr().out)
    assert "warnings" in resolved
