"""Tests for durable memory admission."""

import json

import pytest

from aegis.memory_admit import (
    add_conflict,
    admit,
    delete_record,
    list_records,
    neutral_emotion,
    propose,
    record_stats,
    validate_record,
)


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def _valid_record(**overrides):
    row = {
        "id": "mem_test001",
        "memory_type": "semantic",
        "content": "Aegis pack reuse hits when hashes match.",
        "provenance": {
            "source_type": "direct_observation",
            "source_id": "test/fixture",
            "captured_by": "pytest",
        },
        "confidence": 0.9,
        "evidence_status": "verified",
        "emotion": neutral_emotion(),
        "privacy_class": "internal",
        "observed_at": "2026-08-21T00:00:00+00:00",
        "recorded_at": "2026-08-21T00:00:00+00:00",
        "deletion_path": "aegis memory delete --id mem_test001",
        "conflicts_with": [],
    }
    row.update(overrides)
    return row


def test_validate_rejects_missing_fields():
    ok, errors = validate_record({"id": "x"})
    assert ok is False
    assert any("missing" in e for e in errors)


def test_validate_rejects_preference_without_verified_evidence():
    row = _valid_record(memory_type="preference", evidence_status="proposed")
    ok, errors = validate_record(row)
    assert ok is False
    assert any("preference" in e for e in errors)


def test_admit_and_list(aegis_tmp):
    row = admit(_valid_record())
    assert row["id"] == "mem_test001"
    listed = list_records(memory_type="semantic")
    assert len(listed) == 1
    stats = record_stats()
    assert stats["entries"] == 1


def test_conflict_preserves_prior_content(aegis_tmp):
    a = admit(_valid_record(id="mem_a", content="first claim"))
    b = admit(_valid_record(id="mem_b", content="contradicting claim"))
    linked = add_conflict("mem_a", "mem_b", reason="observed mismatch")
    assert "mem_b" in linked["conflicts_with"]
    rows = {r["id"]: r for r in list_records(limit=10)}
    assert rows["mem_a"]["content"] == "first claim"
    assert rows["mem_b"]["content"] == "contradicting claim"


def test_delete_record(aegis_tmp):
    admit(_valid_record())
    out = delete_record("mem_test001")
    assert out["remaining"] == 0


def test_propose_creates_proposed_status(aegis_tmp):
    row = propose("router run captured note", source_id="run:abc")
    assert row["evidence_status"] == "proposed"
    assert record_stats()["proposed"] == 1


def test_admit_duplicate_id_fails(aegis_tmp):
    admit(_valid_record())
    with pytest.raises(ValueError, match="already exists"):
        admit(_valid_record())
