"""Kotlin structure slice — fun/class/object/interface + package/import."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aegis.brace import brace_end, infer_from_task, match_target_names

_MOD = r"(?:(?:public|private|protected|internal|open|abstract|final|override|suspend|inline|data|sealed|inner|companion|const|lateinit|tailrec|operator|infix)\s+)*"
_TYPE = re.compile(
    rf"^{_MOD}(class|interface|object|enum\s+class|data\s+class|sealed\s+class|annotation\s+class)\s+(\w+)"
)
_FUN = re.compile(
    rf"^{_MOD}fun\s+(?:<[^>]+>\s+)?(?:[\w.]+\.)?(\w+)\s*(?:<[^>]*>)?\s*\("
)
_FUN_RECV = re.compile(
    rf"^{_MOD}fun\s+([\w.<>?]+)\.(\w+)\s*\("
)
_SKIP = frozenset({"if", "for", "while", "when", "catch", "return", "throw"})


def extract_imports_kotlin(source: str) -> List[str]:
    out: List[str] = []
    for line in source.splitlines():
        s = line.strip()
        if s.startswith("package ") or s.startswith("import "):
            out.append(line.rstrip())
    return out


def extract_kotlin_units(source: str) -> List[Dict[str, Any]]:
    lines = source.splitlines()
    units: List[Dict[str, Any]] = []
    i = 0
    stack: List[Tuple[str, int]] = []

    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if (
            not s
            or s.startswith("//")
            or s.startswith("/*")
            or s.startswith("*")
            or s.startswith("@")
        ):
            i += 1
            continue

        while stack and i + 1 > stack[-1][1]:
            stack.pop()

        m_type = _TYPE.match(s)
        if m_type:
            kind = re.sub(r"\s+", "_", m_type.group(1))
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

        m_recv = _FUN_RECV.match(s)
        m_fun = _FUN.match(s)
        if m_recv or m_fun:
            if m_recv:
                name = m_recv.group(2)
                qn_base = name
            else:
                name = m_fun.group(1)
                qn_base = name
            if name in _SKIP:
                i += 1
                continue
            parent = stack[-1][0] if stack else ""
            qn = f"{parent}.{qn_base}" if parent else qn_base
            start = i + 1
            if s.rstrip().endswith("=") or ("=" in s and "{" not in s and s.rstrip().endswith(")")):
                # single-expression fun next line or same
                end = start if "{" not in s else brace_end(lines, i)
                if "{" not in s and i + 1 < len(lines) and not lines[i + 1].strip().startswith("fun"):
                    # expression body one line
                    end = i + 2 if i + 1 < len(lines) else start
            else:
                end = brace_end(lines, i)
            units.append(
                {
                    "name": name,
                    "qualname": qn,
                    "kind": "fun",
                    "start": start,
                    "end": end,
                    "sig_line": raw.rstrip(),
                }
            )
            i = max(end, i + 1)
            continue

        i += 1
    return units


def build_explore_kotlin(source: str) -> str:
    units = extract_kotlin_units(source)
    imports = extract_imports_kotlin(source)
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


def build_implement_kotlin(
    source: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Tuple[str, Dict[str, Any]]:
    lines = source.splitlines()
    units = extract_kotlin_units(source)
    meta: Dict[str, Any] = {
        "units": len(units),
        "targets_requested": list(targets or []),
        "targets_resolved": [],
        "fidelity": "full_file",
        "lang": "kotlin",
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
    imports = extract_imports_kotlin(source)
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


def build_review_kotlin(source: str) -> str:
    if source.lstrip().startswith("diff ") or "\n@@" in source:
        return source
    return build_explore_kotlin(source)
