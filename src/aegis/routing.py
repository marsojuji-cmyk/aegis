"""Tiny-chat routing trial. Implement packs stay on the requested model.

matched_provider_pairs is the only workflow with a quality-preserving cost
cut. aegis_pack_scale and coding_prompt_scale lose money — do not route them.
"""

from __future__ import annotations

from typing import Any, Dict, List

from aegis.pack_cache import normalize_mode

BASELINE_MODEL = "deepseek/deepseek-v4-pro"
GOVERNED_MODEL = "openai/gpt-5.4-nano"
TINY_CHAT_MODES = frozenset({"explore", "review"})
MOCK_MODELS = frozenset({"mock", "echo"})


def workflow_compare() -> List[Dict[str, Any]]:
    """Side-by-side billed-pair math for every recorded workflow."""
    from aegis.outcomes import load_outcome_evidence, outcome_report

    workflows = sorted(
        {
            str(row.get("workflow") or "")
            for row in load_outcome_evidence()["rows"]
            if row.get("workflow")
        }
    )
    rows: List[Dict[str, Any]] = []
    for workflow in workflows:
        report = outcome_report(workflow=workflow)
        rows.append(
            {
                "workflow": workflow,
                "paired_tasks": int(report.get("paired_tasks") or 0),
                "observed_cost_pairs": int(report.get("observed_cost_pairs") or 0),
                "savings_percent": report.get("savings_percent"),
                "total_cost_usd_saved": report.get("total_cost_usd_saved"),
                "routing_authorized": bool(report.get("routing_authorized")),
                "decision": report.get("decision"),
            }
        )
    return rows


def apply_route(*, model: str, mode: str = "explore") -> Dict[str, Any]:
    """Swap v4-pro → nano only for explore/review when pair math authorizes it."""
    from aegis.outcomes import outcome_report
    from aegis.receipt_collect import PAIR_WORKFLOW

    requested = (model or "").strip() or "mock"
    mode_n = normalize_mode(mode)
    report = outcome_report(workflow=PAIR_WORKFLOW)
    eligible = bool(report.get("routing_authorized"))
    body: Dict[str, Any] = {
        "requested_model": requested,
        "mode": mode_n,
        "savings_percent": report.get("savings_percent"),
        "routing_authorized": eligible,
        "applied": False,
        "model": requested,
        "reason": "not_eligible",
    }
    if requested in MOCK_MODELS or requested.startswith("mock"):
        body["reason"] = "mock"
        return body
    if not eligible:
        return body
    if mode_n == "implement":
        body["reason"] = "implement_pack_loses_money"
        return body
    if mode_n not in TINY_CHAT_MODES:
        body["reason"] = f"mode_{mode_n}_not_tiny_chat"
        return body
    if "nano" in requested:
        body["reason"] = "already_governed"
        return body
    if requested != BASELINE_MODEL and "deepseek-v4-pro" not in requested:
        body["reason"] = "model_not_in_trial"
        return body
    body["applied"] = True
    body["from_model"] = requested
    body["model"] = GOVERNED_MODEL
    body["reason"] = "tiny_chat_trial"
    return body
