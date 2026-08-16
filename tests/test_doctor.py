"""Doctor + legacy load."""

import json

import pytest

from aegis.compat.legacy import get_engine_name, legacy_available
from aegis.config import load_config, resolve_hermes_notes_root, save_config
from aegis.doctor import (
    CANONICAL_HERMES_CORPUS,
    COMPLEMENTARY_LABS,
    classify_hermes_root,
    doctor_report,
    hermes_corpus_check,
    hermes_rebuild_root_decision,
    run_checks,
)
from aegis.hermes_index import DEFAULT_ROOT
from aegis.paths import hermes_index_dir, hermes_index_files_path, hermes_index_notes_path


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AEGIS_HERMES_NOTES_ROOT", raising=False)


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


def test_rebuild_root_decision_roles(aegis_tmp, tmp_path, monkeypatch):
    denied = hermes_rebuild_root_decision(str(COMPLEMENTARY_LABS))
    assert denied["allowed"] is False
    assert denied["role"] == "complementary"
    denied_empty = hermes_rebuild_root_decision(DEFAULT_ROOT)
    assert denied_empty["allowed"] is False
    assert denied_empty["role"] == "empty_default_not_product"
    pin = tmp_path / "canonical-fixture"
    pin.mkdir()
    monkeypatch.setenv("AEGIS_HERMES_NOTES_ROOT", str(pin))
    allowed = hermes_rebuild_root_decision(str(pin))
    assert allowed["allowed"] is True
    assert allowed["role"] == "canonical"


def test_classify_hermes_root_roles():
    assert classify_hermes_root("") == "missing"
    assert classify_hermes_root(str(CANONICAL_HERMES_CORPUS)) == "canonical"
    assert classify_hermes_root(str(COMPLEMENTARY_LABS)) == "complementary"
    assert classify_hermes_root(DEFAULT_ROOT) == "empty_default_not_product"
    assert classify_hermes_root("/tmp/not-a-product-root") == "unknown"


def _write_index(path, root: str, **counts) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"root": root, **counts}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_hermes_corpus_missing_index_is_not_product_ready_label(aegis_tmp):
    name, ok, detail = hermes_corpus_check()
    assert name == "hermes_corpus"
    assert ok is True
    assert "notes=missing:0" in detail
    assert "canonical=" in detail
    assert "complementary=" in detail
    assert "empty_default=" in detail
    assert "pin=unset" in detail
    assert "v1_ready=no" in detail


def test_hermes_corpus_fails_empty_default_and_labs_notes(aegis_tmp):
    _write_index(hermes_index_notes_path(), DEFAULT_ROOT, note_count=0)
    name, ok, detail = hermes_corpus_check()
    assert name == "hermes_corpus"
    assert ok is False
    assert "notes=empty_default_not_product:0" in detail

    _write_index(
        hermes_index_notes_path(),
        str(COMPLEMENTARY_LABS),
        note_count=3,
    )
    _ok = hermes_corpus_check()[1]
    assert _ok is False
    assert "notes=complementary:3" in hermes_corpus_check()[2]


def test_hermes_corpus_passes_canonical_notes_even_if_files_empty(aegis_tmp):
    _write_index(
        hermes_index_notes_path(),
        str(CANONICAL_HERMES_CORPUS),
        note_count=9,
    )
    _write_index(hermes_index_files_path(), DEFAULT_ROOT, file_count=0)
    name, ok, detail = hermes_corpus_check()
    assert name == "hermes_corpus"
    assert ok is True
    assert "notes=canonical:9" in detail
    assert "files=empty_default_not_product:0" in detail
    assert "pin=unset" in detail
    assert "v1_ready=no" in detail
    assert hermes_index_dir().is_dir()


def test_resolve_hermes_notes_root_env_overrides_config(aegis_tmp, tmp_path, monkeypatch):
    cfg = load_config()
    cfg.hermes_notes_root = str(tmp_path / "from-config")
    save_config(cfg)
    assert resolve_hermes_notes_root() == str(tmp_path / "from-config")
    monkeypatch.setenv("AEGIS_HERMES_NOTES_ROOT", str(tmp_path / "from-env"))
    assert resolve_hermes_notes_root() == str(tmp_path / "from-env")


def test_hermes_corpus_env_pin_makes_v1_ready(aegis_tmp, tmp_path, monkeypatch):
    pin = tmp_path / "canonical-fixture"
    pin.mkdir()
    monkeypatch.setenv("AEGIS_HERMES_NOTES_ROOT", str(pin))
    _write_index(hermes_index_notes_path(), str(pin), note_count=2)
    _write_index(hermes_index_files_path(), DEFAULT_ROOT, file_count=0)
    name, ok, detail = hermes_corpus_check()
    assert name == "hermes_corpus"
    assert ok is True
    assert "notes=canonical:2" in detail
    assert "files=empty_default_not_product:0" in detail
    assert "pin=set" in detail
    assert "v1_ready=yes" in detail


def test_hermes_corpus_invalid_pin_is_not_v1_ready(aegis_tmp, monkeypatch):
    monkeypatch.setenv("AEGIS_HERMES_NOTES_ROOT", DEFAULT_ROOT)
    _write_index(hermes_index_notes_path(), DEFAULT_ROOT, note_count=0)
    name, ok, detail = hermes_corpus_check()
    assert ok is False
    assert "notes=empty_default_not_product:0" in detail
    assert "pin=set" in detail
    assert "v1_ready=no" in detail

    monkeypatch.setenv("AEGIS_HERMES_NOTES_ROOT", str(COMPLEMENTARY_LABS))
    _write_index(hermes_index_notes_path(), str(COMPLEMENTARY_LABS), note_count=3)
    _ok, detail = hermes_corpus_check()[1], hermes_corpus_check()[2]
    assert _ok is False
    assert "notes=complementary:3" in detail
    assert "v1_ready=no" in detail


def test_doctor_includes_hermes_corpus(aegis_tmp):
    names = {c["name"]: c["pass"] for c in doctor_report()["checks"]}
    assert "hermes_corpus" in names
    assert names["hermes_corpus"] is True
