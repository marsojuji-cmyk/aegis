"""Path A demo clock and four-beat rehearsal."""

from datetime import date, timedelta

import pytest

from aegis.cli import main
from aegis.demo import CLOCK_DAYS, name_buyer, pack_twice, run, start_clock, status
from aegis.paths import close_clock_path


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_USER", raising=False)
    return tmp_path / "home"


def test_clock_and_buyer(aegis_tmp):
    from aegis.portable import init_home

    init_home()
    started = start_clock()
    assert started["running"] is True
    assert started["days_left"] == CLOCK_DAYS
    assert started["buyer_named"] is False
    assert started["savings_percent"] is None
    assert started["routing_authorized"] is False
    again = start_clock()
    assert again["created"] is False
    named = name_buyer("  Lab Owner  ")
    assert named["buyer_name"] == "Lab Owner"
    assert named["buyer_named"] is True
    assert named["ok"] is True
    assert close_clock_path().is_file()


def test_overdue_without_buyer(aegis_tmp):
    from aegis.portable import init_home

    init_home()
    start_clock()
    body = status()
    body["deadline"] = (date.today() - timedelta(days=1)).isoformat()
    # Force persisted overdue state.
    import json

    raw = json.loads(close_clock_path().read_text(encoding="utf-8"))
    raw["started"] = (date.today() - timedelta(days=CLOCK_DAYS + 1)).isoformat()
    raw["deadline"] = (date.today() - timedelta(days=1)).isoformat()
    close_clock_path().write_text(json.dumps(raw), encoding="utf-8")
    late = status()
    assert late["overdue"] is True
    assert late["ok"] is False
    assert late["savings_percent"] is None


def test_pack_twice_covering_hit(aegis_tmp, tmp_path):
    from aegis.portable import init_home

    init_home()
    sample = tmp_path / "sample.py"
    sample.write_text("def demo():\n    return 1\n", encoding="utf-8")
    packed = pack_twice([str(sample)])
    assert packed["ok"] is True
    assert packed["covering_hit"] is True
    assert packed["second"]["reuse"] is True
    assert packed["savings_percent"] is None


def test_demo_run_and_cli(aegis_tmp, tmp_path):
    from aegis.portable import init_home

    init_home()
    sample = tmp_path / "sample.py"
    sample.write_text("x = 1\n", encoding="utf-8")
    payload = run([str(sample)])
    assert payload["ok"] is True
    assert payload["savings_percent"] is None
    assert payload["routing_authorized"] is False
    assert payload["beat2_pack"]["covering_hit"] is True
    assert payload["beat3_price"]["hosted"] is None
    assert payload["beat4_honesty"]["aa_models"][2]["index"] == 53
    assert payload["clock"]["running"] is True
    assert main(["demo", "status"]) == 0
    assert main(["demo", "script"]) == 0
    assert main(["demo", "run", "--skip-pack", "--json"]) == 0
    assert main(["demo", "run"]) == 2
