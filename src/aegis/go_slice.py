"""Go structure slice — func / type / method (regex + brace match)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aegis.brace import brace_end, infer_from_task, match_target_names

# func Name / func (recv T) Name / type Name struct|interface|...
_FUNC = re.compile(
    r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\("
)
_TYPE = re.compile(
    r"^type\s+(\w+)\s+"
)
_METHOD_RECV = re.compile(
    r"^func\s+\((\w+)\s+\*?(\w+)\)\s+(\w+)\s*\("
)


def extract_imports_go(source: str) -> List[str]:
    lines = source.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("package "):
            out.append(lines[i].rstrip())
        elif s == "import (" or s.startswith("import ("):
            start = i
            while i < len(lines) and ")" not in lines[i]:
                i += 1
            out.extend(ln.rstrip() for ln in lines[start : i + 1])
        elif s.startswith("import "):
            out.append(lines[i].rstrip())
        i += 1
    return out


def extract_go_units(source: str) -> List[Dict[str, Any]]:
    lines = source.splitlines()
    units: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        # skip comments
        if s.startswith("//") or s.startswith("/*"):
            i += 1
            continue

        m_recv = _METHOD_RECV.match(s)
        m_func = _FUNC.match(s)
        m_type = _TYPE.match(s)

        if m_recv:
            recv_type = m_recv.group(2)
            name = m_recv.group(3)
            qn = f"{recv_type}.{name}"
            kind = "method"
        elif m_func:
            name = m_func.group(1)
            qn = name
            kind = "func"
        elif m_type:
            name = m_type.group(1)
            qn = name
            kind = "type"
        else:
            i += 1
            continue

        start = i + 1
        end = brace_end(lines, i)
        units.append(
            {
                "name": name,
                "qualname": qn,
                "kind": kind,
                "start": start,
                "end": end,
                "sig_line": raw.rstrip(),
            }
        )
        i = max(end, i + 1)
    return units


def build_explore_go(source: str) -> str:
    units = extract_go_units(source)
    imports = extract_imports_go(source)
    parts: List[str] = []
    if imports:
        parts.append("// package/imports")
        parts.extend(imports)
    if units:
        parts.append("// signatures")
        for u in units:
            parts.append(f"{u['sig_line']}  // {u['qualname']} L{u['start']}-{u['end']}")
    if not parts:
        return "\n".join(ln for ln in source.splitlines() if ln.strip())[:40]
    return "\n".join(parts)


def build_implement_go(
    source: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Tuple[str, Dict[str, Any]]:
    lines = source.splitlines()
    units = extract_go_units(source)
    meta: Dict[str, Any] = {
        "units": len(units),
        "targets_requested": list(targets or []),
        "targets_resolved": [],
        "fidelity": "full_file",
        "lang": "go",
    }
    if not units:
        return source, meta

    resolved = match_target_names(units, targets or [])
    if not resolved:
        resolved = infer_from_task(task, units)
    if not resolved:
        meta["fidelity"] = "full_file"
        return source, meta

    meta["targets_resolved"] = sorted(resolved)
    meta["fidelity"] = "target_bodies"
    imports = extract_imports_go(source)
    parts: List[str] = []
    if imports:
        parts.append("// package/imports")
        parts.extend(imports)
    neighbors = [u for u in units if u["qualname"] not in resolved]
    if neighbors:
        parts.append("// neighbor signatures")
        for u in neighbors:
            parts.append(f"{u['sig_line']}  // {u['qualname']}")
    parts.append("// implement targets (full bodies)")
    for u in sorted((x for x in units if x["qualname"] in resolved), key=lambda x: x["start"]):
        parts.append(f"// --- {u['qualname']} L{u['start']}-{u['end']} ---")
        parts.append("\n".join(lines[u["start"] - 1 : u["end"]]))
    return "\n".join(parts), meta


def build_review_go(source: str) -> str:
    if source.lstrip().startswith("diff ") or "\n@@" in source:
        return source
    return build_explore_go(source)
