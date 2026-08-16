"""Hermes → AEGIS gate: allow, deny, redact, fail-closed, audit, no bypass."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from aegis.cli import main
from aegis.config import AegisConfig
from aegis.guard import AegisGuard
from aegis.wrappers.hermes_wrapper import (
    KNOWN_AGENTS,
    REDACTION_VERSION,
    HermesWrapper,
    hermes_tool_execution,
    redact_value,
    register,
)


ALLOWED = "/tmp/aegis-hermes-allowed"
SECRET = "SUPER_SECRET_TOKEN_9f3c1a"


@pytest.fixture()
def log_file(tmp_path, monkeypatch):
    path = tmp_path / "guard_log.jsonl"
    monkeypatch.setattr("aegis.guard.GUARD_LOG_PATH", path)
    return path


def _cfg(*, shadow: bool = False, domains: str = ALLOWED) -> AegisConfig:
    return AegisConfig(
        guard_shadow_mode=shadow,
        guard_signal_shadow_mode=shadow,
        guard_allowed_domains=domains,
        guard_max_tool_calls=50,
        guard_max_velocity_calls_per_min=50,
    )


def _wrapper(log_file: Path, **kwargs) -> HermesWrapper:
    return HermesWrapper(_cfg(**kwargs), AegisGuard(_cfg(**kwargs)))


def _req(
    tool: str = "read_file",
    args=None,
    *,
    agent: str = "hermes",
    session_id: str = "sess-1",
    extra=None,
):
    body = {
        "tool_name": tool,
        "args": args if args is not None else {"filepath": f"{ALLOWED}/note.txt"},
        "identity": {"agent": agent, "session_id": session_id},
        "scope": {"allowed_domains": [ALLOWED]},
    }
    if extra:
        body.update(extra)
    return body


def _records(log_file: Path):
    if not log_file.exists():
        return []
    return [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]


def test_allowed_low_risk_request(log_file):
    ran = []

    def execute(args):
        ran.append(args)
        return "ok-body"

    out = _wrapper(log_file).handle(_req(), execute_fn=execute)
    assert out["decision"] == "allow"
    assert out["ok"] is True
    assert out["executed"] is True
    assert out["output"] == "ok-body"
    assert out["capability"] == "fs.read"
    assert out["risk"] == "low"
    assert out["request_id"]
    assert out["trace_id"]
    assert ran and ran[0]["filepath"].startswith(ALLOWED)
    assert out["reason"]


def test_denied_out_of_scope_request(log_file):
    ran = []
    out = _wrapper(log_file).handle(
        _req(args={"filepath": "/etc/passwd"}),
        execute_fn=lambda args: ran.append(args) or "leaked",
    )
    assert out["decision"] == "deny"
    assert out["ok"] is False
    assert out["executed"] is False
    assert out["would_block"] is True
    assert "out of scope" in out["reason"]
    assert ran == []


def test_denied_unknown_capability(log_file):
    ran = []
    out = _wrapper(log_file).handle(
        _req("launch_missiles", args={"target": "x"}),
        execute_fn=lambda args: ran.append("x") or "nope",
    )
    assert out["decision"] == "deny"
    assert out["capability"] is None
    assert "unknown capability" in out["reason"]
    assert ran == []
    assert out["executed"] is False


def test_denied_malformed_request(log_file):
    wrap = _wrapper(log_file)
    missing = wrap.handle("not-an-object", execute_fn=lambda args: "ran")
    assert missing["decision"] == "deny"
    assert "malformed" in missing["reason"]
    assert missing["executed"] is False

    no_tool = wrap.handle(_req(tool=""), execute_fn=lambda args: "ran")
    assert no_tool["decision"] == "deny"
    assert "tool_name" in no_tool["reason"]

    bad_args = wrap.handle(_req(args="plain-string"), execute_fn=lambda args: "ran")
    assert bad_args["decision"] == "deny"
    assert "args" in bad_args["reason"]


def test_sensitive_data_redaction(log_file):
    wrap = _wrapper(log_file)
    out = wrap.handle(
        _req(
            "write_file",
            args={
                "filepath": f"{ALLOWED}/out.txt",
                "api_key": SECRET,
                "content": f"token={SECRET}",
            },
        )
    )
    assert out["decision"] == "allow"
    blob = log_file.read_text()
    assert SECRET not in blob
    assert REDACTION_VERSION in blob
    redacted = redact_value({"api_key": SECRET, "ok": "x"})
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["ok"] == "x"
    for rec in _records(log_file):
        assert rec.get("redaction_version") == "1.0"
        assert "raw_prompt" not in rec
        assert "provider_payload" not in rec


def test_fail_closed_unknown_identity_scope_and_shadow(log_file):
    ran = []
    wrap_shadow = _wrapper(log_file, shadow=True)

    no_id = wrap_shadow.handle(
        {
            "tool_name": "read_file",
            "args": {"filepath": f"{ALLOWED}/a.txt"},
            "identity": {},
            "scope": {"allowed_domains": [ALLOWED]},
        },
        execute_fn=lambda args: ran.append("id") or "x",
    )
    assert no_id["decision"] == "deny"
    assert "identity" in no_id["reason"]
    assert no_id["executed"] is False

    unknown_agent = wrap_shadow.handle(
        _req(agent="untrusted-bot"),
        execute_fn=lambda args: ran.append("agent") or "x",
    )
    assert unknown_agent["decision"] == "deny"
    assert unknown_agent["executed"] is False

    no_scope = HermesWrapper(
        _cfg(shadow=True, domains=""),
        AegisGuard(_cfg(shadow=True, domains="")),
    ).handle(
        {
            "tool_name": "read_file",
            "args": {"filepath": f"{ALLOWED}/a.txt"},
            "identity": {"agent": "hermes", "session_id": "s"},
        },
        execute_fn=lambda args: ran.append("scope") or "x",
    )
    assert no_scope["decision"] == "deny"
    assert "scope unknown" in no_scope["reason"]
    assert no_scope["executed"] is False

    unknown = wrap_shadow.handle(
        _req("not_a_real_tool", args={"filepath": f"{ALLOWED}/a.txt"}),
        execute_fn=lambda args: ran.append("cap") or "x",
    )
    assert unknown["decision"] == "deny"
    assert unknown["executed"] is False
    assert ran == []


def test_audit_record_creation(log_file):
    wrap = _wrapper(log_file)
    out = wrap.handle(_req(), execute_fn=lambda args: "body")
    recs = _records(log_file)
    assert recs
    first = recs[0]
    assert first["request_id"] == out["request_id"]
    assert first["run_id"] == out["trace_id"]
    assert first["provider"] == "hermes"
    assert first["redaction_version"] == "1.0"
    assert first["reason"]
    assert first["action"] == "allow"
    deny = wrap.handle(_req("unknown_tool", args={"x": 1}))
    assert deny["decision"] == "deny"
    last = _records(log_file)[-1]
    assert last["would_block"] is True
    assert last["action"] == "block"


def test_no_direct_hermes_to_tool_bypass(log_file):
    ran = []

    def next_call(args):
        ran.append(args)
        return "executed"

    # Unknown tool via middleware must not invoke next_call and must not raise
    # (Hermes fail-open would otherwise execute the tool).
    denied = hermes_tool_execution(
        tool_name="launch_missiles",
        args={"target": "x"},
        session_id="s1",
        next_call=next_call,
        scope={"allowed_domains": [ALLOWED]},
    )
    assert ran == []
    assert denied["blocked_by"] == "aegis"
    assert denied["decision"] == "deny"
    assert "ok" in denied and denied["ok"] is False

    # High-risk in enforce mode: next_call stays cold; review is explainable.
    wrap = _wrapper(log_file, shadow=False)
    review = wrap.handle(
        _req("terminal", args={"workdir": ALLOWED, "command": "id"}),
        execute_fn=next_call,
    )
    assert review["decision"] == "require-review"
    assert review["executed"] is False
    assert ran == []
    assert "requires review" in review["reason"]

    public = {name for name, _ in inspect.getmembers(HermesWrapper) if not name.startswith("_")}
    assert "inspect_and_filter" not in public
    src = inspect.getsource(hermes_tool_execution)
    assert "wrapper.handle" in src
    assert "next_call(" not in src.replace("next_call if callable", "")


def test_shadow_mode_compatibility(log_file):
    ran = []
    wrap = _wrapper(log_file, shadow=True)
    out = wrap.handle(
        _req("terminal", args={"workdir": ALLOWED, "command": "echo hi"}),
        execute_fn=lambda args: ran.append(args) or "shadow-ran",
    )
    assert out["decision"] == "require-review"
    assert out["shadow_mode"] is True
    assert out["would_block"] is True
    assert out["executed"] is True
    assert ran
    recs = _records(log_file)
    assert any(r.get("would_block") and r.get("shadow_mode") for r in recs)

    # Out-of-scope still fail-closed in shadow (not a threshold observation).
    ran.clear()
    blocked = wrap.handle(
        _req(args={"filepath": "/etc/shadow"}),
        execute_fn=lambda args: ran.append("no") or "x",
    )
    assert blocked["decision"] == "deny"
    assert blocked["executed"] is False
    assert ran == []


def test_org_layer_catalog_and_scope(log_file):
    wrap = _wrapper(log_file)
    ran = []

    search = wrap.handle(
        _req("session_search", args={"query": "aegis gate"}),
        execute_fn=lambda args: ran.append("search") or "hits",
    )
    assert search["decision"] == "allow"
    assert search["capability"] == "session.read"
    assert search["risk"] == "low"
    assert search["executed"] is True

    mem = wrap.handle(
        _req("memory", args={"action": "add", "target": "memory", "content": "note"}),
        execute_fn=lambda args: ran.append("mem") or "saved",
    )
    assert mem["decision"] == "allow"
    assert mem["capability"] == "memory.write"
    assert mem["risk"] == "medium"
    assert mem["executed"] is True

    listed = wrap.handle(
        _req("project_list", args={}),
        execute_fn=lambda args: ran.append("proj") or [],
    )
    assert listed["decision"] == "allow"
    assert listed["capability"] == "project.read"

    manage = wrap.handle(
        _req("skill_manage", args={"action": "create", "name": "x"}),
        execute_fn=lambda args: ran.append("skill") or "ok",
    )
    assert manage["decision"] == "allow"
    assert manage["capability"] == "skill.write"
    assert manage["risk"] == "medium"

    # Empty production-style scope still fail-closed (D-011 domains unchanged).
    bare = HermesWrapper(
        _cfg(shadow=True, domains=""),
        AegisGuard(_cfg(shadow=True, domains="")),
    ).handle(
        {
            "tool_name": "session_search",
            "args": {"query": "x"},
            "identity": {"agent": "hermes", "session_id": "s"},
        },
        execute_fn=lambda args: ran.append("bare") or "x",
    )
    assert bare["decision"] == "deny"
    assert "scope unknown" in bare["reason"]
    assert bare["executed"] is False
    assert "bare" not in ran


def test_plugin_register_wires_gate():
    seen = []

    class Ctx:
        def register_middleware(self, kind, fn):
            seen.append((kind, fn))

    register(Ctx())
    kinds = {k for k, _ in seen}
    assert kinds == {"tool_request", "tool_execution"}
    exec_fn = next(fn for kind, fn in seen if kind == "tool_execution")
    assert exec_fn is hermes_tool_execution


def test_cli_wrap_hermes_json(log_file, capsys):
    payload = json.dumps(_req())
    code = main(["wrap", "--provider", "hermes", "--prompt", payload, "--json"])
    captured = capsys.readouterr()
    body = json.loads(captured.out)
    assert body["decision"] in {"allow", "deny", "require-review"}
    assert "reason" in body
    assert code in (0, 1)
    assert KNOWN_AGENTS
