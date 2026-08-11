"""Java structure slice — class/method/interface/enum + package/import."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aegis.brace import brace_end, infer_from_task, match_target_names

_MOD = r"(?:(?:public|private|protected|static|final|abstract|synchronized|native|default|strictfp)\s+)*"
_TYPE = re.compile(
    rf"^{_MOD}(class|interface|enum|record)\s+(\w+)"
)
# method or constructor: skip if starts with class/interface/enum/record
_METHOD = re.compile(
    rf"^{_MOD}(?:<[^>]+>\s+)?"
    r"(?:[\w.<>\[\],\s\?]+\s+)?"
    r"(\w+)\s*\("
)
_SKIP_METHOD_NAMES = frozenset(
    {"if", "for", "while", "switch", "catch", "synchronized", "return", "new", "throw"}
)


def extract_imports_java(source: str) -> List[str]:
    out: List[str] = []
    for line in source.splitlines():
        s = line.strip()
        if s.startswith("package ") or s.startswith("import "):
            out.append(line.rstrip())
    return out


def extract_java_units(source: str) -> List[Dict[str, Any]]:
    lines = source.splitlines()
    units: List[Dict[str, Any]] = []
    i = 0
    # stack of (class_name, end_line_1based)
    stack: List[Tuple[str, int]] = []

    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if not s or s.startswith("//") or s.startswith("/*") or s.startswith("*") or s.startswith("@"):
            i += 1
            continue

        # pop finished outer types
        while stack and i + 1 > stack[-1][1]:
            stack.pop()

        m_type = _TYPE.match(s)
        if m_type:
            kind = m_type.group(1)
            name = m_type.group(2)
            parent = stack[-1][0] if stack else ""
            qn = f"{parent}.{name}" if parent else name
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
            stack.append((qn, end))
            i += 1
            continue

        m_meth = _METHOD.match(s)
        if m_meth and not s.startswith("package ") and not s.startswith("import "):
            name = m_meth.group(1)
            if name not in _SKIP_METHOD_NAMES and not _TYPE.match(s):
                # reject field-like if no ( is method - we require (
                parent = stack[-1][0] if stack else ""
                qn = f"{parent}.{name}" if parent else name
                start = i + 1
                end = brace_end(lines, i)
                # one-liner abstract/interface methods end with ;
                if s.rstrip().endswith(";") and "{" not in s:
                    end = start
                units.append(
                    {
                        "name": name,
                        "qualname": qn,
                        "kind": "method",
                        "start": start,
                        "end": end,
                        "sig_line": raw.rstrip(),
                    }
                )
                i = max(end, i + 1)
                continue

        i += 1
    return units


def build_explore_java(source: str) -> str:
    units = extract_java_units(source)
    imports = extract_imports_java(source)
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


def build_implement_java(
    source: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Tuple[str, Dict[str, Any]]:
    lines = source.splitlines()
    units = extract_java_units(source)
    meta: Dict[str, Any] = {
        "units": len(units),
        "targets_requested": list(targets or []),
        "targets_resolved": [],
        "fidelity": "full_file",
        "lang": "java",
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
    imports = extract_imports_java(source)
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


def build_review_java(source: str) -> str:
    if source.lstrip().startswith("diff ") or "\n@@" in source:
        return source
    return build_explore_java(source)
