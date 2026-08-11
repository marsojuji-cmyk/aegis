"""Agent preflight + output lane activation."""

import os
import tempfile

import pytest

from aegis.cli import main
from aegis.ledger import read_all
from aegis.output_lane import activate_output, load_last_output, mode_default_profile
from aegis.preflight import run_preflight


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def test_mode_default_profile():
    assert mode_default_profile("implement") == "diff"
    assert mode_default_profile("explore") == "brief"
    assert mode_default_profile("review") == "json"


def test_activate_output_writes_lane(aegis_tmp):
    r = activate_output(profile="brief", mode="explore", task="t1")
    assert r["profile"] == "brief"
    assert r["tokens_saved_est"] > 0
    last = load_last_output()
    assert last is not None
    assert last["profile"] == "brief"
    # A profile receipt is a policy, not an already-generated model response.
    assert read_all() == []


def test_preflight_explore(aegis_tmp, tmp_path):
    f = tmp_path / "m.py"
    f.write_text('"""w"""\nimport os\n\ndef foo():\n    return 1\n')
    result = run_preflight(
        paths=[str(f)],
        task="preflight test",
        mode="explore",
    )
    assert result.ok is True
    assert result.exit_code == 0
    assert result.pack_id
    assert result.output_profile == "brief"
    assert result.summary.get("token_accounting") == "code_only"
    assert result.summary.get("output_saved_est", 0) > 0


def test_cli_preflight(aegis_tmp, tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def bar():\n    return 2\n")
    assert (
        main(
            [
                "preflight",
                "--task",
                "cli pf",
                "--mode",
                "explore",
                "--banner-only",
                str(f),
            ]
        )
        == 0
    )


def test_budget_shows_output_lane(aegis_tmp):
    activate_output(profile="diff", mode="implement")
    assert main(["budget"]) == 0
