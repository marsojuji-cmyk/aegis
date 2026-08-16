"""Hermes org skills: note graph + project context.

JSON is the API contract. No arbitrary filesystem access.
Does not persist to Hermes memory. Does not change shadow, domains, billing, or models.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aegis.hermes_index import DEFAULT_ROOT
from aegis.hermes_notes import (
    GraphIndex,
    active_graph,
    build_notes,
    format_context_packet,
    load_verified_disk_graph,
    notes_linked_to,
    notes_tagged,
    orphan_notes,
    project_context,
    resolve_context,
    resolve_note_ref,
    search_notes,
    skill_error,
)

DOCUMENTS_LABS = Path("/Users/a100/Documents/Memory Utility Labs")
from aegis.paths import hermes_index_graph_path, hermes_index_notes_path, hermes_index_projects_path
from aegis.wrappers.hermes_wrapper import TOOL_CAPABILITIES

SKILL_REGISTRY = (
    "hermes_notes_search",
    "hermes_note_get",
    "hermes_graph_neighbors",
    "hermes_project_context",
    "hermes_resolve_context",
)
LEGACY_SKILLS = ("note_graph", "project_context")
SKILL_NAMES = LEGACY_SKILLS + SKILL_REGISTRY

# Machine-readable skill surface. Vault Hermes Skill Surface.md is not SoT.
SKILL_CATALOG: Tuple[Dict[str, Any], ...] = (
    {
        "name": "note_graph",
        "description": "Index Markdown notes and query links, tags, orphans",
        "legacy": True,
        "use": "rebuild/status/linked_to/tagged/orphans only",
        "args": ["action", "root", "target", "tag"],
        "aliases": {},
    },
    {
        "name": "project_context",
        "description": "Load PROJECT.md goals, constraints, decisions for a session",
        "legacy": True,
        "use": "load PROJECT.md; prefer hermes_project_context for graph packets",
        "args": ["name"],
        "aliases": {},
    },
    {
        "name": "hermes_notes_search",
        "description": "Lexical search of the note graph by query, project, tags",
        "legacy": False,
        "use": "find notes by text; not graph expansion",
        "args": ["query", "project", "tags", "limit", "include_unresolved"],
        "aliases": {},
    },
    {
        "name": "hermes_note_get",
        "description": "Get one note by id or title",
        "legacy": False,
        "use": "fetch one resolved note",
        "args": ["note_id", "include_body"],
        "aliases": {"title": "note_id", "query": "note_id"},
    },
    {
        "name": "hermes_graph_neighbors",
        "description": "Inbound/outbound note neighbors",
        "legacy": False,
        "use": "one-hop link list; no bodies",
        "args": ["note_id", "direction", "hops", "limit"],
        "aliases": {"title": "note_id", "query": "note_id", "depth": "hops"},
    },
    {
        "name": "hermes_project_context",
        "description": "Bounded project context packet + provenance",
        "legacy": False,
        "use": "project-scoped packet; not a single-note walk",
        "args": ["project", "query", "max_notes", "max_total_chars"],
        "aliases": {},
    },
    {
        "name": "hermes_resolve_context",
        "description": "Bounded graph context from a note id or title",
        "legacy": False,
        "use": "graph walk from one seed; not lexical search",
        "args": ["note_id", "project", "depth", "max_notes", "max_body_chars", "max_total_chars", "include_target"],
        "aliases": {"title": "note_id", "query": "note_id", "max_hops": "depth", "max_chars": "max_body_chars"},
    },
)


def list_skills() -> List[Dict[str, Any]]:
    return [dict(row) for row in SKILL_CATALOG]


def _index_status() -> Dict[str, Any]:
    notes_path = hermes_index_notes_path()
    graph_path = hermes_index_graph_path()
    projects_path = hermes_index_projects_path()
    notes = {}
    graph = {}
    projects = {}
    if notes_path.is_file():
        notes = json.loads(notes_path.read_text(encoding="utf-8"))
    if graph_path.is_file():
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    if projects_path.is_file():
        projects = json.loads(projects_path.read_text(encoding="utf-8"))
    return {
        "note_count": int(notes.get("note_count") or 0),
        "edge_count": len(graph.get("edges") or []),
        "orphan_count": len(graph.get("orphans") or []),
        "project_count": len(projects.get("projects") or []),
        "root": notes.get("root") or graph.get("root") or "",
    }


def _require_graph() -> Tuple[Optional[GraphIndex], Optional[Dict[str, Any]]]:
    return load_verified_disk_graph()


def _ok(skill: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    out = {"ok": True, "skill": skill, "persisted_to_memory": False}
    out.update(payload)
    return out


def _note_ref(args: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    raw = args.get("note_id")
    if raw in (None, ""):
        raw = args.get("title")
    if raw in (None, ""):
        raw = args.get("query")
    if not isinstance(raw, str) or not raw.strip():
        return None, skill_error("INVALID_ARGUMENT", "note_id or title is required")
    return raw.strip(), None


def _resolved_note(graph: GraphIndex, args: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    ref, err = _note_ref(args)
    if err:
        return None, err
    return resolve_note_ref(ref, graph)


def invoke(skill: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structured JSON skill surface. Empty hits are success."""
    name = (skill or "").strip()
    payload = dict(args or {})
    if name not in SKILL_NAMES:
        return skill_error("INVALID_ARGUMENT", "unknown skill", details={"skill": name})
    graph, graph_err = _require_graph()
    if name in SKILL_REGISTRY and graph is None:
        return graph_err or skill_error("GRAPH_NOT_BUILT", "note graph has not been built")

    try:
        if name == "hermes_notes_search":
            return _notes_search(graph, payload)
        if name == "hermes_note_get":
            return _note_get(graph, payload)
        if name == "hermes_graph_neighbors":
            return _graph_neighbors(graph, payload)
        if name == "hermes_project_context":
            return _project_context_skill(graph, payload)
        if name == "hermes_resolve_context":
            return _resolve_context_skill(graph, payload)
        return dispatch(
            name,
            action=str(payload.get("action") or ""),
            root=str(payload.get("root") or ""),
            target=str(payload.get("target") or ""),
            tag=str(payload.get("tag") or ""),
            name=str(payload.get("name") or ""),
        )
    except Exception as exc:
        return skill_error("INTERNAL_ERROR", type(exc).__name__, details={"skill": name})


