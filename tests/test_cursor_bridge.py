"""Cursor composer bridge — rules install, context, outputs."""

import pytest

from aegis.cli import main
from aegis.cursor_bridge import (
    cursor_context,
    cursor_status,
    install_cursor_rules,
    list_cursor_outputs,
)


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_install_cursorrules(aegis_tmp):
    import os
    from pathlib import Path
    
    cwd_rule = Path.cwd() / ".cursorrules"
    before = cwd_rule.read_bytes() if cwd_rule.exists() else None

    target = aegis_tmp / "target_dir"
    target.mkdir()
    res = install_cursor_rules(target_dir=str(target))
    
    after = cwd_rule.read_bytes() if cwd_rule.exists() else None
    assert after == before

    assert res["count"] >= 6
    assert (target / ".cursorrules").is_file()
    assert (target / ".cursorignore").is_file()
    for name in (
        "aegis-pack-first",
        "aegis-continuity",
        "aegis-sprint",
        "aegis-hermes",
        "aegis-flow",
    ):
        skill = target / "skills" / name / "SKILL.md"
        assert skill.is_file(), name
        text = skill.read_text(encoding="utf-8")
        assert f"name: {name}" in text
    text = (target / ".cursorrules").read_text()
    assert "aegis cursor" in text.lower() or "AEGIS" in text
    assert "outputs" in text
    assert "Perplexity" in text
    assert "aegis-flow" in text
    
    import os
    from pathlib import Path
    for written in res["written"]:
        assert os.path.commonpath([
            str(Path(written).resolve()),
            str(target.resolve()),
        ]) == str(target.resolve())


def test_cursor_context(aegis_tmp):
    f = aegis_tmp / "mod.py"
    f.write_text("def foo():\n    return 1\n")
    ctx = cursor_context(task="edit foo", paths=[str(f)], mode="implement")
    assert ctx["ok"] is True
    assert "AEGIS CURSOR CONTEXT" in ctx["composer_block"]
    assert ctx["meta"].get("pack_id")
    assert "outputs" in ctx["meta"].get("outputs_dir", "")


def test_cli_cursor_task(aegis_tmp):
    f = aegis_tmp / "a.py"
    f.write_text("def bar():\n    return 2\n")
    assert (
        main(
            [
                "cursor",
                "--task",
                "composer pack",
                "--mode",
                "explore",
                str(f),
            ]
        )
        == 0
    )


def test_cli_cursor_install_status(aegis_tmp):
    assert main(["cursor", "--install", "--dir", str(aegis_tmp)]) == 0
    assert main(["cursor", "--status"]) == 0
    assert main(["cursor", "--outputs"]) == 0


def test_cli_cursor_with_model(aegis_tmp):
    f = aegis_tmp / "b.py"
    f.write_text("def z():\n    return 0\n")
    assert (
        main(
            [
                "cursor",
                "--task",
                "router path",
                "--model",
                "mock",
                "--mode",
                "explore",
                str(f),
            ]
        )
        == 0
    )


def test_cursor_status_shape(aegis_tmp):
    st = cursor_status()
    assert "outputs_dir" in st
    assert "cli" in st
    assert "skills" in st


def test_install_cursor_skills_to_agents_dir(aegis_tmp, tmp_path, monkeypatch):
    from aegis.cursor_bridge import CURSOR_SKILL_NAMES, install_cursor_skills

    dest = tmp_path / "agents-skills"
    monkeypatch.setenv("AEGIS_AGENTS_SKILLS", str(dest))
    written = install_cursor_skills()
    assert len(written) == 5
    assert {p.name for p in dest.iterdir()} == set(CURSOR_SKILL_NAMES)


def test_cursor_pack_first_reuse_and_gate(aegis_tmp):
    from aegis.cursor_bridge import cursor_gate

    a = aegis_tmp / "a.py"
    b = aegis_tmp / "b.py"
    a.write_text("def a():\n    return 1\n")
    b.write_text("def b():\n    return 2\n")
    first = cursor_context(task="pack both", paths=[str(a), str(b)], mode="implement")
    assert first["ok"] is True
    assert first["reuse"] == "miss"
    assert first["pack_id"]
    assert "reuse=miss" in first["composer_block"]
    second = cursor_context(task="subset", paths=[str(a)], mode="implement")
    assert second["ok"] is True
    assert second["reuse"] == "hit"
    assert second["pack_id"] == first["pack_id"]
    assert "reuse=hit" in second["composer_block"]
    gate = cursor_gate(str(a), mode="implement")
    assert gate["action"] == "reuse"
    assert gate["pack_id"] == first["pack_id"]
    assert main(["cursor", "--gate", str(a), "--mode", "implement"]) == 0


def test_cursor_empty_pack_without_neighbors(aegis_tmp, tmp_path):
    missing = tmp_path / "nowhere" / "ghost.py"
    ctx = cursor_context(task="empty", paths=[str(missing)], mode="explore")
    assert ctx["ok"] is False
    assert ctx["reason"] == "EMPTY_PACK"
    assert ctx["pack_id"] is None


def test_cursor_packs_neighbor_when_target_missing(aegis_tmp):
    pkg = aegis_tmp / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("x = 1\n")
    missing = pkg / "new_mod.py"
    ctx = cursor_context(task="new file", paths=[str(missing)], mode="implement")
    assert ctx["ok"] is True
    assert ctx["pack_id"]
    assert ctx["expanded"]["neighbors"]
    assert str((pkg / "__init__.py").resolve()) in ctx["meta"]["paths"]
