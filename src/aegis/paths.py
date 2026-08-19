"""Resolve ~/.aegis (or $AEGIS_HOME) data plane paths.

Portable product home: $AEGIS_HOME wins. Else $AEGIS_USER namespaces
~/.aegis/users/<id>. Else ~/.aegis. No host-absolute defaults.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def sanitize_user(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "", (raw or "").strip())
    return cleaned[:64] or "default"


def aegis_home() -> Path:
    raw = os.environ.get("AEGIS_HOME")
    if raw:
        return Path(raw).expanduser().resolve()
    user = (os.environ.get("AEGIS_USER") or "").strip()
    base = Path.home() / ".aegis"
    if user:
        return (base / "users" / sanitize_user(user)).resolve()
    return base


def ensure_home() -> Path:
    home = aegis_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "packs").mkdir(exist_ok=True)
    (home / "outputs").mkdir(exist_ok=True)
    (home / "kernel").mkdir(exist_ok=True)
    return home


def config_path() -> Path:
    return aegis_home() / "config.toml"


def ledger_path() -> Path:
    return aegis_home() / "ledger.jsonl"


def fund_path() -> Path:
    return aegis_home() / "fund.json"


def ideas_path() -> Path:
    return aegis_home() / "ideas.jsonl"


def sprints_path() -> Path:
    return aegis_home() / "sprints.jsonl"


def packs_dir() -> Path:
    return aegis_home() / "packs"


def outputs_dir() -> Path:
    return aegis_home() / "outputs"


def daemon_pid_path() -> Path:
    return aegis_home() / "router.pid"


def daemon_log_path() -> Path:
    return aegis_home() / "router.log"


def daemon_meta_path() -> Path:
    return aegis_home() / "router.meta.json"


def legacy_import_flag() -> Path:
    return aegis_home() / ".legacy_imported"


def memory_path() -> Path:
    return aegis_home() / "memory.jsonl"


def intel_state_path() -> Path:
    return aegis_home() / "intel_state.json"


def cache_stats_path() -> Path:
    return aegis_home() / "cache_stats.json"


def reports_dir() -> Path:
    return aegis_home() / "reports"


def burn_events_path() -> Path:
    return aegis_home() / "burn_events.jsonl"


def burn_state_path() -> Path:
    return aegis_home() / "burn_state.json"


def budget_state_path() -> Path:
    return aegis_home() / "budget_aware_state.json"


def budget_events_path() -> Path:
    return aegis_home() / "budget_aware_events.jsonl"


def continuity_dir() -> Path:
    return aegis_home() / "continuity"


def continuity_events_path() -> Path:
    return aegis_home() / "continuity_events.jsonl"


def context_capsules_dir() -> Path:
    return aegis_home() / "context-capsules"


def outcomes_path() -> Path:
    """Append-only evidence for matched baseline/governed workflow runs."""
    return aegis_home() / "outcomes.jsonl"


def hermes_token_pairs_path() -> Path:
    """Append-only Hermes gated/ungated token-pair records. No inferred savings."""
    return aegis_home() / "hermes_token_pairs.jsonl"


def hermes_index_dir() -> Path:
    return aegis_home() / "hermes_index"


def hermes_index_files_path() -> Path:
    return hermes_index_dir() / "files.json"


def hermes_index_notes_path() -> Path:
    return hermes_index_dir() / "notes.json"


def hermes_index_graph_path() -> Path:
    return hermes_index_dir() / "graph.json"


def hermes_index_projects_path() -> Path:
    return hermes_index_dir() / "projects.json"


def manifest_path() -> Path:
    return aegis_home() / "MANIFEST.json"


def kernel_dir() -> Path:
    return aegis_home() / "kernel"


def kernel_procs_path() -> Path:
    return kernel_dir() / "procs.jsonl"


def kernel_stats_path() -> Path:
    return kernel_dir() / "stats.json"


def backups_dir() -> Path:
    return aegis_home() / "backups"


def close_clock_path() -> Path:
    """14-day Path A operator-owner clock. Local JSON, not a CRM."""
    return aegis_home() / "close_clock.json"
