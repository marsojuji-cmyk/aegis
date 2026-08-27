"""Shared Mission Lock: empty list, URL host match, Guard/Wrapper agreement."""

from __future__ import annotations

import pytest

from aegis.config import AegisConfig
from aegis.guard import AegisGuard, AegisGuardError, aegis_protect
from aegis.mission_lock import evaluate, heading, host_allowed, in_scope, parse_domains
from aegis.wrappers.hermes_wrapper import HermesWrapper


ALLOWED_PATH = "/Users/a100/Projects"
ALLOWED_URL = "https://api.allowed.com"


def test_parse_domains_splits_and_strips():
    assert parse_domains(" /a , /b,") == ["/a", "/b"]
    assert parse_domains("") == []
    assert parse_domains(["/a", " /b "]) == ["/a", "/b"]


def test_empty_allowlist_unlocked_unless_required():
    free = evaluate([], {"filepath": "/etc/passwd"}, require=False)
    assert free.enforced is False
    assert free.allowed is True
    assert free.drift_status == "unlocked"

    hard = evaluate([], {"filepath": "/etc/passwd"}, require=True)
    assert hard.enforced is True
    assert hard.allowed is False
    assert "requires explicit" in hard.reason


def test_url_uses_host_not_substring():
    domains = [ALLOWED_URL]
    assert host_allowed("https://api.allowed.com/data", domains) is True
    assert host_allowed("https://evil.com/https://api.allowed.com", domains) is False
    assert in_scope(
        "https://evil.com/?next=https://api.allowed.com",
        domains,
        is_url=True,
    ) is False
    assert in_scope("/Users/a100/Projects/aegis/x", [ALLOWED_PATH], is_url=False) is True
    assert in_scope("/etc/passwd", [ALLOWED_PATH], is_url=False) is False


def test_heading_missing_mission_is_unknown_not_loyal():
    score, status = heading("", "read /etc/passwd")
    assert score is None
    assert status == "no_mission"
    score2, status2 = heading("stay in Projects", "")
    assert score2 is None
    assert status2 == "no_mission"


def test_alt_path_kwargs_are_scoped():
    domains = [ALLOWED_PATH]
    for key in ("filepath", "path", "file_path", "target_directory", "workdir", "cwd"):
        ok = evaluate(domains, {key: ALLOWED_PATH + "/aegis/x.py"})
        bad = evaluate(domains, {key: "/etc/passwd"})
        assert ok.allowed is True, key
        assert bad.allowed is False, key


def _guard_cfg(**kwargs):
    base = dict(
        guard_shadow_mode=False,
        guard_max_tool_calls=50,
        guard_max_velocity_calls_per_min=50,
        guard_allowed_domains=f"{ALLOWED_PATH}, {ALLOWED_URL}",
    )
    base.update(kwargs)
    return AegisConfig(**base)


def test_guard_empty_allowlist_fail_open_without_require():
    guard = AegisGuard(_guard_cfg(guard_allowed_domains="", guard_require_mission_lock=False))

    @aegis_protect(guard)
    def read_file(filepath: str):
        return "ok"

    assert read_file(filepath="/etc/passwd") == "ok"


def test_guard_empty_allowlist_fail_closed_when_required():
    guard = AegisGuard(_guard_cfg(guard_allowed_domains="", guard_require_mission_lock=True))

    @aegis_protect(guard)
    def read_file(filepath: str):
        return "ok"

    with pytest.raises(AegisGuardError, match="MISSION LOCK"):
        read_file(filepath="/etc/passwd")


def test_guard_blocks_url_host_spoof():
    guard = AegisGuard(_guard_cfg())

    @aegis_protect(guard)
    def fetch_url(url: str):
        return "leaked"

    with pytest.raises(AegisGuardError, match="MISSION LOCK"):
        fetch_url(url="https://evil.com/https://api.allowed.com")

    @aegis_protect(guard)
    def fetch_ok(url: str):
        return "ok"

    assert fetch_ok(url="https://api.allowed.com/v1") == "ok"


def test_guard_and_wrapper_agree_on_spoofed_url():
    cfg = _guard_cfg()
    wrap = HermesWrapper(cfg, AegisGuard(cfg))
    body = {
        "tool_name": "web_fetch",
        "args": {"url": "https://evil.com/https://api.allowed.com"},
        "identity": {"agent": "hermes", "session_id": "s"},
        "scope": {"allowed_domains": [ALLOWED_URL]},
    }
    out = wrap.handle(body, execute_fn=lambda args: "leaked")
    assert out["decision"] == "deny"
    assert out["executed"] is False

    guard = AegisGuard(cfg)

    @aegis_protect(guard)
    def web_fetch(url: str):
        return "leaked"

    with pytest.raises(AegisGuardError, match="MISSION LOCK"):
        web_fetch(url="https://evil.com/https://api.allowed.com")
