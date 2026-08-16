"""Note graph and project context. Markdown reads go through HermesWrapper.

Default root remains /Users/ektar/workspace. Empty trees produce empty graphs.
Does not change shadow mode, production domains, billing, or models.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from aegis.hermes_index import (
    COMMON_IGNORES,
    DEFAULT_ROOT,
    _gate_write,
    _ignored,
    _load_gitignore,
    _wrapper,
)
from aegis.paths import (
    ensure_home,
    hermes_index_dir,
    hermes_index_graph_path,
    hermes_index_notes_path,
    hermes_index_projects_path,
)
from aegis.wrappers.hermes_wrapper import redact_excerpt

NOTES_VERSION = "1.0"
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
HEADING_RE = re.compile(r"^#{1,3}\s+(.*)$")
MANIFEST_SECTIONS = {
    "goal": "goals",
    "goals": "goals",
    "objective": "goals",
    "objectives": "goals",
    "constraint": "constraints",
    "constraints": "constraints",
    "limit": "constraints",
    "limits": "constraints",
    "decision": "decisions",
    "decisions": "decisions",
    "recent decisions": "decisions",
}
REASON_ORDER = {
    "exact_match": 0,
    "same_project": 1,
    "outbound_link": 2,
    "inbound_link": 3,
    "tag_match": 4,
    "lexical_match": 5,
}
ERROR_CODES = (
    "INVALID_ARGUMENT",
    "NOTE_NOT_FOUND",
    "AMBIGUOUS_TITLE",
    "PROJECT_NOT_FOUND",
    "PATH_NOT_ALLOWED",
    "GRAPH_NOT_BUILT",
    "INDEX_INVALID",
    "CONTEXT_LIMIT_EXCEEDED",
    "INTERNAL_ERROR",
)

_ACTIVE_GRAPH: Optional["GraphIndex"] = None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_frontmatter(text: str) -> Dict[str, Any]:
    """Parse a simple YAML-ish --- block. Unknown keys are preserved."""
    meta: Dict[str, Any] = {}
    if not text.startswith("---"):
        return meta
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return meta
    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break
    if end is None:
        return meta
    list_key: Optional[str] = None
    for line in lines[1:end]:
        stripped = line.strip()
        if list_key and stripped.startswith("- "):
            item = stripped[2:].strip().strip("\"'")
            bucket = meta.setdefault(list_key, [])
            if not isinstance(bucket, list):
                bucket = []
                meta[list_key] = bucket
            if item:
                bucket.append(item)
            continue
        if ":" not in line:
            list_key = None
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if not key:
            list_key = None
            continue
        if key in {"tags", "projects"}:
            if value:
                meta[key] = [part.strip() for part in value.strip("[]").split(",") if part.strip()]
                list_key = None
            else:
                meta[key] = []
                list_key = key
        else:
            list_key = None
            meta[key] = value
    return meta


def parse_wikilinks(text: str) -> List[str]:
    seen = []
    for match in WIKILINK_RE.finditer(text or ""):
        name = match.group(1).strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def parse_wikilink_spans(text: str) -> List[Tuple[str, int]]:
    """All [[wikilinks]] with character offsets. Duplicates kept."""
    spans: List[Tuple[str, int]] = []
    for match in WIKILINK_RE.finditer(text or ""):
        name = match.group(1).strip()
        if name:
            spans.append((name, match.start()))
    return spans


def _note_body(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2]
    return text


def parse_manifest_sections(text: str) -> Dict[str, List[str]]:
    """Pull Goals / Constraints / Decisions from a PROJECT.md body."""
    sections: Dict[str, List[str]] = {"goals": [], "constraints": [], "decisions": []}
    current: Optional[str] = None
    for line in _note_body(text or "").splitlines():
        heading = HEADING_RE.match(line.strip())
        if heading:
            current = MANIFEST_SECTIONS.get(heading.group(1).strip().lower())
            continue
        if not current:
            continue
        item = line.strip().lstrip("-*").strip()
        if item:
            sections[current].append(item)
    return sections


def _empty_project(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "manifest": None,
        "notes": [],
        "goals": [],
        "constraints": [],
        "decisions": [],
    }


def parse_note(text: str, *, relpath: str = "") -> Dict[str, Any]:
    meta = parse_frontmatter(text)
    body = _note_body(text)
    title = str(meta.get("title") or "")
    if not title:
        for line in body.splitlines():
            heading = HEADING_RE.match(line.strip())
            if heading:
                title = heading.group(1).strip()
                break
    if not title:
        title = Path(relpath).stem if relpath else ""
    tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    if isinstance(meta.get("tags"), str):
        tags = [meta["tags"]]
    project = meta.get("project") or ""
    if not project and isinstance(meta.get("projects"), list) and meta["projects"]:
        project = str(meta["projects"][0])
    return {
        "title": title,
        "tags": tags,
        "project": project,
        "date": meta.get("date") or meta.get("updated") or "",
        "links": parse_wikilinks(text),
        "headings": [m.group(1).strip() for m in (HEADING_RE.match(ln.strip()) for ln in body.splitlines()) if m],
        "frontmatter": meta,
        "body": body,
    }


def note_id_for(relpath: str) -> str:
    return str(relpath or "").replace("\\", "/")


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def skill_error(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if code not in ERROR_CODES:
        code = "INTERNAL_ERROR"
    return {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details or {},
        }
    }


def path_not_allowed(note_id: str) -> bool:
    raw = str(note_id or "")
    if not raw or "\x00" in raw:
        return True
    if raw.startswith("~"):
        return True
    parts = Path(raw).parts
    return ".." in parts or raw.startswith("/")


@dataclass
class NoteRecord:
    id: str
    path: str
    title: str
    body: str
    frontmatter: Dict[str, Any]
    tags: List[str]
    project: str
    modified_at: str
    content_hash: str

    def summary(self, *, include_body: bool = False, max_body_chars: int = 0) -> Dict[str, Any]:
        row = {
            "id": self.id,
            "path": self.path,
            "title": self.title,
            "tags": list(self.tags),
            "project": self.project,
            "modified_at": self.modified_at,
            "content_hash": self.content_hash,
            "frontmatter": dict(self.frontmatter),
        }
        if include_body:
            body = self.body
            if max_body_chars and len(body) > max_body_chars:
                body = body[:max_body_chars]
            row["body"] = body
        return row


@dataclass
class NoteLink:
    source_id: str
    target_title: str
    target_id: Optional[str]
    link_type: str
    position: int

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContextResult:
    query: str
    project: str
    notes: List[Dict[str, Any]]
    links: List[Dict[str, Any]]
    provenance: List[Dict[str, Any]]
    unresolved_links: List[str]
    warnings: List[str]
    truncated: bool = False
    root: str = ""
    corpus_note_count: int = 0
    unresolved_count: int = 0
    target_truncated: bool = False
    algorithm: str = "graph-nav/1.0"
    index_source: str = "active_graph"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphIndex:
    root: str
    notes_by_id: Dict[str, NoteRecord] = field(default_factory=dict)
    notes_by_title: Dict[str, List[str]] = field(default_factory=dict)
    outbound_links: Dict[str, List[NoteLink]] = field(default_factory=dict)
    inbound_links: Dict[str, List[NoteLink]] = field(default_factory=dict)
    notes_by_project: Dict[str, List[str]] = field(default_factory=dict)
    notes_by_tag: Dict[str, List[str]] = field(default_factory=dict)
    unresolved_links: List[NoteLink] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    version: str = NOTES_VERSION
    reads_allowed: int = 0
    reads_denied: int = 0


def active_graph() -> Optional[GraphIndex]:
    return _ACTIVE_GRAPH


def set_active_graph(index: Optional[GraphIndex]) -> None:
    global _ACTIVE_GRAPH
    _ACTIVE_GRAPH = index


def _under_root(path: Path, root: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
        anchor = root.expanduser().resolve()
    except OSError:
        return False
    return resolved == anchor or anchor in resolved.parents


def _graph_from_disk(notes: Dict[str, Any], graph: Dict[str, Any]) -> GraphIndex:
    root = str(notes.get("root") or graph.get("root") or "")
    index = GraphIndex(root=root, version=str(notes.get("version") or NOTES_VERSION))
    for item in notes.get("notes") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        rec = NoteRecord(
            id=str(item["id"]),
            path=str(item.get("path") or ""),
            title=str(item.get("title") or ""),
            body=str(item.get("excerpt") or ""),
            frontmatter=dict(item.get("frontmatter") or {}),
            tags=[str(t) for t in (item.get("tags") or [])],
            project=str(item.get("project") or ""),
            modified_at=str(item.get("modified_at") or ""),
            content_hash=str(item.get("content_hash") or ""),
        )
        index.notes_by_id[rec.id] = rec
    title_map = graph.get("notes_by_title") or {}
    if isinstance(title_map, dict) and title_map:
        for title, ids in title_map.items():
            index.notes_by_title[str(title)] = [str(i) for i in ids]
    else:
        for rec in index.notes_by_id.values():
            index.notes_by_title.setdefault(rec.title, []).append(rec.id)
    for project, ids in (graph.get("notes_by_project") or {}).items():
        index.notes_by_project[str(project)] = [str(i) for i in ids]
    for tag, ids in (graph.get("notes_by_tag") or {}).items():
        index.notes_by_tag[str(tag)] = [str(i) for i in ids]
    if not index.notes_by_project or not index.notes_by_tag:
        for rec in index.notes_by_id.values():
            if rec.project:
                bucket = index.notes_by_project.setdefault(rec.project, [])
                if rec.id not in bucket:
                    bucket.append(rec.id)
            for tag in rec.tags:
                bucket = index.notes_by_tag.setdefault(tag, [])
                if rec.id not in bucket:
                    bucket.append(rec.id)
    for raw in graph.get("unresolved") or []:
        if not isinstance(raw, dict):
            continue
        index.unresolved_links.append(
            NoteLink(
                source_id=str(raw.get("source_id") or ""),
                target_title=str(raw.get("target_title") or ""),
                target_id=raw.get("target_id"),
                link_type=str(raw.get("link_type") or "wikilink"),
                position=int(raw.get("position") or 0),
            )
        )
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if not source:
            continue
        resolved = bool(edge.get("resolved"))
        target_id = target if resolved and target in index.notes_by_id else None
        title = (
            index.notes_by_id[target_id].title
            if target_id
            else target
        )
        link = NoteLink(
            source_id=source,
            target_title=title,
            target_id=target_id,
            link_type=str(edge.get("link_type") or "wikilink"),
            position=int(edge.get("position") or 0),
        )
        index.outbound_links.setdefault(source, []).append(link)
        if target_id:
            index.inbound_links.setdefault(target_id, []).append(link)
    index.reads_allowed = int(notes.get("reads_allowed") or 0)
    index.reads_denied = int(notes.get("reads_denied") or 0)
    return index


def _hydrate_note_bodies(index: GraphIndex) -> None:
    root = Path(index.root)
    for rec in index.notes_by_id.values():
        path = Path(rec.path) if rec.path else root / rec.id
        if not _under_root(path, root):
            continue
        try:
            rec.body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue


def load_verified_disk_graph() -> Tuple[Optional[GraphIndex], Optional[Dict[str, Any]]]:
    """Load notes+graph from $AEGIS_HOME when provenance matches. No rebuild. Never files.json."""
    live = active_graph()
    if live is not None:
        return live, None
    notes_path = hermes_index_notes_path()
    graph_path = hermes_index_graph_path()
    if not notes_path.is_file() or not graph_path.is_file():
        return None, skill_error(
            "GRAPH_NOT_BUILT",
            "note graph has not been built",
            details={"notes": str(notes_path), "graph": str(graph_path)},
        )
    try:
        notes = json.loads(notes_path.read_text(encoding="utf-8"))
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, skill_error(
            "INDEX_INVALID",
            "malformed disk index",
            details={"error": type(exc).__name__},
        )
    if not isinstance(notes, dict) or not isinstance(graph, dict):
        return None, skill_error("INDEX_INVALID", "malformed disk index")
    if "files" in notes and "notes" not in notes:
        return None, skill_error(
            "INDEX_INVALID",
            "files.json is not a notes graph",
            details={"path": str(notes_path)},
        )
    nver = str(notes.get("version") or "")
    gver = str(graph.get("version") or "")
    if nver != NOTES_VERSION or gver != NOTES_VERSION:
        return None, skill_error(
            "INDEX_INVALID",
            "incompatible index schema",
            details={"notes_version": nver, "graph_version": gver, "expected": NOTES_VERSION},
        )
    nroot = str(notes.get("root") or "")
    groot = str(graph.get("root") or "")
    try:
        same_root = bool(nroot) and bool(groot) and Path(nroot).resolve() == Path(groot).resolve()
    except OSError:
        same_root = False
    if not same_root:
        return None, skill_error(
            "INDEX_INVALID",
            "notes and graph roots do not match",
            details={"notes_root": nroot, "graph_root": groot},
        )
    nsig = str(notes.get("signature") or "")
    gsig = str(graph.get("signature") or "")
    if nsig and gsig and nsig != gsig:
        return None, skill_error(
            "INDEX_INVALID",
            "stale index: notes and graph signatures differ",
            details={"notes_signature": nsig, "graph_signature": gsig},
        )
    from aegis.doctor import classify_hermes_root, hermes_rebuild_root_decision, resolve_hermes_notes_root

    pin = resolve_hermes_notes_root()
    role = classify_hermes_root(nroot, pin=pin)
    if role != "canonical":
        return None, skill_error(
            "PATH_NOT_ALLOWED",
            "disk index root is not the pinned or canonical Hermes corpus",
            details={"root": nroot, "role": role},
        )
    decision = hermes_rebuild_root_decision(nroot)
    if not decision["allowed"]:
        return None, skill_error(
            "PATH_NOT_ALLOWED",
            decision["reason"],
            details={"root": nroot, "role": decision["role"]},
        )
    index = _graph_from_disk(notes, graph)
    _hydrate_note_bodies(index)
    set_active_graph(index)
    return index, None


def graph_signature(index: GraphIndex) -> str:
    payload = {
        "root": index.root,
        "notes": {
            nid: {
                "title": rec.title,
                "hash": rec.content_hash,
                "tags": rec.tags,
                "project": rec.project,
                "frontmatter": rec.frontmatter,
            }
            for nid, rec in sorted(index.notes_by_id.items())
        },
        "out": {
            nid: [
                (link.target_title, link.target_id, link.link_type, link.position)
                for link in links
            ]
            for nid, links in sorted(index.outbound_links.items())
        },
        "unresolved": [
            (link.source_id, link.target_title, link.position)
            for link in index.unresolved_links
        ],
        "warnings": list(index.warnings),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _gate_read_full(wrapper: Any, filepath: str, domains: Sequence[str]) -> Dict[str, Any]:
    return wrapper.handle(
        {
            "tool_name": "read_file",
            "args": {"filepath": filepath},
            "identity": {"agent": "hermes", "session_id": "hermes-notes"},
            "scope": {"allowed_domains": list(domains)},
            "environment": "hermes-index",
        },
        execute_fn=lambda args: Path(args["filepath"]).read_text(
            encoding="utf-8", errors="replace"
        ),
    )


def _write_json(wrapper: Any, dest: Path, payload: Dict[str, Any], domains: Sequence[str]) -> Dict[str, Any]:
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    write = _gate_write(wrapper, str(dest), body, domains)
    if write.get("decision") == "allow" and write.get("executed"):
        dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return write


def _mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(
            microsecond=0
        ).isoformat()
    except OSError:
        return ""


def make_note_record(text: str, *, relpath: str, path: Path) -> NoteRecord:
    parsed = parse_note(text, relpath=relpath)
    nid = note_id_for(relpath)
    return NoteRecord(
        id=nid,
        path=str(path),
        title=str(parsed["title"]),
        body=str(parsed.get("body") or ""),
        frontmatter=dict(parsed.get("frontmatter") or {}),
        tags=list(parsed.get("tags") or []),
        project=str(parsed.get("project") or ""),
        modified_at=_mtime(path),
        content_hash=content_hash(text),
    )


def build_graph(root: str = DEFAULT_ROOT) -> GraphIndex:
    """Discover Markdown, parse with existing helpers, resolve [[wikilinks]]."""
    root_path = Path(root).expanduser().resolve()
    index = GraphIndex(root=str(root_path))
    patterns = list(COMMON_IGNORES) + _load_gitignore(root_path)
    wrapper = _wrapper([str(root_path)])
    if root_path.is_dir():
        md_files = sorted(p for p in root_path.rglob("*.md") if p.is_file())
    else:
        md_files = []

    records: List[NoteRecord] = []
    raw_by_id: Dict[str, str] = {}
    for path in md_files:
        rel = str(path.relative_to(root_path)).replace("\\", "/")
        if _ignored(rel, path.name, patterns) or any(
            _ignored(part, part, patterns) for part in Path(rel).parts
        ):
            continue
        gated = _gate_read_full(wrapper, str(path), [str(root_path)])
        if not (gated.get("decision") == "allow" and gated.get("executed")):
            index.reads_denied += 1
            continue
        index.reads_allowed += 1
        raw_text = str(gated.get("output") or "")
        rec = make_note_record(raw_text, relpath=rel, path=path)
        records.append(rec)
        raw_by_id[rec.id] = raw_text

    records.sort(key=lambda rec: rec.id)
    for rec in records:
        index.notes_by_id[rec.id] = rec
        title_key = rec.title
        index.notes_by_title.setdefault(title_key, []).append(rec.id)
        if rec.project:
            index.notes_by_project.setdefault(rec.project, []).append(rec.id)
        for tag in rec.tags:
            index.notes_by_tag.setdefault(str(tag), []).append(rec.id)

    for title, ids in index.notes_by_title.items():
        ids.sort()
        if len(ids) > 1:
            index.warnings.append(f"AMBIGUOUS_TITLE:{title}")
    for ids in index.notes_by_project.values():
        ids.sort()
    for ids in index.notes_by_tag.values():
        ids.sort()

    for rec in records:
        outbound: List[NoteLink] = []
        for target_title, position in parse_wikilink_spans(raw_by_id.get(rec.id, rec.body)):
            matches = list(index.notes_by_title.get(target_title) or [])
            target_id: Optional[str] = None
            if len(matches) == 1:
                target_id = matches[0]
            elif len(matches) > 1:
                index.warnings.append(f"AMBIGUOUS_TITLE:{target_title}")
            link = NoteLink(
                source_id=rec.id,
                target_title=target_title,
                target_id=target_id,
                link_type="wikilink",
                position=position,
            )
            outbound.append(link)
            if target_id is None:
                index.unresolved_links.append(link)
            else:
                index.inbound_links.setdefault(target_id, []).append(link)
        outbound.sort(key=lambda link: (link.position, link.target_title, link.target_id or ""))
        index.outbound_links[rec.id] = outbound

    for nid in index.inbound_links:
        index.inbound_links[nid].sort(
            key=lambda link: (link.source_id, link.position, link.target_title)
        )
    index.unresolved_links.sort(key=lambda link: (link.source_id, link.position, link.target_title))
    set_active_graph(index)
    return index


def build_notes(
    root: str = DEFAULT_ROOT,
    *,
    notes_dest: Optional[Path] = None,
    graph_dest: Optional[Path] = None,
    projects_dest: Optional[Path] = None,
) -> Dict[str, Any]:
    """Read Markdown through the gate; write notes/graph/projects under ~/.aegis/hermes_index/."""
    from aegis.doctor import hermes_rebuild_root_decision

    decision = hermes_rebuild_root_decision(root)
    if not decision["allowed"]:
        return {
            "ok": False,
            "write_executed": False,
            "write_decision": "deny",
            "error": {
                "code": "PATH_NOT_ALLOWED",
                "message": decision["reason"],
                "retryable": False,
                "details": {
                    "root": root,
                    "role": decision["role"],
                    "resolved": decision["resolved"],
                },
            },
        }
    root = decision["resolved"]
    ensure_home()
    index = build_graph(root)
    root_path = Path(index.root)
    notes_path = notes_dest or hermes_index_notes_path()
    graph_path = graph_dest or hermes_index_graph_path()
    projects_path = projects_dest or hermes_index_projects_path()
    hermes_index_dir().mkdir(parents=True, exist_ok=True)
    index_domain = str(notes_path.parent)
    wrapper = _wrapper([str(root_path), index_domain])

    notes: List[Dict[str, Any]] = []
    for rec in sorted(index.notes_by_id.values(), key=lambda item: item.id):
        item: Dict[str, Any] = {
            "id": rec.id,
            "path": rec.path,
            "relpath": rec.id,
            "stem": Path(rec.id).stem,
            "title": rec.title,
            "tags": rec.tags,
            "project": rec.project,
            "date": rec.frontmatter.get("date") or rec.frontmatter.get("updated") or "",
            "links": [link.target_title for link in index.outbound_links.get(rec.id, [])],
            "headings": [
                m.group(1).strip()
                for m in (HEADING_RE.match(ln.strip()) for ln in rec.body.splitlines())
                if m
            ],
            "excerpt": redact_excerpt(rec.body, limit=240),
            "read_decision": "allow",
            "content_hash": rec.content_hash,
            "modified_at": rec.modified_at,
            "frontmatter": rec.frontmatter,
        }
        if Path(rec.id).name == "PROJECT.md":
            item["manifest_sections"] = parse_manifest_sections(rec.body)
        notes.append(item)

    edges = []
    for rec in sorted(index.notes_by_id.values(), key=lambda item: item.id):
        for link in index.outbound_links.get(rec.id, []):
            edges.append(
                {
                    "from": rec.id,
                    "to": link.target_id or link.target_title,
                    "resolved": link.target_id is not None,
                    "position": link.position,
                    "link_type": link.link_type,
                }
            )
    incoming = {rec.id: 0 for rec in index.notes_by_id.values()}
    for edge in edges:
        if edge["resolved"] and edge["to"] in incoming:
            incoming[edge["to"]] += 1
    orphans = [
        rec.id
        for rec in sorted(index.notes_by_id.values(), key=lambda item: item.id)
        if incoming.get(rec.id, 0) == 0 and not index.outbound_links.get(rec.id)
    ]

    graph = {
        "version": NOTES_VERSION,
        "root": str(root_path),
        "signature": graph_signature(index),
        "nodes": [
            {"id": rec.id, "title": rec.title, "tags": rec.tags, "project": rec.project}
            for rec in sorted(index.notes_by_id.values(), key=lambda item: item.id)
        ],
        "edges": edges,
        "orphans": orphans,
        "notes_by_title": {k: list(v) for k, v in sorted(index.notes_by_title.items())},
        "notes_by_project": {k: list(v) for k, v in sorted(index.notes_by_project.items())},
        "notes_by_tag": {k: list(v) for k, v in sorted(index.notes_by_tag.items())},
        "unresolved": [link.as_dict() for link in index.unresolved_links],
        "warnings": list(index.warnings),
    }

    projects: Dict[str, Dict[str, Any]] = {}
    for rec in sorted(index.notes_by_id.values(), key=lambda item: item.id):
        if rec.id.endswith("PROJECT.md"):
            name = rec.project or Path(rec.id).parent.name or "root"
            bucket = projects.setdefault(name, _empty_project(name))
            bucket["manifest"] = rec.id
            sections = parse_manifest_sections(rec.body)
            for key in ("goals", "constraints", "decisions"):
                bucket[key] = list(sections.get(key) or [])
        if rec.project:
            bucket = projects.setdefault(rec.project, _empty_project(rec.project))
            if rec.id not in bucket["notes"]:
                bucket["notes"].append(rec.id)

    notes_payload = {
        "version": NOTES_VERSION,
        "root": str(root_path),
        "signature": graph_signature(index),
        "note_count": len(notes),
        "reads_allowed": index.reads_allowed,
        "reads_denied": index.reads_denied,
        "notes": notes,
    }
    projects_payload = {
        "version": NOTES_VERSION,
        "root": str(root_path),
        "projects": list(projects.values()),
    }

    w_notes = _write_json(wrapper, notes_path, notes_payload, [index_domain])
    w_graph = _write_json(wrapper, graph_path, graph, [index_domain])
    w_proj = _write_json(wrapper, projects_path, projects_payload, [index_domain])
    return {
        "notes": notes_payload,
        "graph": graph,
        "projects": projects_payload,
        "index": index,
        "write_decision": w_notes.get("decision"),
        "write_executed": bool(
            w_notes.get("executed") and w_graph.get("executed") and w_proj.get("executed")
        ),
    }


def notes_linked_to(target: str, *, graph_dest: Optional[Path] = None) -> List[str]:
    src = graph_dest or hermes_index_graph_path()
    if not src.is_file():
        return []
    data = json.loads(src.read_text(encoding="utf-8"))
    needle = target.lower()
    hits = []
    for edge in data.get("edges") or []:
        to = str(edge.get("to") or "")
        if needle in to.lower() or needle in Path(to).stem.lower():
            hits.append(edge.get("from"))
    return hits


def notes_tagged(tag: str, *, notes_dest: Optional[Path] = None) -> List[str]:
    src = notes_dest or hermes_index_notes_path()
    if not src.is_file():
        return []
    data = json.loads(src.read_text(encoding="utf-8"))
    needle = tag.lower()
    return [
        note.get("id") or note["relpath"]
        for note in data.get("notes") or []
        if any(needle == str(t).lower() for t in (note.get("tags") or []))
    ]


def orphan_notes(*, graph_dest: Optional[Path] = None) -> List[str]:
    src = graph_dest or hermes_index_graph_path()
    if not src.is_file():
        return []
    data = json.loads(src.read_text(encoding="utf-8"))
    return list(data.get("orphans") or [])


def project_context(name: str = "", *, projects_dest: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    src = projects_dest or hermes_index_projects_path()
    if not src.is_file():
        return None
    data = json.loads(src.read_text(encoding="utf-8"))
    rows = list(data.get("projects") or [])
    if not rows:
        return None
    if not name:
        return rows[0]
    needle = name.lower()
    for row in rows:
        if needle == str(row.get("name") or "").lower():
            return row
    return None


SEARCH_ALGORITHM = "lexical/index/1.0"
CONTEXT_ALGORITHM = "graph-nav/1.0"
SEARCH_LIMIT_MAX = 100


def _tokens(text: str) -> List[str]:
    return [part.lower() for part in re.findall(r"[A-Za-z0-9_./-]+", text or "") if len(part) > 1]


def retrieval_meta(graph: Optional[GraphIndex], *, project: str = "", algorithm: str = "") -> Dict[str, Any]:
    """Read-only corpus locator. Does not open vaults or rebuild indexes."""
    notes_path = hermes_index_notes_path()
    graph_path = hermes_index_graph_path()
    projects_path = hermes_index_projects_path()
    generated_ts = ""
    index_root = ""
    if notes_path.is_file():
        try:
            payload = json.loads(notes_path.read_text(encoding="utf-8"))
            generated_ts = str(payload.get("generated_ts") or "")
            index_root = str(payload.get("root") or "")
        except (OSError, json.JSONDecodeError):
            generated_ts = ""
    root = (graph.root if graph is not None else "") or index_root
    from_index = bool(index_root) and bool(root) and Path(index_root) == Path(root)
    return {
        "root": root,
        "index_files": [str(notes_path), str(graph_path), str(projects_path)],
        "index_generated_ts": generated_ts,
        "corpus_note_count": len(graph.notes_by_id) if graph is not None else 0,
        "index_source": "production_index" if from_index else "active_graph",
        "project_filter": project or "",
        "algorithm": algorithm,
    }


def search_notes(
    query: str,
    *,
    project: str = "",
    limit: int = 10,
    include_unresolved: bool = False,
    index: Optional[GraphIndex] = None,
) -> Dict[str, Any]:
    """Deterministic lexical ranker over an in-memory GraphIndex. No writes."""
    graph = index or active_graph()
    meta = retrieval_meta(graph, project=project, algorithm=SEARCH_ALGORITHM)
    if graph is None:
        return skill_error("GRAPH_NOT_BUILT", "note graph has not been built")
    q = (query or "").strip()
    if not q:
        return skill_error("INVALID_ARGUMENT", "query must be a non-empty string")
    if limit < 1:
        return skill_error("INVALID_ARGUMENT", "limit must be >= 1")
    cap = min(int(limit), SEARCH_LIMIT_MAX)
    q_l = q.lower()
    tokens = _tokens(q)
    hits: List[Dict[str, Any]] = []
    for rec in graph.notes_by_id.values():
        if project and rec.project != project:
            continue
        title_l = rec.title.lower()
        id_l = rec.id.lower()
        body_l = rec.body.lower()
        tags_l = [str(t).lower() for t in rec.tags]
        score = 0
        reason = "lexical_match"
        if title_l == q_l or id_l == q_l or Path(rec.id).stem.lower() == q_l:
            score += 1000
            reason = "exact_title"
        if q_l and q_l in title_l:
            score += 400
            if reason != "exact_title":
                reason = "title_phrase"
        if q_l and q_l in body_l:
            score += 200
            if reason == "lexical_match":
                reason = "body_phrase"
        if q_l in tags_l or (project and project.lower() == q_l and rec.project.lower() == q_l):
            score += 150
            if reason == "lexical_match":
                reason = "tag_match"
        for tok in tokens:
            if tok in title_l or tok in id_l:
                score += 50
            if tok in body_l:
                score += 10
            if tok in tags_l:
                score += 20
        if score <= 0:
            continue
        hits.append(
            {
                "id": rec.id,
                "title": rec.title,
                "score": score,
                "reason": reason,
                "project": rec.project,
                "tags": list(rec.tags),
                "path": rec.path,
                "provenance": "verified",
            }
        )
    unresolved_hits: List[Dict[str, Any]] = []
    if include_unresolved:
        seen = set()
        for link in graph.unresolved_links:
            title = link.target_title
            if title in seen:
                continue
            if q_l not in title.lower() and not all(tok in title.lower() for tok in tokens):
                continue
            seen.add(title)
            unresolved_hits.append(
                {
                    "id": None,
                    "title": title,
                    "score": 1,
                    "reason": "unresolved_wikilink",
                    "project": "",
                    "tags": [],
                    "path": "",
                    "provenance": "verified",
                }
            )
    hits.sort(key=lambda row: (-int(row["score"]), str(row["title"]).lower(), str(row["id"])))
    unresolved_hits.sort(key=lambda row: (str(row["title"]).lower(),))
    combined = hits + unresolved_hits
    truncated = len(combined) > cap
    capped = combined[:cap]
    meta["unresolved_count"] = len(graph.unresolved_links)
    meta["truncated"] = truncated
    return {
        "ok": True,
        "query": q,
        "project": project or "",
        "hit_count": len(capped),
        "hits": capped,
        "truncated": truncated,
        "include_unresolved": include_unresolved,
        "persisted_to_memory": False,
        "corpus": meta,
    }


def resolve_note_ref(ref: str, index: GraphIndex) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    if path_not_allowed(ref) and not (ref in index.notes_by_id):
        return None, skill_error("PATH_NOT_ALLOWED", "note_id escapes configured notes root", details={"note_id": ref})
    if ref in index.notes_by_id:
        return ref, None
    matches = list(index.notes_by_title.get(ref) or [])
    if not matches:
        lowered = ref.lower()
        for title, ids in index.notes_by_title.items():
            if title.lower() == lowered:
                matches = list(ids)
                break
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, skill_error(
            "AMBIGUOUS_TITLE",
            "duplicate titles; use a path-based note_id",
            details={"title": ref, "ids": matches},
        )
    return None, skill_error("NOTE_NOT_FOUND", "note not in graph", details={"note_id": ref})


def resolve_context(
    query: str = "",
    *,
    project: str = "",
    max_notes: int = 8,
    max_hops: int = 1,
    max_body_chars: int = 800,
    max_total_chars: int = 4000,
    include_target: bool = True,
    seed_mode: str = "auto",
    index: Optional[GraphIndex] = None,
) -> ContextResult:
    graph = index or active_graph()
    warnings: List[str] = []
    meta = retrieval_meta(graph, project=project, algorithm=CONTEXT_ALGORITHM)
    if graph is None:
        return ContextResult(
            query=query,
            project=project,
            notes=[],
            links=[],
            provenance=[],
            unresolved_links=[],
            warnings=["GRAPH_NOT_BUILT"],
            truncated=False,
            algorithm=CONTEXT_ALGORITHM,
            index_source=meta["index_source"],
        )
    if max_notes < 1 or max_hops < 0 or max_body_chars < 0 or max_total_chars < 0:
        return ContextResult(
            query=query,
            project=project,
            notes=[],
            links=[],
            provenance=[],
            unresolved_links=[],
            warnings=["INVALID_ARGUMENT"],
            truncated=False,
            root=graph.root,
            corpus_note_count=len(graph.notes_by_id),
            algorithm=CONTEXT_ALGORITHM,
            index_source=meta["index_source"],
        )

    seeds: Dict[str, str] = {}
    q = (query or "").strip()
    q_l = q.lower()
    tokens = _tokens(q)
    graph_only = (seed_mode or "auto").strip().lower() == "graph"

    def consider(nid: str, reason: str) -> None:
        if project and graph.notes_by_id[nid].project != project and reason != "outbound_link" and reason != "inbound_link":
            if reason != "same_project":
                return
        current = seeds.get(nid)
        if current is None or REASON_ORDER[reason] < REASON_ORDER[current]:
            seeds[nid] = reason

    if q and q in graph.notes_by_id:
        consider(q, "exact_match")
    title_ids = list(graph.notes_by_title.get(q) or [])
    if q and not title_ids:
        for title, ids in graph.notes_by_title.items():
            if title.lower() == q_l:
                title_ids = list(ids)
                break
    if q and title_ids:
        if len(title_ids) == 1:
            consider(title_ids[0], "exact_match")
        else:
            warnings.append(f"AMBIGUOUS_TITLE:{q}")
            for nid in title_ids:
                consider(nid, "exact_match")
    if project and not graph_only:
        for nid in graph.notes_by_project.get(project, []):
            consider(nid, "same_project")
    if project and graph_only and not q:
        for nid in graph.notes_by_project.get(project, []):
            consider(nid, "same_project")
    if q and not graph_only:
        for tag, ids in graph.notes_by_tag.items():
            if tag.lower() == q_l:
                for nid in ids:
                    consider(nid, "tag_match")
        for rec in graph.notes_by_id.values():
            blob = f"{rec.title} {rec.body} {' '.join(rec.tags)} {rec.project}".lower()
            lexical = q_l in rec.title.lower() or q_l in rec.id.lower()
            if tokens and all(tok in blob for tok in tokens):
                lexical = True
            if q_l and lexical:
                if rec.id not in seeds:
                    consider(rec.id, "lexical_match")

    visited: Dict[str, Tuple[str, int]] = {}
    queue: deque[str] = deque()
    for nid, reason in sorted(seeds.items(), key=lambda item: (REASON_ORDER[item[1]], item[0])):
        visited[nid] = (reason, 0)
        queue.append(nid)

    while queue:
        nid = queue.popleft()
        hop = visited[nid][1]
        if hop >= max_hops:
            continue
        for link in graph.outbound_links.get(nid, []):
            if link.target_id and link.target_id not in visited:
                visited[link.target_id] = ("outbound_link", hop + 1)
                queue.append(link.target_id)
        for link in graph.inbound_links.get(nid, []):
            if link.source_id not in visited:
                visited[link.source_id] = ("inbound_link", hop + 1)
                queue.append(link.source_id)

    ranked = sorted(
        visited.items(),
        key=lambda item: (REASON_ORDER.get(item[1][0], 9), item[1][1], item[0]),
    )
    truncated = False
    if len(ranked) > max_notes:
        truncated = True
        warnings.append("CONTEXT_LIMIT_EXCEEDED")
        ranked = ranked[:max_notes]

    target_ids = {nid for nid, reason in seeds.items() if reason == "exact_match"}
    if not include_target:
        ranked = [item for item in ranked if item[0] not in target_ids or item[1][1] > 0]
    notes_out: List[Dict[str, Any]] = []
    provenance: List[Dict[str, Any]] = []
    links_out: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    total = 0
    target_truncated = False
    for nid, (reason, hop) in ranked:
        rec = graph.notes_by_id[nid]
        body = rec.body
        body_cut = bool(max_body_chars and len(body) > max_body_chars)
        if body_cut:
            body = body[:max_body_chars]
            truncated = True
            warnings.append("CONTEXT_LIMIT_EXCEEDED")
            if nid in target_ids:
                target_truncated = True
        row = rec.summary(include_body=True, max_body_chars=max_body_chars)
        row["body"] = body
        row["reason"] = reason
        row["hop"] = hop
        size = len(json.dumps(row, ensure_ascii=False))
        if max_total_chars and total + size > max_total_chars:
            truncated = True
            warnings.append("CONTEXT_LIMIT_EXCEEDED")
            if nid in target_ids:
                target_truncated = True
            break
        total += size
        notes_out.append(row)
        provenance.append({"note_id": nid, "reason": reason, "hop": hop})
        for link in graph.outbound_links.get(nid, []):
            links_out.append(link.as_dict())
            if link.target_id is None:
                unresolved.append(link.target_title)

    # stable unique unresolved
    seen_u = []
    for title in unresolved:
        if title not in seen_u:
            seen_u.append(title)
    if truncated and "bounded result; not complete" not in warnings:
        warnings.append("bounded result; not complete")
    # de-dupe warnings, keep order
    seen_w = []
    for item in warnings:
        if item not in seen_w:
            seen_w.append(item)
    return ContextResult(
        query=query,
        project=project,
        notes=notes_out,
        links=links_out,
        provenance=provenance,
        unresolved_links=seen_u,
        warnings=seen_w,
        truncated=truncated,
        root=graph.root,
        corpus_note_count=len(graph.notes_by_id),
        unresolved_count=len(seen_u),
        target_truncated=target_truncated,
        algorithm=CONTEXT_ALGORITHM,
        index_source=meta["index_source"],
    )


def format_context_packet(result: ContextResult) -> str:
    lines = [
        f"# Project: {result.project or '(none)'}",
        f"# Query: {result.query or '(none)'}",
        f"# truncated={str(result.truncated).lower()}",
    ]
    for note in result.notes:
        lines.append(f"## {note.get('id')} ({note.get('reason')})")
        body = str(note.get("body") or "").strip()
        if body:
            lines.append(body)
    lines.append("## provenance")
    for row in result.provenance:
        lines.append(f"- {row.get('note_id')}: {row.get('reason')} hop={row.get('hop')}")
    if result.warnings:
        lines.append("## warnings")
        for warning in result.warnings:
            lines.append(f"- {warning}")
    return "\n".join(lines) + "\n"
