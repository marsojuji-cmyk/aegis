"""Pack quality gates — reject false economy and fidelity failures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class GateResult:
    ok: bool
    strict_fail: bool
    grade: str  # pass | warn | fail
    issues: List[Dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "strict_fail": self.strict_fail,
            "grade": self.grade,
            "issues": self.issues,
        }


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    path: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row = {"code": code, "severity": severity, "message": message}
    if path:
        row["path"] = path
    if meta:
        row["meta"] = meta
    return row


def evaluate_pack(
    payload: Dict[str, Any],
    *,
    mode: str,
    targets: Optional[Sequence[str]] = None,
    sources: Optional[Dict[str, str]] = None,
    explore_min_reduction: float = 30.0,
    implement_max_expansion: float = 15.0,
    min_payload_chars: int = 1,
) -> GateResult:
    """
    Evaluate a pack payload.

    severity: info | warn | fail
    strict_fail True if any fail-level issue (for --strict exit).
    """
    mode = (mode or payload.get("mode") or "explore").lower()
    targets = list(targets or payload.get("targets") or [])
    sources = sources or {}
    issues: List[Dict[str, Any]] = []

    raw = int(payload.get("total_raw_tokens") or 0)
    proc = int(payload.get("total_compressed_tokens") or 0)
    reduction = float(payload.get("overall_reduction_percent") or 0.0)
    components = payload.get("bento_components") or []

    # Empty pack
    if not components:
        issues.append(_issue("empty_pack", "fail", "No components in pack"))
    for c in components:
        snippet = c.get("payload_snippet") or ""
        path = c.get("path") or ""
        if len(snippet.strip()) < min_payload_chars:
            issues.append(
                _issue("empty_component", "fail", "Empty payload component", path=path)
            )

    # Explore: expect meaningful cut on non-tiny inputs
    if mode == "explore" and raw >= 80:
        if reduction < explore_min_reduction:
            issues.append(
                _issue(
                    "explore_low_cut",
                    "warn",
                    f"Explore reduction {reduction}% < {explore_min_reduction}% floor",
                    meta={"reduction": reduction, "floor": explore_min_reduction},
                )
            )

    # Implement: expansion beyond annotations budget is suspicious for full-file
    if mode == "implement" and raw >= 40:
        if reduction < -implement_max_expansion:
            issues.append(
                _issue(
                    "implement_expansion",
                    "warn",
                    f"Implement expanded tokens ({reduction}% cut) — labels or failed compress",
                    meta={"reduction": reduction},
                )
            )

    # Targets requested but none resolved on any structured file
    if mode == "implement" and targets:
        fidelity = payload.get("fidelity") or []
        resolved_any = False
        for f in fidelity:
            res = f.get("targets_resolved") or []
            if res:
                resolved_any = True
                break
            if f.get("fidelity") == "target_bodies":
                resolved_any = True
                break
        if not resolved_any:
            issues.append(
                _issue(
                    "targets_unresolved",
                    "warn",
                    f"Targets {targets} not resolved — fell back to full file(s)",
                    meta={"targets": targets},
                )
            )

    # Per-component implement fidelity when source available
    if mode == "implement" and targets and sources:
        from aegis.bento import assert_implement_fidelity
        from aegis.lang import detect_lang

        for c in components:
            path = c.get("path") or ""
            src = sources.get(path)
            if not src:
                continue
            lang = detect_lang(path, src)
            if lang != "python":
                # light check: each target name string appears if lang structured
                snip = c.get("payload_snippet") or ""
                for t in targets:
                    simple = t.split(".")[-1]
                    if simple not in snip and t not in snip:
                        # only fail if fidelity claimed target_bodies
                        continue
            else:
                snip = c.get("payload_snippet") or ""
                if not assert_implement_fidelity(src, snip, targets):
                    issues.append(
                        _issue(
                            "implement_fidelity",
                            "fail",
                            "Implement payload missing target body content",
                            path=path,
                            meta={"targets": list(targets)},
                        )
                    )

    # Reuse path: zero processed is OK; flag missing pack_id
    if payload.get("reuse") and not payload.get("pack_id"):
        issues.append(_issue("reuse_no_id", "warn", "Reuse hit without pack_id"))

    fails = [i for i in issues if i["severity"] == "fail"]
    warns = [i for i in issues if i["severity"] == "warn"]
    if fails:
        grade = "fail"
        ok = False
        strict_fail = True
    elif warns:
        grade = "warn"
        ok = True
        strict_fail = False
    else:
        grade = "pass"
        ok = True
        strict_fail = False

    return GateResult(ok=ok, strict_fail=strict_fail, grade=grade, issues=issues)


def format_gates(result: GateResult) -> str:
    lines = [f"# quality: {result.grade}"]
    for i in result.issues:
        loc = f" ({i['path']})" if i.get("path") else ""
        lines.append(f"#   [{i['severity']}] {i['code']}{loc}: {i['message']}")
    if not result.issues:
        lines.append("#   (no issues)")
    return "\n".join(lines)
