import json

import pytest

from aegis.config import AegisConfig
from aegis.context_governor import (
    evaluate_drift,
    load_latest_capsule,
    meter_context,
    persist_capsule,
    state_capsule,
)
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


def test_context_config_rejects_inconsistent_thresholds():
    assert AegisConfig(
        context_checkpoint_percent=60,
        context_transfer_percent=85,
    ).context_transfer_percent == 85
    for checkpoint, transfer in ((0, 85), (85, 85), (90, 85), (60, 101)):
        with pytest.raises(ValueError, match="context thresholds"):
            AegisConfig(
                context_checkpoint_percent=checkpoint,
                context_transfer_percent=transfer,
            )


def test_capsule_is_bounded_and_persisted(aegis_tmp):
    capsule = state_capsule(objective="ship release", decisions=["use hashes"], verified=["hashes checked"], next_action="run test suite")
    path = persist_capsule(capsule)
    assert json.loads(path.read_text())["fingerprint"] == capsule["fingerprint"]
    with pytest.raises(ValueError):
        state_capsule(objective="x" * 20_000, verified=["bounded"], next_action="run check", max_tokens=1)


def test_latest_capsule_rejects_corrupt_or_tampered_state(aegis_tmp):
    capsule = state_capsule(
        objective="resume verified work", verified=["focused tests passed"],
        next_action="run the next matched pair",
    )
    path = persist_capsule(capsule)
    assert load_latest_capsule()["fingerprint"] == capsule["fingerprint"]

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["verified"] = ["invented result"]
    path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_latest_capsule()

    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="capsule is corrupt"):
        load_latest_capsule()


def test_batch_builder_uses_responses_and_flex():
    lines = build_response_batch([{"id": "a", "input": [{"role": "user", "content": "hi"}]}], model="gpt-test")
    row = json.loads(lines)
    assert row["url"] == "/v1/responses"
    assert row["body"]["service_tier"] == "flex"


def test_context_cli_persists_transfer_capsule(aegis_tmp):
    assert main(["context", "--objective", "ship fix", "--verified", "test passed", "--next-action", "send handoff", "--json"]) == 0


def test_continuity_checkpoint_persists_verified_capsule(aegis_tmp):
    assert main(["continuity", "checkpoint", "--objective", "ship", "--verified", "tests pass", "--next-action", "handoff"]) == 0


def test_provisional_capsule_is_labeled():
    capsule = state_capsule(objective="transfer task", next_action="start fresh task", verification_status="provisional")
    assert capsule["verification_status"] == "provisional"


def test_verified_capsule_rejects_template_filler():
    with pytest.raises(ValueError, match="specific"):
        state_capsule(objective="...", verified=["..."], next_action="...")
    with pytest.raises(ValueError, match="verified capsule"):
        state_capsule(objective="ship release", next_action="open pull request")


def test_evaluate_drift():
    # Identical texts should have ~0.0 drift
    assert evaluate_drift("test mission", "test mission") < 0.01
    
    # Completely unrelated texts should have high drift
    score1 = evaluate_drift("build authentication system", "mine cryptocurrency")
    assert score1 > 0.4
    
    # Empty texts
    assert evaluate_drift("", "something") == 0.0


def test_state_capsule_mission_lock():
    # In scope
    capsule = state_capsule(
        objective="add evaluate_drift function",
        verified=["function added"],
        next_action="add evaluate_drift function tests",
        mission="add evaluate_drift function",
    )
    assert capsule["drift_status"] == "ok"
    
    # Completely unrelated - should hit quarantine
    capsule = state_capsule(
        objective="mine cryptocurrency on servers",
        verified=["mining pool connected"],
        next_action="scale up workers",
        mission="add evaluate_drift function and tests",
    )
    assert capsule["drift_status"] in ("quarantine", "warn")
    assert capsule["drift_score"] > 0.3


def test_sentinel_capsule_fields_optional(aegis_tmp):
    capsule = state_capsule(
        objective="resume verified work",
        verified=["pytest green"],
        next_action="run relay export",
        owner="operator",
        privacy_class="internal",
        open_risks=["routing scope unchanged"],
        evidence_refs=[{"kind": "path", "ref": "/tmp/evidence.json"}],
        deletion_path="remove capsule file",
    )
    assert capsule["owner"] == "operator"
    assert capsule["privacy_class"] == "internal"
    assert capsule["open_risks"]
    assert capsule["evidence_refs"]
    assert capsule["deletion_path"] == "remove capsule file"
    assert "recorded_at" in capsule

