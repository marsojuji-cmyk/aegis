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
    res = install_cursor_rules(target_dir=str(aegis_tmp))
    assert res["count"] >= 2
    assert (aegis_tmp / ".cursorrules").is_file()
    assert (aegis_tmp / ".cursorignore").is_file()
    text = (aegis_tmp / ".cursorrules").read_text()
    assert "aegis cursor" in text.lower() or "AEGIS" in text
    assert "outputs" in text


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
