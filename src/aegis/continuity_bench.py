"""Offline continuity A/B bench: baseline capsule vs memory_admit + sentinel v2.

Holds fixture constant; compares handoff integrity without model calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from aegis.context_governor import persist_capsule, state_capsule
from aegis.memory_admit import add_conflict, admit, list_records, neutral_emotion
from aegis.relay import query, tail


@dataclass
class CaseResult:
    case_id: str
    handoff_failures: List[str]
    unsupported_recalls: List[str]
    relay_linked: bool
    passed: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "handoff_failures": self.handoff_failures,
            "unsupported_recalls": self.unsupported_recalls,
            "relay_linked": self.relay_linked,
            "passed": self.passed,
        }


def _load_cases(path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("cases file must contain a cases array")
    return [c for c in cases if isinstance(c, dict) and c.get("id")]


def _admit_evidence(case: Mapping[str, Any]) -> List[str]:
    """Admit required evidence ids as durable records; return admitted ids."""
    admitted: List[str] = []
    for eid in case.get("required_evidence_ids") or []:
        rid = f"mem_{eid}"
        row = admit(
            {
                "id": rid,
                "memory_type": "semantic",
                "content": f"Fixture evidence for {eid}: {case.get('task', '')}",
                "provenance": {
                    "source_type": "document",
                    "source_id": f"fixture:{case.get('id')}/{eid}",
                    "captured_by": "continuity_bench",
                },
                "confidence": 0.95,
                "evidence_status": "verified",
                "emotion": neutral_emotion(),
                "privacy_class": "internal",
                "observed_at": "2026-08-21T00:00:00+00:00",
                "recorded_at": "2026-08-21T00:00:00+00:00",
                "deletion_path": f"aegis memory delete --id {rid}",
                "conflicts_with": [],
            },
            replace=True,
        )
        admitted.append(str(row["id"]))
    if case.get("id") == "conflict-preservation" and len(admitted) >= 2:
        add_conflict(admitted[0], admitted[1], reason="fixture contradictory regions")
    return admitted


def _baseline_capsule(case: Mapping[str, Any]) -> Dict[str, Any]:
    """Legacy handoff: verified capsule without sentinel fields or admitted memory."""
    verified = [f"Claimed {eid} from chat context" for eid in (case.get("required_evidence_ids") or [])]
    return state_capsule(
        objective=str(case.get("task") or "resume task"),
        verified=verified if verified else ["Task context assumed from prior chat"],
        next_action="Continue from chat history without reloading evidence",
        verification_status="verified",
    )


def _governed_capsule(case: Mapping[str, Any], admitted: Sequence[str]) -> Dict[str, Any]:
    """Sentinel v2 + evidence refs tied to admitted memory ids."""
    refs = [{"kind": "memory_record", "ref": mid} for mid in admitted]
    verified = [f"Admitted record {mid} present in memory_records.jsonl" for mid in admitted]
    signals = case.get("expected_signals") or []
    return state_capsule(
        objective=str(case.get("task") or "resume task"),
        verified=verified,
        next_action="Reload JIT pack and admitted memory records; do not replay broad history",
        verification_status="verified",
        owner="continuity_bench",
        privacy_class="internal",
        open_risks=[f"missing_signal:{s}" for s in signals if s],
        evidence_refs=refs,
        deletion_path="aegis memory delete + remove context capsule file",
    )


def _score_baseline(case: Mapping[str, Any], capsule: Mapping[str, Any]) -> CaseResult:
    failures: List[str] = []
    unsupported: List[str] = []

    for field in ("owner", "privacy_class", "recorded_at", "evidence_refs"):
        if field not in capsule:
            failures.append(f"missing_sentinel_field:{field}")

    known = {str(r.get("id")) for r in list_records(limit=500)}
    for eid in case.get("required_evidence_ids") or []:
        mid = f"mem_{eid}"
        if mid not in known:
            unsupported.append(f"required_evidence_not_admitted:{eid}")

    verified_text = " ".join(str(x) for x in (capsule.get("verified") or []))
    for fid in case.get("forbidden_evidence_ids") or []:
        if fid in verified_text:
            failures.append(f"forbidden_evidence_cited:{fid}")

    if "chat history" in str(capsule.get("next_action") or "").lower():
        failures.append("handoff_relies_on_chat_history")

    relay_linked = False
    passed = not failures and not unsupported
    return CaseResult(case["id"], failures, unsupported, relay_linked, passed)


def _score_governed(
    case: Mapping[str, Any],
    capsule: Mapping[str, Any],
    admitted: Sequence[str],
) -> CaseResult:
    failures: List[str] = []
    unsupported: List[str] = []

    for field in ("owner", "privacy_class", "recorded_at", "evidence_refs", "deletion_path"):
        if not capsule.get(field):
            failures.append(f"missing_sentinel_field:{field}")

    refs = capsule.get("evidence_refs") or []
    ref_ids = {str(r.get("ref")) for r in refs if isinstance(r, dict)}
    for mid in admitted:
        if mid not in ref_ids:
            failures.append(f"evidence_ref_missing:{mid}")

    known = {str(r.get("id")) for r in list_records(limit=500)}
    for mid in admitted:
        if mid not in known:
            unsupported.append(f"admitted_record_missing:{mid}")

    if case.get("id") == "conflict-preservation" and len(admitted) >= 2:
        rows = {str(r.get("id")): r for r in list_records(limit=500)}
        a, b = admitted[0], admitted[1]
        if b not in (rows.get(a) or {}).get("conflicts_with", []):
            failures.append("conflict_link_missing")

    fp = str(capsule.get("fingerprint") or "")
    relay_rows = query(source="continuity", kind="capsule", limit=50)
    relay_linked = any(str(r.get("fingerprint") or "") == fp for r in relay_rows)
    if not relay_linked:
        failures.append("relay_capsule_event_missing")

    verified_text = " ".join(str(x) for x in (capsule.get("verified") or []))
    for fid in case.get("forbidden_evidence_ids") or []:
        if fid in verified_text:
            failures.append(f"forbidden_evidence_cited:{fid}")

    passed = not failures and not unsupported
    return CaseResult(case["id"], failures, unsupported, relay_linked, passed)


def run_bench(cases_path: Path) -> Dict[str, Any]:
    cases = _load_cases(cases_path)
    baseline_results: List[CaseResult] = []
    governed_results: List[CaseResult] = []

    for case in cases:
        base_cap = _baseline_capsule(case)
        persist_capsule(base_cap)
        baseline_results.append(_score_baseline(case, base_cap))

        admitted = _admit_evidence(case)
        gov_cap = _governed_capsule(case, admitted)
        persist_capsule(gov_cap)
        governed_results.append(_score_governed(case, gov_cap, admitted))

    def _agg(results: Sequence[CaseResult]) -> Dict[str, Any]:
        return {
            "cases_total": len(results),
            "cases_passed": sum(1 for r in results if r.passed),
            "handoff_failures": sum(len(r.handoff_failures) for r in results),
            "unsupported_recalls": sum(len(r.unsupported_recalls) for r in results),
            "relay_linked_cases": sum(1 for r in results if r.relay_linked),
            "cases": [r.as_dict() for r in results],
        }

    base = _agg(baseline_results)
    gov = _agg(governed_results)
    return {
        "suite": "continuity-assurance-ab",
        "cases_path": str(cases_path),
        "baseline": base,
        "governed": gov,
        "delta": {
            "cases_passed": gov["cases_passed"] - base["cases_passed"],
            "handoff_failures": gov["handoff_failures"] - base["handoff_failures"],
            "unsupported_recalls": gov["unsupported_recalls"] - base["unsupported_recalls"],
            "relay_linked_cases": gov["relay_linked_cases"] - base["relay_linked_cases"],
            "pass_rate_baseline": round(base["cases_passed"] / max(1, base["cases_total"]), 3),
            "pass_rate_governed": round(gov["cases_passed"] / max(1, gov["cases_total"]), 3),
        },
    }
