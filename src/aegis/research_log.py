"""Deterministic research-log validator. No LLM. Fail-closed.

Parses flat Hermes frontmatter via parse_frontmatter. Nested blind-spot
objects belong in the body. Does not authorize routing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from aegis.hermes_notes import HEADING_RE, parse_frontmatter, parse_wikilinks, _note_body

NOTE_TYPES = frozenset(
    {
        "aegis-research-protocol",
        "aegis-research-record",
        "aegis-blind-spot-register",
        "aegis-utility-fix",
        "aegis-experiment-report",
        "aegis-research-decision",
    }
)
DOMAINS = frozenset(
    {"capability", "economics", "governance", "memory", "reliability", "safety"}
)
DECISIONS = frozenset({"investigate", "adopt", "defer", "reject", "hold"})
RELEVANCE = frozenset({"low", "medium", "high", "critical"})
CONFIDENCE = frozenset({"low", "medium", "high"})
COMMON_KEYS = (
    "type",
    "id",
    "status",
    "date_created",
    "owner",
    "domain",
    "decision_relevance",
    "evidence_grade",
    "utility_grade",
    "risk_grade",
    "blind_spot_count",
    "confidence",
    "decision",
    "related",
    "sources",
    "limitations",
    "canonical",
    "project",
    "tags",
    "title",
)
REQUIRED_HEADERS = (
    "Question",
    "Why it matters",
    "Hypothesis",
    "Evidence table",
    "Competing explanations",
    "Claims",
    "Assumptions",
    "Observed failures",
    "Blind spots",
    "Proposed intervention",
    "Experiment design",
    "Results",
    "Decision",
    "Rollback",
    "Follow-up date",
    "Facts",
    "Inferences",
    "Recommendations",
)
VERIFY_COST_KEYS = ("audited_runs", "gaps_found", "trustworthy_for_routing")
JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S | re.I)
BS_ID_RE = re.compile(r"\bid:\s*BS-\d+", re.I)
ROUTING_TRUE_RE = re.compile(
    r"routing_authorized\s*[\"']?\s*[:=]\s*[\"']?true\b", re.I
)

RESEARCH_FILENAMES = (
    "Aegis Research Log Protocol.md",
    "Aegis Blind-Spot Register.md",
    "Aegis Utility-Fix Proposal.md",
    "Aegis Pilot Experiment Report.md",
    "Aegis Research Log Decision Record.md",
    "Aegis RR-2026-08-001 Cost Trust Window.md",
    "Aegis RR-2026-08-002 Untrusted Cost Sources.md",
    "Aegis RR-2026-08-003 Utility Cannot Override Provenance.md",
)


def coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text or not re.fullmatch(r"-?\d+", text):
        return None
    return int(text)


def headings(body: str) -> List[str]:
    names: List[str] = []
    for line in (body or "").splitlines():
        match = HEADING_RE.match(line.strip())
        if match:
            names.append(match.group(1).strip())
    return names


def has_header(names: Sequence[str], required: str) -> bool:
    needle = required.lower()
    for name in names:
        lowered = name.lower()
        if lowered == needle or lowered.startswith(needle + " ") or lowered.startswith(needle + ":"):
            return True
    return False


def extract_json_objects(body: str) -> List[Dict[str, Any]]:
    found: List[Dict[str, Any]] = []
    for blob in JSON_FENCE_RE.findall(body or ""):
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            found.append(payload)
    return found


def verify_cost_excerpt(body: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    matches = [
        obj for obj in extract_json_objects(body)
        if all(key in obj for key in VERIFY_COST_KEYS)
    ]
    if not matches:
        return None, ["missing verify-cost excerpt (audited_runs, gaps_found, trustworthy_for_routing)"]
    excerpt = matches[0]
    path = str(excerpt.get("outcomes_path") or "")
    if "outcomes.jsonl" not in path:
        errors.append("verify-cost excerpt missing outcomes.jsonl path")
    if not str(excerpt.get("captured_at") or "").strip():
        errors.append("verify-cost excerpt missing captured_at")
    return excerpt, errors


def _nonempty_list(meta: Dict[str, Any], key: str) -> bool:
    value = meta.get(key)
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    if isinstance(value, str):
        return bool(value.strip())
    return False


def _frontmatter_errors(meta: Dict[str, Any], *, require_question: bool) -> List[str]:
    errors: List[str] = []
    for key in COMMON_KEYS:
        if key not in meta:
            errors.append(f"missing frontmatter key: {key}")
    note_type = str(meta.get("type") or "")
    if note_type not in NOTE_TYPES:
        errors.append(f"invalid type: {note_type}")
    if str(meta.get("domain") or "") not in DOMAINS:
        errors.append(f"invalid domain: {meta.get('domain')}")
    if str(meta.get("decision") or "") not in DECISIONS:
        errors.append(f"invalid decision: {meta.get('decision')}")
    if str(meta.get("decision_relevance") or "") not in RELEVANCE:
        errors.append(f"invalid decision_relevance: {meta.get('decision_relevance')}")
    if str(meta.get("confidence") or "") not in CONFIDENCE:
        errors.append(f"invalid confidence: {meta.get('confidence')}")
    if not str(meta.get("id") or "").strip():
        errors.append("empty id")
    if not str(meta.get("limitations") or "").strip():
        errors.append("empty limitations")
    if not _nonempty_list(meta, "sources"):
        errors.append("empty sources")
    if not _nonempty_list(meta, "related"):
        errors.append("empty related")
    if not _nonempty_list(meta, "tags"):
        errors.append("empty tags")
    tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    if "memory-utility-labs" not in tags or "hermes" not in tags:
        errors.append("tags must include memory-utility-labs and hermes")
    if str(meta.get("project") or "") != "aegis":
        errors.append("project must be aegis")
    if meta.get("canonical") is not False:
        errors.append("canonical must be false")
    if require_question and not str(meta.get("question") or "").strip():
        errors.append("research record missing question")
    grades: Dict[str, Optional[int]] = {}
    for key in ("evidence_grade", "utility_grade", "risk_grade", "blind_spot_count"):
        grades[key] = coerce_int(meta.get(key))
        if grades[key] is None:
            errors.append(f"{key} is not an integer")
        elif key == "blind_spot_count":
            if grades[key] < 0:
                errors.append("blind_spot_count must be >= 0")
        elif grades[key] < 0 or grades[key] > 5:
            errors.append(f"{key} out of range 0-5")
    return errors


def _header_errors(body: str) -> List[str]:
    names = headings(body)
    return [f"missing header: {required}" for required in REQUIRED_HEADERS if not has_header(names, required)]


def _rubric(meta: Dict[str, Any], body: str, excerpt: Optional[Dict[str, Any]], errors: Sequence[str]) -> Dict[str, bool]:
    names = headings(body)
    links = parse_wikilinks(body)
    note_type = str(meta.get("type") or "")
    mission = str(meta.get("domain") or "") in DOMAINS and note_type in NOTE_TYPES
    evidence = (
        _nonempty_list(meta, "sources")
        and bool(str(meta.get("limitations") or "").strip())
        and (
            excerpt is not None
            if note_type in {"aegis-research-record", "aegis-utility-fix", "aegis-experiment-report"}
            else True
        )
    )
    claims = all(has_header(names, name) for name in ("Facts", "Inferences", "Recommendations"))
    coverage = all(
        has_header(names, name)
        for name in ("Evidence table", "Observed failures", "Results")
    )
    blind = has_header(names, "Blind spots") and has_header(names, "Competing explanations")
    if note_type == "aegis-blind-spot-register":
        blind = blind and len(BS_ID_RE.findall(body)) >= 5
    utility = has_header(names, "Proposed intervention") and coerce_int(meta.get("utility_grade")) is not None
    reversibility = has_header(names, "Rollback") and "rollback" in body.lower()
    governance = (
        ("fail-closed" in body.lower() or "fail closed" in body.lower())
        and not ROUTING_TRUE_RE.search(body)
    )
    validation = _nonempty_list(meta, "sources")
    persistence = _nonempty_list(meta, "related") and bool(links)
    return {
        "mission_fit": mission,
        "evidence_completeness": evidence and "empty limitations" not in errors,
        "claim_separation": claims,
        "log_coverage": coverage,
        "blind_spot_review": blind,
        "utility_definition": utility,
        "reversibility": reversibility,
        "governance": governance,
        "validation": validation,
        "persistence": persistence,
    }


def validate_note(text: str, *, relpath: str = "") -> Dict[str, Any]:
    meta = parse_frontmatter(text)
    body = _note_body(text)
    note_type = str(meta.get("type") or "")
    require_question = note_type == "aegis-research-record"
    errors = _frontmatter_errors(meta, require_question=require_question)
    errors.extend(_header_errors(body))
    excerpt = None
    needs_excerpt = note_type in {
        "aegis-research-record",
        "aegis-utility-fix",
        "aegis-experiment-report",
    }
    if needs_excerpt:
        excerpt, excerpt_errors = verify_cost_excerpt(body)
        errors.extend(excerpt_errors)
    if note_type == "aegis-research-record" and "RR-2026-08" not in str(meta.get("id") or ""):
        errors.append("research record id must contain RR-YYYY-MM")
    if note_type == "aegis-blind-spot-register" and len(BS_ID_RE.findall(body)) < 5:
        errors.append("blind-spot register requires at least five BS- ids")
    if note_type == "aegis-utility-fix":
        if "[[Aegis RR-" not in body and "RR-2026-08" not in body:
            errors.append("utility fix must link to an observed research record")
    if note_type == "aegis-experiment-report":
        objects = extract_json_objects(body)
        labeled = sum(
            1
            for obj in objects
            if obj.get("role") in {"baseline", "treatment"} and all(k in obj for k in VERIFY_COST_KEYS)
        )
        if labeled < 2:
            errors.append("experiment report requires baseline and treatment verify-cost JSON")
    evidence = coerce_int(meta.get("evidence_grade"))
    utility = coerce_int(meta.get("utility_grade"))
    risk = coerce_int(meta.get("risk_grade"))
    decision = str(meta.get("decision") or "")
    if decision == "adopt":
        for label, grade in (("evidence_grade", evidence), ("utility_grade", utility), ("risk_grade", risk)):
            if grade is None or grade < 3:
                errors.append(f"adopt requires {label} >= 3")
        if needs_excerpt and excerpt is None:
            errors.append("adopt requires a live verify-cost excerpt")
    if ROUTING_TRUE_RE.search(body):
        errors.append("research log must not claim routing_authorized=true")
    if excerpt and excerpt.get("trustworthy_for_routing") is True and "eligible for routing" in body.lower():
        errors.append("must not treat a research note as routing authorization")
    rubric = _rubric(meta, body, excerpt, errors)
    passed = sum(1 for ok in rubric.values() if ok)
    return {
        "ok": not errors,
        "relpath": relpath,
        "id": str(meta.get("id") or ""),
        "type": note_type,
        "errors": errors,
        "grades": {
            "evidence": evidence,
            "utility": utility,
            "risk": risk,
        },
        "decision": decision,
        "excerpt": excerpt,
        "rubric": rubric,
        "rubric_pass_count": passed,
        "rubric_total": len(rubric),
        "wikilinks": parse_wikilinks(body),
    }


def validate_path(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return validate_note(text, relpath=str(path.name))


def validate_corpus(root: str, expected: Iterable[str] = RESEARCH_FILENAMES) -> Dict[str, Any]:
    base = Path(root).expanduser()
    reports = []
    missing = []
    for name in expected:
        path = base / name
        if not path.is_file():
            missing.append(name)
            continue
        reports.append(validate_path(path))
    errors = list(missing)
    for report in reports:
        errors.extend(f"{report['relpath']}: {item}" for item in report["errors"])
    return {
        "ok": not errors,
        "root": str(base),
        "missing": missing,
        "reports": reports,
        "errors": errors,
        "checked": len(reports),
        "expected": len(list(expected)),
    }
