"""Python AST slicing — signatures vs full bodies (E2 fidelity)."""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


def _line_span(node: ast.AST) -> Tuple[int, int]:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", None) or start
    return start, end


def _decorators_start(node: ast.AST) -> int:
    decos = getattr(node, "decorator_list", None) or []
    if not decos:
        return getattr(node, "lineno", 1)
    return min(getattr(d, "lineno", node.lineno) for d in decos)


def _sig_line(source_lines: List[str], node: ast.AST) -> str:
    """First line of def/class including decorators start."""
    start = _decorators_start(node)
    idx = max(0, start - 1)
    if idx < len(source_lines):
        return source_lines[idx].rstrip()
    return ""


def _slice_lines(source_lines: List[str], start: int, end: int) -> str:
    start = max(1, start)
    end = min(len(source_lines), end)
    if start > end:
        return ""
    return "\n".join(source_lines[start - 1 : end])


def _qualname(parent_stack: List[str], name: str) -> str:
    return ".".join(parent_stack + [name]) if parent_stack else name


def extract_python_units(source: str) -> List[Dict[str, Any]]:
    """
    Return top-level and nested functions/classes with spans.
    Each unit: name, qualname, kind, start, end, sig_line
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    units: List[Dict[str, Any]] = []

    def walk(node: ast.AST, stack: List[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = child.name
                qn = _qualname(stack, name)
                start = _decorators_start(child)
                _, end = _line_span(child)
                kind = (
                    "class"
                    if isinstance(child, ast.ClassDef)
                    else ("async_def" if isinstance(child, ast.AsyncFunctionDef) else "def")
                )
                units.append(
                    {
                        "name": name,
                        "qualname": qn,
                        "kind": kind,
                        "start": start,
                        "end": end,
                        "sig_line": _sig_line(lines, child),
                    }
                )
                walk(child, stack + [name])
            else:
                walk(child, stack)

    walk(tree, [])
    return units


def extract_imports(source: str) -> List[str]:
    lines = source.splitlines()
    out: List[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        for line in lines:
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                out.append(line.rstrip())
        return out

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            start, end = _line_span(node)
            out.append(_slice_lines(lines, start, end))
    return out


def match_targets(units: List[Dict[str, Any]], targets: Sequence[str]) -> Set[str]:
    """Match target names against unit name or qualname (case-sensitive, then lower)."""
    if not targets:
        return set()
    wanted = {t.strip() for t in targets if t and t.strip()}
    matched: Set[str] = set()
    for u in units:
        qn = u["qualname"]
        name = u["name"]
        for t in wanted:
            if t == qn or t == name or t.lower() == qn.lower() or t.lower() == name.lower():
                matched.add(qn)
            # task-like substring
            elif t in qn or t in name:
                matched.add(qn)
    return matched


def infer_targets_from_task(task: str, units: List[Dict[str, Any]]) -> Set[str]:
    """If task mentions a def/class name, select those units."""
    if not task or not units:
        return set()
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", task))
    matched: Set[str] = set()
    for u in units:
        if u["name"] in tokens or u["qualname"] in tokens:
            matched.add(u["qualname"])
    return matched


def build_explore_payload(source: str) -> str:
    """Signatures + imports only."""
    units = extract_python_units(source)
    imports = extract_imports(source)
    parts: List[str] = []
    if imports:
        parts.append("# imports")
        parts.extend(imports)
    if units:
        parts.append("# signatures")
        for u in units:
            parts.append(f"{u['sig_line']}  # {u['qualname']} L{u['start']}-{u['end']}")
    if not parts:
        # non-python or empty: light head
        lines = [ln for ln in source.splitlines() if ln.strip()][:40]
        return "\n".join(lines)
    return "\n".join(parts)


def build_implement_payload(
    source: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """
    Full bodies for target symbols; signatures for neighbors.
    If no targets resolved: full source (scrubbed externally) for fidelity.
    """
    lines = source.splitlines()
    units = extract_python_units(source)
    meta: Dict[str, Any] = {
        "units": len(units),
        "targets_requested": list(targets or []),
        "targets_resolved": [],
        "fidelity": "full_file",
    }

    if not units:
        # cannot AST-slice — return full source for implement safety
        return source, meta

    resolved = match_targets(units, targets or [])
    if not resolved:
        resolved = infer_targets_from_task(task, units)
    if not resolved:
        # No symbols named — implement on whole file = full body fidelity
        meta["fidelity"] = "full_file"
        return source, meta

    meta["targets_resolved"] = sorted(resolved)
    meta["fidelity"] = "target_bodies"

    imports = extract_imports(source)
    parts: List[str] = []
    if imports:
        parts.append("# imports")
        parts.extend(imports)

    # Neighbors: signatures only
    neighbors = [u for u in units if u["qualname"] not in resolved]
    if neighbors:
        parts.append("# neighbor signatures")
        for u in neighbors:
            parts.append(f"{u['sig_line']}  # {u['qualname']}")

    parts.append("# implement targets (full bodies)")
    # Sort by start line; avoid double-including nested if parent also selected
    selected = [u for u in units if u["qualname"] in resolved]
    selected.sort(key=lambda u: u["start"])

    # Drop nested unit if parent body already includes it
    filtered: List[Dict[str, Any]] = []
    for u in selected:
        nested_in_parent = False
        for p in filtered:
            if u["start"] >= p["start"] and u["end"] <= p["end"] and u["qualname"] != p["qualname"]:
                nested_in_parent = True
                break
        if not nested_in_parent:
            filtered.append(u)

    for u in filtered:
        parts.append(f"# --- {u['qualname']} L{u['start']}-{u['end']} ---")
        parts.append(_slice_lines(lines, u["start"], u["end"]))

    return "\n".join(parts), meta


def build_review_payload(source: str) -> str:
    """Prefer keeping diff hunks; else explore-style + short body previews."""
    if source.lstrip().startswith("diff ") or "\n@@" in source or source.lstrip().startswith("--- "):
        return source
    # Light: imports + signatures + up to 80 non-empty body lines from first units
    base = build_explore_payload(source)
    units = extract_python_units(source)
    lines = source.splitlines()
    extra: List[str] = []
    budget = 80
    for u in units[:5]:
        chunk = _slice_lines(lines, u["start"], min(u["end"], u["start"] + 15))
        extra.append(chunk)
        budget -= len(chunk.splitlines())
        if budget <= 0:
            break
    if extra:
        return base + "\n# review previews\n" + "\n".join(extra)
    return base
