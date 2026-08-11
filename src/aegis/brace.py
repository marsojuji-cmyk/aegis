"""Shared brace/paren span helpers for structure slicers."""

from __future__ import annotations

from typing import List


def brace_end(lines: List[str], start_idx: int, open_ch: str = "{", close_ch: str = "}") -> int:
    """
    1-based end line of balanced open/close from start_idx (0-based).
    If no open brace on the start line region, return start line (or first ';' line).
    """
    depth = 0
    started = False
    for j in range(start_idx, len(lines)):
        line = lines[j]
        for ch in line:
            if ch == open_ch:
                depth += 1
                started = True
            elif ch == close_ch:
                depth -= 1
                if started and depth <= 0:
                    return j + 1
        if not started and j == start_idx:
            stripped = line.rstrip()
            if stripped.endswith(";") or (open_ch not in line and j + 1 < len(lines) and open_ch not in lines[j + 1]):
                # single-line decl without body, or body starts later — peek ahead for {
                for k in range(j, min(j + 3, len(lines))):
                    if open_ch in lines[k]:
                        return brace_end(lines, k, open_ch, close_ch)
                return j + 1
    return min(len(lines), start_idx + 1)


def match_target_names(units: list, targets) -> set:
    if not targets:
        return set()
    wanted = {t.strip() for t in targets if t and str(t).strip()}
    matched = set()
    for u in units:
        name = u.get("name", "")
        qn = u.get("qualname", name)
        for t in wanted:
            if t == name or t == qn or t.lower() == name.lower() or t in name or t in qn:
                matched.add(qn)
    return matched


def infer_from_task(task: str, units: list) -> set:
    import re

    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", task or ""))
    return {u["qualname"] for u in units if u.get("name") in tokens}
