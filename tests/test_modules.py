"""Budget-aware module health probes."""

import pytest

from aegis.cli import main
from aegis.config import opt_in
from aegis.intelligence import start_background_ticks
from aegis.modules import MODULE_IDS, health
from aegis.policy_nudges import apply_policy_nudges


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_USER", raising=False)
    return tmp_path / "home"


def test_opt_in_fail_closed():
    class Bare:
        pass

    assert opt_in(Bare(), "auto_tick") is False
    assert opt_in(Bare(), "auto_invest") is False
    assert opt_in(None, "auto_memory") is False


def test_missing_auto_tick_does_not_start_loop(aegis_tmp):
    from aegis.portable import init_home

    init_home()

    class Bare:
        pass

    out = start_background_ticks(Bare())
    assert out.get("ok") is False
    assert "auto_tick" in str(out.get("message") or "")


def test_policy_nudges_fail_closed_without_flag(aegis_tmp):
    from aegis.portable import init_home

    init_home()

    class Bare:
        pass

    cfg, applied = apply_policy_nudges(
        [{"id": "x", "fix": "default_mode_explore"}],
        Bare(),
    )
    assert applied == []
    assert cfg is not None


def test_health_covers_every_module(aegis_tmp):
    from aegis.portable import init_home

    init_home()
    report = health()
    ids = [row["id"] for row in report["modules"]]
    assert ids == list(MODULE_IDS)
    assert len(ids) == 14
    by_id = {row["id"]: row for row in report["modules"]}
    assert by_id["M-001"]["verdict"] == "keep"
    assert by_id["M-006"]["verdict"] == "park"
    assert by_id["M-008"]["verdict"] == "park"
    assert by_id["M-011"]["verdict"] == "keep"
    assert by_id["M-012"]["verdict"] == "keep"
    assert by_id["M-013"]["verdict"] == "superseded"
    assert by_id["M-013"]["aligned"] is True
    assert by_id["M-014"]["verdict"] == "keep"


def test_cli_modules_health(aegis_tmp):
    from aegis.portable import init_home

    init_home()
    assert main(["modules", "health", "--json"]) in (0, 1)
