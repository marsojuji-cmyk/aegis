"""C# structure slice — class/method/interface/namespace + using."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aegis.brace import brace_end, infer_from_task, match_target_names

_MOD = (
    r"(?:(?:public|private|protected|internal|static|sealed|abstract|partial|"
    r"async|virtual|override|extern|unsafe|new|readonly|required)\s+)*"
)
_TYPE = re.compile(
    rf"^{_MOD}(class|interface|struct|enum|record(?:\s+class|\s+struct)?)\s+(\w+)"
)
_NAMESPACE = re.compile(r"^namespace\s+([\w.]+)")
_METHOD = re.compile(
    rf"^{_MOD}(?:[\w.<>\[\],\s\?]+\s+)?(\w+)\s*\("
)
_SKIP = frozenset(
    {
        "if",
        "for",
        "foreach",
        "while",
        "switch",
        "catch",
        "using",
        "lock",
        "fixed",
        "return",
        "typeof",
        "sizeof",
        "nameof",
    }
)


def extract_imports_csharp(source: str) -> List[str]:
    out: List[str] = []
    for line in source.splitlines():
        s = line.strip()
        if s.startswith("using ") or s.startswith("namespace "):
            out.append(line.rstrip())
            # file-scoped namespace ends with ;
            if s.startswith("namespace ") and s.endswith(";"):
                continue
    return out


def extract_csharp_units(source: str) -> List[Dict[str, Any]]:
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
            or s.startswith("[")  # attributes
            or s.startswith("#")
        ):
            i += 1
            continue

        while stack and i + 1 > stack[-1][1]:
            stack.pop()

        m_ns = _NAMESPACE.match(s)
        if m_ns:
            name = m_ns.group(1)
            start = i + 1
            if s.endswith(";"):
                # file-scoped — no brace body for namespace itself
                units.append(
                    {
                        "name": name.split(".")[-1],
                        "qualname": name,
                        "kind": "namespace",
                        "start": start,
                        "end": start,
                        "sig_line": raw.rstrip(),
                    }
                )
                i += 1
                continue
            end = brace_end(lines, i)
            units.append(
                {
                    "name": name.split(".")[-1],
                    "qualname": name,
                    "kind": "namespace",
                    "start": start,
                    "end": end,
                    "sig_line": raw.rstrip(),
                }
            )
            stack.append((name, end))
            i += 1
            continue

        m_type = _TYPE.match(s)
        if m_type:
            kind = m_type.group(1).split()[0]  # record class → record
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

        if s.startswith("using ") or s.startswith("namespace "):
            i += 1
            continue

        m_meth = _METHOD.match(s)
        if m_meth and "(" in s:
            name = m_meth.group(1)
            if name not in _SKIP and not _TYPE.match(s):
                parent = stack[-1][0] if stack else ""
                qn = f"{parent}.{name}" if parent else name
                start = i + 1
                if s.rstrip().endswith(";") and "{" not in s:
                    end = start
                else:
                    end = brace_end(lines, i)
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


def build_explore_csharp(source: str) -> str:
    units = extract_csharp_units(source)
    imports = extract_imports_csharp(source)
    parts: List[str] = []
    if imports:
        parts.append("// using/namespace")
        parts.extend(imports)
    if units:
        parts.append("// signatures")
        for u in units:
            parts.append(f"{u['sig_line']}  // {u['qualname']} L{u['start']}-{u['end']}")
    if not parts:
        return "\n".join(ln for ln in source.splitlines() if ln.strip())[:40]
    return "\n".join(parts)


def build_implement_csharp(
    source: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Tuple[str, Dict[str, Any]]:
    lines = source.splitlines()
    units = extract_csharp_units(source)
    meta: Dict[str, Any] = {
        "units": len(units),
        "targets_requested": list(targets or []),
        "targets_resolved": [],
        "fidelity": "full_file",
        "lang": "csharp",
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
    imports = extract_imports_csharp(source)
    parts: List[str] = []
    if imports:
        parts.append("// using/namespace")
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


def build_review_csharp(source: str) -> str:
    if source.lstrip().startswith("diff ") or "\n@@" in source:
        return source
    return build_explore_csharp(source)
