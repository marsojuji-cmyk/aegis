"""Offline R-012 admission gate. No model calls."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from r012_admission_gate import (
    MARKER,
    _NOT_ADMITTED,
    admit_pair,
    admit_run,
    classify_compatibility_artifact,
    is_prose_claim,
    is_text_imitation,
)


def _run(stdout, *, mode="control", tool_count=0, read_file=False, guard=None):
    return admit_run(
        mode=mode,
        stdout=stdout,
        usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
        context_length=262144,
        metadata_advertises_tools=True,
        hermes_accepted=True,
        session_stats={
            "tool_call_count": tool_count,
            "api_call_count": 1,
            "read_file_executed": read_file,
            "tool_names": ["read_file"] if read_file else [],
        },
        guard_records=guard or [],
    )


def _reject_shape(out):
    assert out["admitted"] is False
    assert out["native_tool_call"] is False
    assert out["tool_event_observed"] is False
    assert out["gate_observed"] is False
    assert out["marker_check"] is False
    assert out["token_delta"] is None
    assert out["savings_percent"] is None
    assert out["decision_summary"] == _NOT_ADMITTED


def test_xml_imitation_rejected():
    assert is_text_imitation("<tool_call><read_file>")
    out = _run("<tool_call><read_file><path>/tmp/x</path></read_file>")
    assert out["checks"]["no_text_imitation_tool_call"] is False
    assert out["checks"]["tool_call_count_gt_0"] is False
    _reject_shape(out)


def test_vendor_markup_rejected():
    out = _run("<|tool_call:start|>read_file")
    _reject_shape(out)


def test_dsml_imitation_rejected():
    stdout = (
        "<\uff5c\uff5cDSML\uff5c\uff5ctool_calls>\n"
        '<\uff5c\uff5cDSML\uff5c\uff5cinvoke name="read_file">\n'
        '<\uff5c\uff5cDSML\uff5c\uff5cparameter name="file" string="true">'
        "/tmp/aegis-r012-admit/marker.txt"
        "</\uff5c\uff5cDSML\uff5c\uff5cparameter>\n"
        "</\uff5c\uff5cDSML\uff5c\uff5cinvoke>\n"
        "</\uff5c\uff5cDSML\uff5c\uff5ctool_calls>\n"
    )
    assert is_text_imitation(stdout)
    out = _run(stdout)
    assert out["checks"]["no_text_imitation_tool_call"] is False
    _reject_shape(out)


def test_dsml_plus_guessed_marker_rejected():
    out = _run(f'invoke name="read_file"\n{MARKER}\n')
    assert out["checks"]["no_text_imitation_tool_call"] is False
    _reject_shape(out)


def test_prose_claim_without_tool_rejected():
    assert is_prose_claim("I read the file and it looks fine.")
    out = _run("I read the file and it looks fine.")
    assert out["checks"]["no_text_imitation_tool_call"] is False
    _reject_shape(out)


def test_hallucinated_marker_rejected():
    out = _run("R012-MEASURE-ACTIVE")
    assert MARKER not in "R012-MEASURE-ACTIVE"
    assert out["checks"]["no_hallucinated_content"] is False
    _reject_shape(out)


def test_guessed_exact_marker_without_tool_rejected():
    out = _run(MARKER + "\n", tool_count=0, read_file=False)
    assert out["checks"]["tool_call_count_gt_0"] is False
    _reject_shape(out)


def test_advertised_tools_not_sufficient():
    out = _run("nope", tool_count=0)
    assert out["checks"]["metadata_advertises_tools"] is True
    assert out["admitted"] is False


def test_native_control_admitted():
    out = _run(MARKER + "\n", tool_count=1, read_file=True)
    assert out["admitted"] is True
    assert out["native_tool_call"] is True
    assert out["tool_event_observed"] is True
    assert out["marker_check"] is True
    assert out["decision_summary"] is None
    assert out["token_delta"] is None
    assert out["savings_percent"] is None


def test_treatment_requires_gate_observation():
    bare = _run(MARKER + "\n", mode="treatment", tool_count=1, read_file=True)
    assert bare["admitted"] is False
    assert bare["gate_observed"] is False
    gated = _run(
        MARKER + "\n",
        mode="treatment",
        tool_count=1,
        read_file=True,
        guard=[{"action": "allow", "rule": "hermes"}],
    )
    assert gated["admitted"] is True
    assert gated["gate_observed"] is True


def test_pair_invalid_nulls_efficiency():
    control = _run(MARKER + "\n", tool_count=1, read_file=True)
    treatment = _run("<tool_call>", mode="treatment")
    pair = admit_pair(control, treatment)
    assert pair["pair_valid"] is False
    assert pair["token_delta"] is None
    assert pair["savings_percent"] is None
    assert pair["efficiency_result"] == "invalid_pair"
    assert pair["decision_summary"] == _NOT_ADMITTED


def test_cli_no_args_is_not_admission():
    from r012_admission_gate import main

    assert main([]) == 2


def test_cli_scores_failed_artifact(tmp_path):
    from r012_admission_gate import main, score_artifact

    src = Path("/tmp/aegis-r012-measure/admission-20260815.json")
    if src.is_file():
        path = src
    else:
        path = tmp_path / "fail.json"
        path.write_text(
            json.dumps(
                {
                    "admission": {
                        "admitted": False,
                        "decision_summary": _NOT_ADMITTED,
                        "checks": {"tool_call_count_gt_0": False},
                    }
                }
            )
        )
    scored = score_artifact(path)
    assert scored["admitted"] is False
    assert scored["savings_percent"] is None
    assert main([str(path)]) == 2


def test_compatibility_artifact_has_no_native_model(tmp_path):
    src = Path("/tmp/aegis-r012-measure/compatibility-20260814.json")
    if src.is_file():
        summary = classify_compatibility_artifact(src)
    else:
        fake = tmp_path / "c.json"
        fake.write_text(
            json.dumps(
                {
                    "pair_run": False,
                    "token_delta": None,
                    "savings_percent": None,
                    "screened": [{"native_tool_call": False}],
                }
            )
        )
        summary = classify_compatibility_artifact(fake)
    assert summary["any_native_tool_call"] is False
    assert summary["compatible_model"] is None
    assert summary["token_delta"] is None
    assert summary["savings_percent"] is None
