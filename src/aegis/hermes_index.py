"""Hermes workspace file index. Reads and index writes go through HermesWrapper.

Does not change shadow mode, production domains, billing, or models.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from aegis.config import load_config
from aegis.guard import AegisGuard
from aegis.paths import ensure_home, hermes_index_dir, hermes_index_files_path
from aegis.wrappers.hermes_wrapper import HermesWrapper, redact_excerpt

INDEX_VERSION = "1.0"
DEFAULT_ROOT = "/Users/ektar/workspace"
PREVIEW_LINES = 8
MAX_PREVIEW_BYTES = 4096

COMMON_IGNORES = (
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    ".env",
    ".env.*",
    "credentials.json",
    "secrets.json",
    "*.pem",
    "*.key",
)

TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".py",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".rst",
    ".org",
    ".csv",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_gitignore(root: Path) -> List[str]:
    path = root / ".gitignore"
    if not path.is_file():
        return []
    patterns: List[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        patterns.append(line.rstrip("/"))
    return patterns


def _ignored(rel: str, name: str, patterns: Sequence[str]) -> bool:
    for pattern in patterns:
        pat = pattern[2:] if pattern.startswith("**/") else pattern
        if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat):
            return True
    return False


def _is_text(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES


def _wrapper(domains: Sequence[str]) -> HermesWrapper:
    # Batch index only. Does not write production config.toml.
    scoped = replace(
        load_config(),
        guard_allowed_domains=",".join(domains),
        guard_max_tool_calls=10_000,
        guard_max_velocity_calls_per_min=10_000,
    )
    return HermesWrapper(scoped, AegisGuard(scoped))


def _gate_read(wrapper: HermesWrapper, filepath: str, domains: Sequence[str]) -> Dict[str, Any]:
    def _read(args: Dict[str, Any]) -> str:
        raw = Path(args["filepath"]).read_text(encoding="utf-8", errors="replace")
        return "\n".join(raw.splitlines()[:PREVIEW_LINES])

    return wrapper.handle(
        {
            "tool_name": "read_file",
            "args": {"filepath": filepath},
            "identity": {"agent": "hermes", "session_id": "hermes-index"},
            "scope": {"allowed_domains": list(domains)},
            "environment": "hermes-index",
        },
        execute_fn=_read,
    )


def _gate_write(wrapper: HermesWrapper, filepath: str, content: str, domains: Sequence[str]) -> Dict[str, Any]:
    return wrapper.handle(
        {
            "tool_name": "write_file",
            "args": {"filepath": filepath, "content": content},
            "identity": {"agent": "hermes", "session_id": "hermes-index"},
            "scope": {"allowed_domains": list(domains)},
            "environment": "hermes-index",
        },
        execute_fn=lambda args: Path(args["filepath"]).write_text(
            args["content"], encoding="utf-8"
        ),
    )


def build_index(
    root: str = DEFAULT_ROOT,
    *,
    dest: Optional[Path] = None,
    preview_lines: int = PREVIEW_LINES,
) -> Dict[str, Any]:
    """Scan root through the AEGIS gate and write files.json."""
    ensure_home()
    root_path = Path(root).expanduser().resolve()
    dest_path = dest or hermes_index_files_path()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    root_domain = str(root_path)
    index_domain = str(dest_path.parent)
    wrapper = _wrapper([root_domain, index_domain])
    patterns = list(COMMON_IGNORES) + _load_gitignore(root_path)

    entries: List[Dict[str, Any]] = []
    reads_allowed = 0
    reads_denied = 0

    if root_path.is_dir():
        candidates = [root_path, *sorted(root_path.rglob("*"))]
    elif root_path.exists():
        candidates = [root_path]
    else:
        candidates = []

    for path in candidates:
        rel = "." if path == root_path else str(path.relative_to(root_path))
        if path != root_path and (
            _ignored(rel, path.name, patterns)
            or any(_ignored(part, part, patterns) for part in Path(rel).parts)
        ):
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        item: Dict[str, Any] = {
            "path": str(path),
            "relpath": rel,
            "type": "dir" if path.is_dir() else "file",
            "size": int(st.st_size),
            "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "ext": path.suffix.lower() if path.is_file() else "",
            "preview": None,
            "read_decision": None,
        }
        if (
            path.is_file()
            and _is_text(path)
            and st.st_size <= MAX_PREVIEW_BYTES * 4
        ):
            gated = _gate_read(wrapper, str(path), [root_domain])
            item["read_decision"] = gated.get("decision")
            if gated.get("decision") == "allow" and gated.get("executed"):
                reads_allowed += 1
                item["preview"] = redact_excerpt(gated.get("output") or "", limit=400)
            else:
                reads_denied += 1
        entries.append(item)

    payload: Dict[str, Any] = {
        "version": INDEX_VERSION,
        "root": str(root_path),
        "generated_ts": _now(),
        "file_count": sum(1 for e in entries if e["type"] == "file"),
        "dir_count": sum(1 for e in entries if e["type"] == "dir"),
        "reads_allowed": reads_allowed,
        "reads_denied": reads_denied,
        "files": entries,
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    write = _gate_write(wrapper, str(dest_path), body, [index_domain])
    payload["write_decision"] = write.get("decision")
    payload["write_executed"] = bool(write.get("executed"))
    if write.get("decision") == "allow" and write.get("executed"):
        dest_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return payload


def query_index(
    *,
    path_contains: str = "",
    file_type: str = "",
    keyword: str = "",
    dest: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    src = dest or hermes_index_files_path()
    if not src.is_file():
        return []
    data = json.loads(src.read_text(encoding="utf-8"))
    rows = list(data.get("files") or [])
    if path_contains:
        needle = path_contains.lower()
        rows = [r for r in rows if needle in str(r.get("path") or "").lower()]
    if file_type:
        rows = [r for r in rows if r.get("type") == file_type]
    if keyword:
        needle = keyword.lower()
        rows = [
            r
            for r in rows
            if needle in str(r.get("preview") or "").lower()
            or needle in str(r.get("relpath") or "").lower()
        ]
    return rows
