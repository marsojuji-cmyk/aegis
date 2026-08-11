"""Doctor + legacy load."""

import pytest

from aegis.compat.legacy import get_engine_name, legacy_available
from aegis.doctor import doctor_report, run_checks


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))


def test_engine_default_legacy(aegis_tmp):
    assert get_engine_name() in ("legacy", "product")


def test_legacy_available(aegis_tmp):
    assert legacy_available() is True


def test_doctor_ok_in_compat(aegis_tmp):
    report = doctor_report()
    assert "checks" in report
    names = {c["name"]: c["pass"] for c in report["checks"]}
    assert names.get("legacy_pipeline") is True
    assert names.get("legacy_import") is True
    assert names.get("compat_mode") is True


def test_run_checks_nonempty(aegis_tmp):
    assert len(run_checks()) >= 5


def test_doctor_reports_remote_credential_coverage(aegis_tmp):
    checks = {name: detail for name, _ok, detail in run_checks()}
    assert "remote credentials=" in checks["universal_router"]


def test_doctor_fails_for_unwritable_aegis_home(tmp_path, monkeypatch):
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory")
    monkeypatch.setenv("AEGIS_HOME", str(blocked / "home"))
    checks = {name: ok for name, ok, _detail in run_checks()}
    assert checks["aegis_home"] is False
