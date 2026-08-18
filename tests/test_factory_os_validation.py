"""Adversarial validation for the factory OS overlay. No new product surface.

Extends existing AegisGuard, admission, outcomes, and context tests.
Unimplemented OS fields stay documented gaps. Matched-pair measurement
stays parked (D-015/D-016/D-019).
"""

from dataclasses import fields

import pytest

from aegis.agent_contract import AEGIS_AGENT_CONTRACT
from aegis.config import AegisConfig
from aegis.context_governor import evaluate_drift, meter_context
from aegis.guard import AegisGuard, AegisGuardError, aegis_protect
from aegis.outcomes import MINIMUM_MATCHED_TASKS, outcome_report, record_outcome
from aegis.wrappers.hermes_wrapper import TOOL_CAPABILITIES, GateResult, HermesWrapper

CONSEQUENTIAL_METADATA = (
    "economic",
    "privacy",
    "capacity",
    "risk",
    "authority",
    "reversibility",
)


def test_truncation_preserves_signal_and_prunes_filler():
    config = AegisConfig(
        guard_shadow_mode=False,
        guard_signal_shadow_mode=False,
        guard_max_output_length=80,
        guard_min_signal_score=0.5,
        guard_signal_preserve_keywords="ADMIT, DENY",
        guard_max_tool_calls=20,
        guard_max_velocity_calls_per_min=20,
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def emit(payload: str) -> str:
        return payload

    pruned = emit(payload=("noise " * 400) + " ADMIT token " + ("noise " * 400))
    assert "AEGIS SIGNAL PRUNED" in pruned
    assert "ADMIT token" in pruned
    filler = emit(payload="aaaa " * 500)
    assert "AEGIS SIGNAL PRUNED" in filler
    assert len(filler) < 400


def test_admission_false_positive_imitation_is_not_a_tool_call():
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from r012_admission_gate import admit_run, is_text_imitation

    stdout = '<invoke name="read_file">/etc/passwd</invoke>'
    assert is_text_imitation(stdout) is True
    out = admit_run(
        mode="treatment",
        stdout=stdout,
        usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        context_length=262144,
        metadata_advertises_tools=True,
        hermes_accepted=True,
        session_stats={
            "tool_call_count": 0,
            "api_call_count": 1,
            "read_file_executed": False,
            "tool_names": [],
        },
        guard_records=[],
    )
    assert out["admitted"] is False
    assert out["savings_percent"] is None
    assert out["token_delta"] is None


def test_matched_pair_requires_ten_observed_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    record_outcome(
        task_id="fp1", variant="baseline", accepted=True, elapsed_seconds=2,
        cost_usd=1.0, cost_status="observed", cost_source="hermes",
    )
    record_outcome(
        task_id="fp1", variant="governed", accepted=False, elapsed_seconds=2,
        cost_usd=1.0, cost_status="observed", cost_source="hermes",
    )
    report = outcome_report()
    assert report["paired_tasks"] == 1
    assert report["minimum_matched_tasks"] == MINIMUM_MATCHED_TASKS
    assert report["routing_authorized"] is False


def _gate_req(tool: str, args: dict):
    return {
        "tool_name": tool,
        "args": args,
        "identity": {"agent": "hermes", "session_id": "factory-os"},
        "scope": {"allowed_domains": ["/tmp/aegis"]},
    }


def test_require_review_is_not_hard_block_while_shadow_on():
    wrapper = HermesWrapper(
        AegisConfig(guard_shadow_mode=True, guard_allowed_domains="/tmp/aegis")
    )
    body = _gate_req("terminal", {"path": "/tmp/aegis/x"})
    result = wrapper.decide(body)
    assert result.decision == "require-review"
    assert result.would_block is True
    ran = wrapper.handle(body, execute_fn=lambda args: "ran")
    assert ran["executed"] is True
    assert ran["decision"] == "require-review"


def test_recovery_loop_and_context_pollution_bands():
    huge = [{"role": "user", "content": "x" * 8000}]
    status = meter_context(huge, expected_output_tokens=2000, capacity=1000)
    assert status.band in {"compact", "transfer", "red"}
    assert status.action != "work"
    drift = evaluate_drift("pack and land Aegis", "rewrite unrelated marketing site")
    assert drift > 0.0


def test_cost_overrun_unknown_cost_is_not_savings(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    row = record_outcome(task_id="c1", variant="baseline", accepted=True, elapsed_seconds=1)
    assert row["cost_status"] == "unknown"
    assert row["cost_usd"] is None


def test_provenance_loss_and_authority_expansion_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("AEGIS_HOME", str(tmp_path / "home"))
    wrapper = HermesWrapper(
        AegisConfig(guard_shadow_mode=True, guard_allowed_domains="/tmp/aegis")
    )
    denied = wrapper.decide(_gate_req("launch_missiles", {"path": "/tmp/aegis/x"}))
    assert denied.decision == "deny"
    assert denied.executed is False
    assert "memory" in TOOL_CAPABILITIES
    assert TOOL_CAPABILITIES["memory"]["capability"] == "memory.write"


def test_loop_risk_blocks_identical_repeats():
    config = AegisConfig(
        guard_shadow_mode=False,
        guard_max_tool_calls=20,
        guard_max_velocity_calls_per_min=20,
    )
    guard = AegisGuard(config)

    @aegis_protect(guard)
    def ping(arg1: str) -> str:
        return arg1

    ping(arg1="same")
    ping(arg1="same")
    with pytest.raises(AegisGuardError, match="LOOP"):
        ping(arg1="same")


def test_meta_instruction_bloat_and_missing_envelope_fields():
    assert len(AEGIS_AGENT_CONTRACT.split()) < 220
    present = {item.name for item in fields(GateResult)}
    missing = [key for key in CONSEQUENTIAL_METADATA if key not in present]
    assert "risk" in present
    assert missing == ["economic", "privacy", "capacity", "authority", "reversibility"]