def _rejected_root(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = args.get("root")
    if raw in (None, ""):
        return None
    if not isinstance(raw, str):
        return skill_error("INVALID_ARGUMENT", "root must be a string")
    try:
        resolved = Path(raw).expanduser().resolve()
    except OSError:
        return skill_error("PATH_NOT_ALLOWED", "root is not a usable path", details={"root": raw})
    if resolved == DOCUMENTS_LABS.resolve() or DOCUMENTS_LABS.resolve() in resolved.parents:
        return skill_error(
            "PATH_NOT_ALLOWED",
            "Documents Labs is not the Hermes product corpus",
            details={"root": raw},
        )
    return skill_error(
        "PATH_NOT_ALLOWED",
        "search and context use the active graph; root overrides are rejected",
        details={"root": raw},
    )


def _notes_search(graph: GraphIndex, args: Dict[str, Any]) -> Dict[str, Any]:
    blocked = _rejected_root(args)
    if blocked:
        return blocked
    query = args.get("query")
    project = args.get("project")
    tags = args.get("tags")
    limit = args.get("limit", 10)
    if query is not None and not isinstance(query, str):
        return skill_error("INVALID_ARGUMENT", "query must be a string")
    if project is not None and not isinstance(project, str):
        return skill_error("INVALID_ARGUMENT", "project must be a string")
    if tags is not None and not isinstance(tags, (list, tuple, str)):
        return skill_error("INVALID_ARGUMENT", "tags must be a list or string")
    try:
        cap = int(limit)
    except (TypeError, ValueError):
        return skill_error("INVALID_ARGUMENT", "limit must be an integer")
    if cap < 1:
        return skill_error("INVALID_ARGUMENT", "limit must be >= 1")
    tag_list = []
    if isinstance(tags, str) and tags:
        tag_list = [tags]
    elif isinstance(tags, (list, tuple)):
        tag_list = [str(t) for t in tags if str(t).strip()]
    result = search_notes(
        str(query or ""),
        project=str(project or ""),
        limit=cap,
        include_unresolved=bool(args.get("include_unresolved", False)),
        index=graph,
    )
    if "error" in result:
        return result
    hits = []
    for hit in result.get("hits") or []:
        if tag_list and not any(t in (hit.get("tags") or []) for t in tag_list):
            continue
        hits.append(hit)
    result["hits"] = hits
    result["hit_count"] = len(hits)
    return _ok("hermes_notes_search", result)


def _note_get(graph: GraphIndex, args: Dict[str, Any]) -> Dict[str, Any]:
    nid, err = _resolved_note(graph, args)
    if err:
        return err
    rec = graph.notes_by_id[nid]
    include_body = bool(args.get("include_body", True))
    return _ok("hermes_note_get", {"note": rec.summary(include_body=include_body)})


def _graph_neighbors(graph: GraphIndex, args: Dict[str, Any]) -> Dict[str, Any]:
    nid, err = _resolved_note(graph, args)
    if err:
        return err
    direction = str(args.get("direction") or "both").lower()
    if direction not in {"inbound", "outbound", "both"}:
        return skill_error("INVALID_ARGUMENT", "direction must be inbound|outbound|both")
    try:
        if "hops" in args:
            hops = int(args["hops"])
        elif "depth" in args:
            hops = int(args["depth"])
        else:
            hops = 1
        limit = int(args.get("limit", 20))
    except (TypeError, ValueError):
        return skill_error("INVALID_ARGUMENT", "hops and limit must be integers")
    if hops < 0 or limit < 1:
        return skill_error("INVALID_ARGUMENT", "hops >= 0 and limit >= 1 required")
    result = resolve_context(
        nid,
        max_notes=limit,
        max_hops=hops,
        max_body_chars=0,
        max_total_chars=100_000,
        seed_mode="graph",
        index=graph,
    )
    neighbors = []
    for note in result.notes:
        if note["id"] == nid:
            continue
        reason = note.get("reason")
        if direction == "outbound" and reason != "outbound_link":
            continue
        if direction == "inbound" and reason != "inbound_link":
            continue
        neighbors.append(
            {
                "id": note["id"],
                "title": note["title"],
                "reason": reason,
                "hop": note.get("hop"),
            }
        )
    return _ok(
        "hermes_graph_neighbors",
        {
            "note_id": nid,
            "direction": direction,
            "neighbors": neighbors,
            "truncated": result.truncated,
            "warnings": result.warnings,
        },
    )


def _project_context_skill(graph: GraphIndex, args: Dict[str, Any]) -> Dict[str, Any]:
    project = args.get("project")
    if not isinstance(project, str) or not project.strip():
        return skill_error("INVALID_ARGUMENT", "project is required")
    if project not in graph.notes_by_project:
        return skill_error("PROJECT_NOT_FOUND", "project not in graph", details={"project": project})
    try:
        max_notes = int(args.get("max_notes", 8))
        max_total_chars = int(args.get("max_total_chars", 4000))
    except (TypeError, ValueError):
        return skill_error("INVALID_ARGUMENT", "max_notes and max_total_chars must be integers")
    if max_notes < 1 or max_total_chars < 1:
        return skill_error("INVALID_ARGUMENT", "max_notes and max_total_chars must be >= 1")
    result = resolve_context(
        str(args.get("query") or ""),
        project=project,
        max_notes=max_notes,
        max_hops=1,
        max_body_chars=800,
        max_total_chars=max_total_chars,
        index=graph,
    )
    packet = format_context_packet(result)
    return _ok(
        "hermes_project_context",
        {
            "context": result.as_dict(),
            "packet": packet,
            "truncated": result.truncated,
        },
    )


def _resolve_context_skill(graph: GraphIndex, args: Dict[str, Any]) -> Dict[str, Any]:
    blocked = _rejected_root(args)
    if blocked:
        return blocked
    nid, err = _resolved_note(graph, args)
    if err:
        return err
    project = args.get("project")
    if project is not None and not isinstance(project, str):
        return skill_error("INVALID_ARGUMENT", "project must be a string")
    try:
        max_hops = int(args.get("depth", args.get("max_hops", 1)))
        max_notes = int(args.get("max_notes", 8))
        max_body_chars = int(args.get("max_body_chars", args.get("max_chars", 800)))
        max_total_chars = int(args.get("max_total_chars", 4000))
    except (TypeError, ValueError):
        return skill_error("INVALID_ARGUMENT", "depth, max_notes, and max_chars must be integers")
    include_target = bool(args.get("include_target", True))
    result = resolve_context(
        nid,
        project=str(project or ""),
        max_notes=max_notes,
        max_hops=max_hops,
        max_body_chars=max_body_chars,
        max_total_chars=max_total_chars,
        include_target=include_target,
        seed_mode="graph",
        index=graph,
    )
    payload = result.as_dict()
    payload["corpus"] = {
        "root": result.root,
        "corpus_note_count": result.corpus_note_count,
        "unresolved_count": result.unresolved_count,
        "target_truncated": result.target_truncated,
        "algorithm": result.algorithm,
        "index_source": result.index_source,
        "project_filter": result.project,
    }
    return _ok(
        "hermes_resolve_context",
        {
            "context": payload,
            "truncated": result.truncated,
            "target_truncated": result.target_truncated,
            "unresolved_count": result.unresolved_count,
        },
    )


def dispatch(
    skill: str,
    *,
    action: str = "",
    root: str = "",
    target: str = "",
    tag: str = "",
    name: str = "",
) -> Dict[str, Any]:
    """Legacy + registry dispatch. Unknown skill names fail closed."""
    skill = (skill or "").strip().lower()
    action = (action or "").strip().lower()
    if skill in SKILL_REGISTRY:
        args: Dict[str, Any] = {
            "query": target or name,
            "project": name,
            "tags": [tag] if tag else [],
            "note_id": target,
            "action": action,
        }
        return invoke(skill, args)
    if skill not in LEGACY_SKILLS:
        return {"ok": False, "skill": skill, "error": "unknown skill", "persisted_to_memory": False}

    if skill == "note_graph":
        if action in {"rebuild", "index", "build"}:
            from aegis.doctor import hermes_rebuild_root_decision

            decision = hermes_rebuild_root_decision(root)
            if not decision["allowed"]:
                denied = skill_error(
                    "PATH_NOT_ALLOWED",
                    decision["reason"],
                    details={
                        "root": root or DEFAULT_ROOT,
                        "role": decision["role"],
                        "resolved": decision["resolved"],
                    },
                )
                denied["ok"] = False
                denied["skill"] = skill
                denied["action"] = "rebuild"
                denied["persisted_to_memory"] = False
                return denied
            out = build_notes(decision["resolved"])
            return {
                "ok": bool(out.get("write_executed")),
                "skill": skill,
                "action": "rebuild",
                "note_count": out.get("notes", {}).get("note_count", 0),
                "reads_allowed": out.get("notes", {}).get("reads_allowed", 0),
                "reads_denied": out.get("notes", {}).get("reads_denied", 0),
                "edge_count": len(out.get("graph", {}).get("edges") or []),
                "orphan_count": len(out.get("graph", {}).get("orphans") or []),
                "project_count": len(out.get("projects", {}).get("projects") or []),
                "write_executed": out.get("write_executed"),
                "persisted_to_memory": False,
            }
        if action in {"linked_to", "linked", "links"}:
            return {
                "ok": True,
                "skill": skill,
                "action": "linked_to",
                "hits": notes_linked_to(target),
                "persisted_to_memory": False,
            }
        if action in {"tagged", "tag"}:
            return {
                "ok": True,
                "skill": skill,
                "action": "tagged",
                "hits": notes_tagged(tag or target),
                "persisted_to_memory": False,
            }
        if action in {"orphans", "orphan"}:
            return {
                "ok": True,
                "skill": skill,
                "action": "orphans",
                "hits": orphan_notes(),
                "persisted_to_memory": False,
            }
        status = _index_status()
        return {
            "ok": True,
            "skill": skill,
            "action": "status",
            "persisted_to_memory": False,
            **status,
        }

    ctx = project_context(name)
    return {
        "ok": ctx is not None,
        "skill": skill,
        "action": "load",
        "project": ctx,
        "persisted_to_memory": False,
    }


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "integrations" / "hermes" / "skills"


def catalogued_in_wrapper() -> bool:
    return all(name in TOOL_CAPABILITIES for name in SKILL_REGISTRY)
