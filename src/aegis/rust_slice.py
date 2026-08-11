"""Rust structure slice — fn / struct / enum / impl / trait (regex + brace match)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aegis.brace import brace_end, infer_from_task, match_target_names

_VIS = r"(?:pub(?:\([^)]*\))?\s+)?"
_FN = re.compile(
    rf"^{_VIS}(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?fn\s+(\w+)"
)
_STRUCT = re.compile(rf"^{_VIS}struct\s+(\w+)")
_ENUM = re.compile(rf"^{_VIS}enum\s+(\w+)")
_TRAIT = re.compile(rf"^{_VIS}trait\s+(\w+)")
_TYPE = re.compile(rf"^{_VIS}type\s+(\w+)")
_IMPL_FOR = re.compile(r"^impl(?:<[^>]*>)?\s+(\w+)\s+for\s+(\w+)")
_IMPL = re.compile(r"^impl(?:<[^>]*>)?\s+(\w+)")
_MOD = re.compile(rf"^{_VIS}mod\s+(\w+)")


def extract_imports_rust(source: str) -> List[str]:
    out = []
    for line in source.splitlines():
        s = line.strip()
        if s.startswith("use ") or s.startswith("mod ") or s.startswith("extern crate"):
            out.append(line.rstrip())
    return out


def extract_rust_units(source: str) -> List[Dict[str, Any]]:
    lines = source.splitlines()
    units: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if s.startswith("//") or s.startswith("/*") or s.startswith("#["):
            # attributes: attach to next unit by skipping; they'll be outside body
            if s.startswith("#["):
                i += 1
                continue
            i += 1
            continue

        name = None
        qn = None
        kind = None

        m = _IMPL_FOR.match(s)
        if m:
            name = m.group(2)
            qn = f"{m.group(1)}_for_{m.group(2)}"
            kind = "impl"
        if name is None:
            m = _IMPL.match(s)
            if m and not s.startswith("impl<") or (m and " for " not in s):
                # avoid double-hit: _IMPL also matches impl Trait for T's "impl"
                if " for " not in s:
                    name = m.group(1)
                    qn = f"impl_{name}"
                    kind = "impl"
        if name is None:
            for rx, k in (
                (_FN, "fn"),
                (_STRUCT, "struct"),
                (_ENUM, "enum"),
                (_TRAIT, "trait"),
                (_TYPE, "type"),
                (_MOD, "mod"),
            ):
                m = rx.match(s)
                if m:
                    name = m.group(1)
                    qn = name
                    kind = k
                    break

        if name is None:
            i += 1
            continue

        # include preceding attribute lines in sig if present
        sig_start = i
        while sig_start > 0 and lines[sig_start - 1].strip().startswith("#["):
            sig_start -= 1
        start = sig_start + 1
        end = brace_end(lines, i)
        units.append(
            {
                "name": name,
                "qualname": qn,
                "kind": kind,
                "start": start,
                "end": end,
                "sig_line": lines[i].rstrip(),
            }
        )
        i = max(end, i + 1)
    return units


def build_explore_rust(source: str) -> str:
    units = extract_rust_units(source)
    imports = extract_imports_rust(source)
    parts: List[str] = []
    if imports:
        parts.append("// use/mod")
        parts.extend(imports)
    if units:
        parts.append("// signatures")
        for u in units:
            parts.append(f"{u['sig_line']}  // {u['qualname']} L{u['start']}-{u['end']}")
    if not parts:
        return "\n".join(ln for ln in source.splitlines() if ln.strip())[:40]
    return "\n".join(parts)


def build_implement_rust(
    source: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Tuple[str, Dict[str, Any]]:
    lines = source.splitlines()
    units = extract_rust_units(source)
    meta: Dict[str, Any] = {
        "units": len(units),
        "targets_requested": list(targets or []),
        "targets_resolved": [],
        "fidelity": "full_file",
        "lang": "rust",
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
    imports = extract_imports_rust(source)
    parts: List[str] = []
    if imports:
        parts.append("// use/mod")
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


def build_review_rust(source: str) -> str:
    if source.lstrip().startswith("diff ") or "\n@@" in source:
        return source
    return build_explore_rust(source)
