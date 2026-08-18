"""Deterministic research-log validator. No LLM. Live MUL optional."""

from pathlib import Path

import pytest

from aegis.research_log import (
    RESEARCH_FILENAMES,
    validate_corpus,
    validate_note,
)

MUL_ROOT = Path(
    "/Users/a100/Library/Mobile Documents/iCloud~md~obsidian/Documents/AGIS"
    "/AEGIS/05-Memory-Utility-Labs"
)

HEADERS = """
## Question
q
## Why it matters
m
## Hypothesis
h
## Evidence table
t
## Competing explanations
c
## Claims
cl
## Assumptions
a
## Observed failures
o
## Blind spots
b
## Proposed intervention
p
## Experiment design
e
## Results
r
## Decision
d
## Rollback
rollback fail-closed
## Follow-up date
2026-09-01
## Facts
f
## Inferences
i
## Recommendations
rec
"""

EXCERPT = """
```json
{"role": "baseline", "captured_at": "2026-08-18T21:16:23Z", "outcomes_path": "/Users/a100/.aegis/outcomes.jsonl", "audited_runs": 5, "gaps_found": 4, "trustworthy_for_routing": false}
```
"""


def _note(*, ntype="aegis-research-record", decision="hold", e=4, u=3, r=5, extra="", question="Is live cost trusted?", nid="RR-2026-08-009"):
    return f"""---
title: Fixture
type: {ntype}
id: {nid}
status: completed
date_created: 2026-08-18
owner: user
domain: economics
question: "{question}"
decision_relevance: high
evidence_grade: {e}
utility_grade: {u}
risk_grade: {r}
blind_spot_count: 1
confidence: high
decision: {decision}
project: aegis
tags:
  - memory-utility-labs
  - hermes
sources:
  - src/aegis/outcomes.py
related:
  - Aegis Research Log Protocol
limitations: Fixture is not live evidence.
canonical: false
---
# Fixture
Related research: [[Aegis RR-2026-08-001 Cost Trust Window]]
{HEADERS}
{EXCERPT}
{extra}
"""


def test_valid_record_passes():
    report = validate_note(_note())
    assert report["ok"] is True
    assert report["errors"] == []
    assert report["grades"] == {"evidence": 4, "utility": 3, "risk": 5}
    assert report["rubric_pass_count"] == report["rubric_total"] == 10


def test_missing_limitations_fails():
    text = _note().replace("limitations: Fixture is not live evidence.\n", "")
    report = validate_note(text)
    assert report["ok"] is False
    assert any("limitations" in err for err in report["errors"])


def test_grade_out_of_range_fails():
    report = validate_note(_note(e=6))
    assert report["ok"] is False
    assert any("evidence_grade out of range" in err for err in report["errors"])


def test_adopt_requires_grades_and_excerpt():
    report = validate_note(_note(decision="adopt", e=2, u=3, r=5))
    assert report["ok"] is False
    assert any("evidence_grade >= 3" in err for err in report["errors"])
    stripped = _note(decision="hold").replace(EXCERPT, "")
    report = validate_note(stripped)
    assert report["ok"] is False
    assert any("verify-cost excerpt" in err for err in report["errors"])


def test_routing_authorized_true_is_rejected():
    report = validate_note(_note(extra='claim routing_authorized=true'))
    assert report["ok"] is False
    assert any("routing_authorized" in err for err in report["errors"])


def test_utility_fix_must_link_record():
    text = _note(ntype="aegis-utility-fix", nid="UF-009", decision="adopt")
    text = text.replace("[[Aegis RR-2026-08-001 Cost Trust Window]]", "[[Memory Utility Labs]]")
    text = text.replace("id: UF-009", "id: UF-009\n")
    report = validate_note(text)
    assert report["ok"] is False
    assert any("observed research record" in err for err in report["errors"])


def test_experiment_requires_baseline_and_treatment():
    report = validate_note(_note(ntype="aegis-experiment-report", nid="EXP-2026-08-009", decision="adopt"))
    assert report["ok"] is False
    assert any("baseline and treatment" in err for err in report["errors"])
    extra = """
```json
{"role": "treatment", "captured_at": "2026-08-18T21:18:53Z", "outcomes_path": "/Users/a100/.aegis/outcomes.jsonl", "audited_runs": 5, "gaps_found": 4, "trustworthy_for_routing": false}
```
"""
    report = validate_note(_note(ntype="aegis-experiment-report", nid="EXP-2026-08-009", decision="adopt", extra=extra))
    assert report["ok"] is True


def test_blind_spot_register_requires_five_ids():
    body = _note(ntype="aegis-blind-spot-register", nid="BS-REGISTER-009", decision="hold")
    report = validate_note(body)
    assert report["ok"] is False
    assert any("five BS-" in err for err in report["errors"])
    ids = "\n".join(f"id: BS-00{i}" for i in range(1, 6))
    report = validate_note(_note(ntype="aegis-blind-spot-register", nid="BS-REGISTER-009", decision="hold", extra=ids))
    assert report["ok"] is True


@pytest.mark.skipif(not MUL_ROOT.is_dir(), reason="AGIS MUL missing")
def test_live_mul_research_cluster_validates():
    for name in RESEARCH_FILENAMES:
        assert (MUL_ROOT / name).is_file(), name
    out = validate_corpus(str(MUL_ROOT))
    assert out["missing"] == []
    assert out["ok"] is True, out["errors"]
    for report in out["reports"]:
        assert report["rubric_pass_count"] >= 8
        assert report["excerpt"] is None or report["excerpt"]["trustworthy_for_routing"] is False
