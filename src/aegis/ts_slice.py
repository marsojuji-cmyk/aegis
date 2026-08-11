"""TypeScript/JavaScript structure slice (E3 stub — regex + brace match, no tree-sitter)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


# Matches common declaration starts
_DECL = re.compile(
    r"^("
    r"\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)"
    r"|\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)"
    r"|\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\("
    r"|\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?function"
    r"|\s*(?:export\s+)?interface\s+(\w+)"
    r"|\s*(?:export\s+)?type\s+(\w+)\s*="
    r"|\s*(?:export\s+)?enum\s+(\w+)"
    r")"
)


def _name_from_match(m: re.Match) -> str:
    for g in m.groups()[1:]:
        if g:
            return g
    return "anon"


def extract_imports_js(source: str) -> List[str]:
    out = []
    for line in source.splitlines():
        s = line.strip()
        if s.startswith("import ") or s.startswith("export {") or s.startswith("require("):
            out.append(line.rstrip())
        elif s.startswith("export *") or s.startswith("export type"):
            out.append(line.rstrip())
    return out


def _find_units(source: str) -> List[Dict[str, Any]]:
    lines = source.splitlines()
    units: List[Dict[str, Any]] = []
    i = 0
    while i < len(lines):
        m = _DECL.match(lines[i])
        if not m:
            i += 1
            continue
        name = _name_from_match(m)
        start = i + 1  # 1-based
        # brace-balanced end
        end = _brace_end(lines, i)
        if end < start:
            end = start
        units.append(
            {
                "name": name,
                "qualname": name,
                "kind": "js_unit",
                "start": start,
                "end": end,
                "sig_line": lines[i].rstrip(),
            }
        )
        i = end  # continue after unit
    return units


def _brace_end(lines: List[str], start_idx: int) -> int:
    """Return 1-based end line of brace-balanced region from start_idx (0-based)."""
    depth = 0
    started = False
    for j in range(start_idx, len(lines)):
        line = lines[j]
        # skip braces in strings roughly
        for ch in line:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth <= 0:
                    return j + 1
        # arrow one-liner without braces
        if not started and j == start_idx and "{" not in line:
            # type alias / single-line
            if line.rstrip().endswith(";") or "=>" in line:
                return j + 1
            # interface might use { on next lines
    return min(len(lines), start_idx + 1)


def extract_js_units(source: str) -> List[Dict[str, Any]]:
    return _find_units(source)


def match_targets(units: List[Dict[str, Any]], targets: Sequence[str]) -> Set[str]:
    if not targets:
        return set()
    wanted = {t.strip() for t in targets if t and t.strip()}
    matched: Set[str] = set()
    for u in units:
        for t in wanted:
            if t == u["name"] or t == u["qualname"] or t.lower() == u["name"].lower():
                matched.add(u["qualname"])
            elif t in u["name"]:
                matched.add(u["qualname"])
    return matched


def infer_targets_from_task(task: str, units: List[Dict[str, Any]]) -> Set[str]:
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", task or ""))
    return {u["qualname"] for u in units if u["name"] in tokens}


def build_explore_js(source: str) -> str:
    units = extract_js_units(source)
    imports = extract_imports_js(source)
    parts: List[str] = []
    if imports:
        parts.append("// imports")
        parts.extend(imports)
    if units:
        parts.append("// signatures")
        for u in units:
            parts.append(f"{u['sig_line']}  // {u['qualname']} L{u['start']}-{u['end']}")
    if not parts:
        lines = [ln for ln in source.splitlines() if ln.strip()][:50]
        return "\n".join(lines)
    return "\n".join(parts)


def build_implement_js(
    source: str,
    targets: Optional[Sequence[str]] = None,
    task: str = "",
) -> Tuple[str, Dict[str, Any]]:
    lines = source.splitlines()
    units = extract_js_units(source)
    meta: Dict[str, Any] = {
        "units": len(units),
        "targets_requested": list(targets or []),
        "targets_resolved": [],
        "fidelity": "full_file",
        "lang": "typescript",
    }
    if not units:
        return source, meta

    resolved = match_targets(units, targets or [])
    if not resolved:
        resolved = infer_targets_from_task(task, units)
    if not resolved:
        meta["fidelity"] = "full_file"
        return source, meta

    meta["targets_resolved"] = sorted(resolved)
    meta["fidelity"] = "target_bodies"
    imports = extract_imports_js(source)
    parts: List[str] = []
    if imports:
        parts.append("// imports")
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


def build_review_js(source: str) -> str:
    if source.lstrip().startswith("diff ") or "\n@@" in source:
        return source
    return build_explore_js(source)
