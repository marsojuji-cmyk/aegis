import json

import pytest

from aegis.context_governor import meter_context, persist_capsule, state_capsule
from aegis.openai_batch import build_response_batch
from aegis.cli import main


@pytest.fixture()
def aegis_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))


def test_context_bands_include_expected_output():
    messages = [{"role": "user", "content": "x" * 400}]
    status = meter_context(messages, expected_output_tokens=20, capacity=100)
    assert status.band in {"checkpoint", "compact", "transfer", "red"}
    assert status.assembled_tokens > 0


def test_capsule_is_bounded_and_persisted(aegis_tmp):
    capsule = state_capsule(objective="ship", decisions=["use hashes"], next_action="test")
    path = persist_capsule(capsule)
    assert json.loads(path.read_text())["fingerprint"] == capsule["fingerprint"]
    with pytest.raises(ValueError):
        state_capsule(objective="x" * 20_000, max_tokens=1)


def test_batch_builder_uses_responses_and_flex():
    lines = build_response_batch([{"id": "a", "input": [{"role": "user", "content": "hi"}]}], model="gpt-test")
    row = json.loads(lines)
    assert row["url"] == "/v1/responses"
    assert row["body"]["service_tier"] == "flex"


def test_context_cli_persists_transfer_capsule(aegis_tmp):
    assert main(["context", "--objective", "ship", "--next-action", "test", "--json"]) == 0


def test_provisional_capsule_is_labeled():
    capsule = state_capsule(objective="transfer", verification_status="provisional")
    assert capsule["verification_status"] == "provisional"
