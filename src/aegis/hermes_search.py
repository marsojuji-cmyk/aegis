"""Unified read-only search over gated Hermes indexes.

Does not call external search APIs. Query text is redacted before ranking.
Does not change shadow mode, production domains, billing, or models.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from aegis.paths import (
    hermes_index_files_path,
    hermes_index_graph_path,
    hermes_index_notes_path,
    hermes_index_projects_path,
)
from aegis.wrappers.hermes_wrapper import redact_excerpt

TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+")


def _load(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _tokens(text: str) -> List[str]:
    return [tok.lower() for tok in TOKEN_RE.findall(text or "") if len(tok) > 1]


def _score(haystack: str, tokens: List[str]) -> int:
    blob = (haystack or "").lower()
    return sum(blob.count(tok) for tok in tokens)


def unified_search(
    query: str,
    *,
    kind: str = "",
    tag: str = "",
    project: str = "",
    limit: int = 20,
    files_path: Optional[Path] = None,
    notes_path: Optional[Path] = None,
    graph_path: Optional[Path] = None,
    projects_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Rank files, notes, and projects. Empty indexes return no hits."""
    safe_query = str(redact_excerpt(query or "", limit=200))
    tokens = _tokens(safe_query)
    kind = (kind or "").lower()
    tag_l = (tag or "").lower()
    project_l = (project or "").lower()

    hits: List[Dict[str, Any]] = []

    if kind in {"", "file"}:
        files = _load(files_path or hermes_index_files_path())
        for row in files.get("files") or []:
            if row.get("type") == "dir":
                continue
            blob = " ".join(
                [
                    str(row.get("relpath") or ""),
                    str(row.get("path") or ""),
                    str(row.get("preview") or ""),
                    str(row.get("ext") or ""),
                ]
            )
            score = _score(blob, tokens) if tokens else 0
            if tokens and score <= 0:
                continue
            if not tokens:
                score = 1
            hits.append(
                {
                    "kind": "file",
                    "id": row.get("relpath"),
                    "title": row.get("relpath"),
                    "score": score,
                    "project": "",
                    "tags": [],
                }
            )

    if kind in {"", "note"}:
        notes = _load(notes_path or hermes_index_notes_path())
        for row in notes.get("notes") or []:
            tags = [str(t).lower() for t in (row.get("tags") or [])]
            if tag_l and tag_l not in tags:
                continue
            if project_l and project_l != str(row.get("project") or "").lower():
                continue
            blob = " ".join(
                [
                    str(row.get("title") or ""),
                    str(row.get("relpath") or ""),
                    str(row.get("project") or ""),
                    " ".join(tags),
                    " ".join(str(x) for x in (row.get("links") or [])),
                    str(row.get("excerpt") or ""),
                ]
            )
            score = _score(blob, tokens) if tokens else 0
            if tokens and score <= 0:
                continue
            if not tokens:
                score = 1
            hits.append(
                {
                    "kind": "note",
                    "id": row.get("relpath"),
                    "title": row.get("title") or row.get("relpath"),
                    "score": score + 1,
                    "project": row.get("project") or "",
                    "tags": row.get("tags") or [],
                }
            )

    if kind in {"", "project"}:
        projects = _load(projects_path or hermes_index_projects_path())
        for row in projects.get("projects") or []:
            if project_l and project_l != str(row.get("name") or "").lower():
                continue
            blob = " ".join(
                [
                    str(row.get("name") or ""),
                    str(row.get("manifest") or ""),
                    " ".join(str(x) for x in (row.get("notes") or [])),
                    " ".join(str(x) for x in (row.get("goals") or [])),
                ]
            )
            score = _score(blob, tokens) if tokens else 0
            if tokens and score <= 0:
                continue
            if not tokens:
                score = 1
            hits.append(
                {
                    "kind": "project",
                    "id": row.get("name"),
                    "title": row.get("name"),
                    "score": score + 2,
                    "project": row.get("name") or "",
                    "tags": [],
                }
            )

    hits.sort(key=lambda item: (-int(item["score"]), str(item.get("kind")), str(item.get("id"))))
    capped = hits[: max(1, min(int(limit), 100))]
    _ = graph_path or hermes_index_graph_path()
    return {
        "query": safe_query,
        "hit_count": len(capped),
        "hits": capped,
        "external_search": False,
    }
