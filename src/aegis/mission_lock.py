"""Shared Mission Lock: boundary (paths/URLs) plus heading (drift)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

from aegis.context_governor import evaluate_drift

PATH_KEYS = (
    "filepath",
    "path",
    "file_path",
    "target_directory",
    "workdir",
    "cwd",
)
URL_KEYS = ("url", "href", "endpoint")
ALL_SCOPE_KEYS = PATH_KEYS + URL_KEYS + ("uri",)

DRIFT_WARN = 0.4
DRIFT_QUARANTINE = 0.7


def parse_domains(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [p.strip() for p in raw.split(",") if p.strip()]
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return [str(p).strip() for p in raw if str(p).strip()]
    return []


def _is_urlish(key: str, value: str) -> bool:
    if key in URL_KEYS:
        return True
    if key == "uri":
        return "://" in value or value.startswith("//")
    return "://" in value


def scope_values(args: Mapping[str, Any]) -> List[Tuple[str, str, bool]]:
    found: List[Tuple[str, str, bool]] = []
    for key in ALL_SCOPE_KEYS:
        if key not in args or args[key] in (None, ""):
            continue
        value = str(args[key])
        found.append((key, value, _is_urlish(key, value)))
    return found


def _domain_host(entry: str) -> str:
    text = entry.strip()
    if "://" in text:
        return (urlparse(text).hostname or "").lower()
    if text.startswith("/") or text.startswith("~") or text.startswith("."):
        return ""
    return text.split("/")[0].lower()


def host_allowed(url: str, domains: Sequence[str]) -> bool:
    raw = url if "://" in url else "https://" + url.lstrip("/")
    host = (urlparse(raw).hostname or "").lower()
    if not host:
        return False
    for entry in domains:
        allowed = _domain_host(entry)
        if not allowed:
            continue
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def path_allowed(path: str, domains: Sequence[str]) -> bool:
    for entry in domains:
        if "://" in entry:
            continue
        if path.startswith(entry):
            return True
    return False


def in_scope(value: str, domains: Sequence[str], *, is_url: bool) -> bool:
    if not domains:
        return False
    if is_url:
        return host_allowed(value, domains)
    return path_allowed(value, domains)


@dataclass
class LockVerdict:
    enforced: bool
    allowed: bool
    reason: str
    drift_score: Optional[float] = None
    drift_status: str = "unlocked"  # unlocked|no_mission|ok|warn|quarantine|blocked


def heading(mission: str, next_action: str) -> Tuple[Optional[float], str]:
    if not (mission or "").strip() or not (next_action or "").strip():
        return None, "no_mission"
    score = float(evaluate_drift(mission, next_action))
    if score >= DRIFT_QUARANTINE:
        return score, "quarantine"
    if score >= DRIFT_WARN:
        return score, "warn"
    return score, "ok"


def evaluate(
    domains: Sequence[str],
    args: Mapping[str, Any],
    *,
    mission: str = "",
    tool_name: str = "",
    require: bool = False,
) -> LockVerdict:
    domains = [d for d in domains if d]
    scoped = scope_values(args)
    action = tool_name + " " + " ".join(v for _, v, _ in scoped)
    score, drift_status = heading(mission, action.strip() or tool_name)

    if not domains:
        if require:
            return LockVerdict(
                True, False, "mission lock requires explicit allowed domains",
                score, "blocked",
            )
        return LockVerdict(False, True, "mission lock unlocked (no allowlist)", score, "unlocked")

    for key, value, is_url in scoped:
        if not in_scope(value, domains, is_url=is_url):
            kind = "URL" if is_url else "path"
            return LockVerdict(
                True, False,
                f"{kind} '{value}' outside allowed mission boundaries ({key})",
                score, "blocked",
            )

    if require and drift_status == "quarantine":
        return LockVerdict(
            True, False,
            f"mission drift quarantine (score {score})",
            score, "quarantine",
        )

    if drift_status == "quarantine":
        return LockVerdict(True, True, "within allowlist; drift quarantine", score, "quarantine")
    if drift_status == "warn":
        return LockVerdict(True, True, "within allowlist; drift warn", score, "warn")
    if drift_status == "no_mission":
        return LockVerdict(True, True, "within allowed domains; no mission heading", score, "no_mission")
    return LockVerdict(True, True, "within allowed domains", score, "ok")
