"""Hermes → AEGIS control gate.

Single enforceable path:
  request → normalize → ids → classify → policy/mission-lock → redact
  → fail-closed → allow|deny|require-review → execute only if permitted
  → GuardDecision audit (existing JSONL format)

Hermes middleware is fail-open on raise. This module must never raise
to block a tool; it returns a structured deny payload instead.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from aegis.config import AegisConfig, load_config
from aegis.guard import AegisGuard, AegisGuardContext

REDACTION_VERSION = "1.0"
REDACTED = "[REDACTED]"

KNOWN_AGENTS = frozenset({"hermes", "grok", "grokbuild", "antigravity"})

# Secret-bearing keys (case-insensitive, _/- ignored).
_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|authorization|auth|cookie|"
    r"private[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"bearer|session[_-]?id_token)",
    re.I,
)
_SECRET_VALUE_RE = re.compile(
    r"(?i)("
    r"sk-[A-Za-z0-9]{16,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|(?:api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+"
    r")"
)

# Explicit catalog. Unknown tool_name → deny (fail-closed).
# Names match Hermes registry.register() in hermes-agent/tools/*.
# risk: low | medium | high
# kind: fs.read | fs.write | net.search | net.fetch | net.browser | exec.shell
#       memory.write | session.read | session.write | skill.read | skill.write
#       project.read | project.write | sched.write
TOOL_CAPABILITIES: Dict[str, Dict[str, str]] = {
    "read_file": {"capability": "fs.read", "risk": "low"},
    "list_dir": {"capability": "fs.read", "risk": "low"},
    "search": {"capability": "fs.read", "risk": "low"},
    "search_files": {"capability": "fs.read", "risk": "low"},
    "write_file": {"capability": "fs.write", "risk": "medium"},
    "edit_file": {"capability": "fs.write", "risk": "medium"},
    "patch": {"capability": "fs.write", "risk": "medium"},
    "web_search": {"capability": "net.search", "risk": "medium"},
    "web_fetch": {"capability": "net.fetch", "risk": "medium"},
    "web_extract": {"capability": "net.fetch", "risk": "medium"},
    "browser": {"capability": "net.browser", "risk": "high"},
    "browse_page": {"capability": "net.browser", "risk": "high"},
    "terminal": {"capability": "exec.shell", "risk": "high"},
    "execute": {"capability": "exec.shell", "risk": "high"},
    # Hermes memory tool is write-only (add/replace/remove). Store is ~/.hermes,
    # not domain-scoped — mission lock is session scope only (R-015).
    "memory": {"capability": "memory.write", "risk": "medium"},
    "session_search": {"capability": "session.read", "risk": "low"},
    "todo": {"capability": "session.write", "risk": "medium"},
    "skills_list": {"capability": "skill.read", "risk": "low"},
    "skill_view": {"capability": "skill.read", "risk": "low"},
    "skill_manage": {"capability": "skill.write", "risk": "medium"},
    "project_list": {"capability": "project.read", "risk": "low"},
    "project_create": {"capability": "project.write", "risk": "medium"},
    "project_switch": {"capability": "project.write", "risk": "medium"},
    "hermes_notes_search": {"capability": "skill.read", "risk": "low"},
    "hermes_note_get": {"capability": "skill.read", "risk": "low"},
    "hermes_graph_neighbors": {"capability": "skill.read", "risk": "low"},
    "hermes_project_context": {"capability": "project.read", "risk": "low"},
    "hermes_resolve_context": {"capability": "skill.read", "risk": "low"},
    "cron": {"capability": "sched.write", "risk": "high"},
    "cronjob": {"capability": "sched.write", "risk": "high"},
}

_SCOPE_KEYS = (
    "filepath",
    "path",
    "file_path",
    "target_directory",
    "workdir",
    "cwd",
    "url",
)


@dataclass
class NormalizedRequest:
    request_id: str
    trace_id: str
    tool_name: str
    args: Dict[str, Any]
    agent: str
    session_id: str
    environment: str
    allowed_domains: List[str]
    capability: Optional[str]
    risk: Optional[str]


@dataclass
class GateResult:
    ok: bool
    decision: str  # allow | deny | require-review
    reason: str
    request_id: str
    trace_id: str
    tool_name: str
    capability: Optional[str]
    risk: Optional[str]
    shadow_mode: bool
    would_block: bool
    executed: bool
    output: Any = None
    redaction_version: str = REDACTION_VERSION
    policy: List[str] = field(default_factory=list)
    rule: str = "hermes"

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def redact_value(value: Any) -> Any:
    """Return a copy with secret keys/patterns replaced. Never mutates input."""
    if isinstance(value, Mapping):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if _SENSITIVE_KEY_RE.search(key.replace("-", "_")):
                out[key] = REDACTED
            else:
                out[key] = redact_value(v)
        return out
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    if isinstance(value, tuple):
        return [redact_value(v) for v in value]
    if isinstance(value, str):
        if _SECRET_VALUE_RE.search(value):
            return _SECRET_VALUE_RE.sub(REDACTED, value)
        return value
    return value


def redact_excerpt(value: Any, limit: int = 160) -> str:
    text = str(redact_value(value))
    if len(text) > limit:
        return text[:limit] + "…"
    return text


def _as_mapping(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, Mapping):
        return None
    return dict(raw)


def _domains_from(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [p.strip() for p in raw.split(",") if p.strip()]
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return [str(p).strip() for p in raw if str(p).strip()]
    return []


def classify_tool(tool_name: str) -> Tuple[Optional[str], Optional[str]]:
    spec = TOOL_CAPABILITIES.get(tool_name)
    if not spec:
        return None, None
    return spec["capability"], spec["risk"]


def _scope_values(args: Mapping[str, Any]) -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for key in _SCOPE_KEYS:
        if key in args and args[key] not in (None, ""):
            found.append((key, str(args[key])))
    return found


def _in_scope(value: str, domains: Sequence[str], *, is_url: bool) -> bool:
    if not domains:
        return False
    if is_url:
        return any(domain in value for domain in domains)
    return any(value.startswith(domain) for domain in domains)


class HermesWrapper:
    """Single AEGIS gate for Hermes tool requests."""

    def __init__(
        self,
        config: Optional[AegisConfig] = None,
        guard: Optional[AegisGuard] = None,
    ) -> None:
        self.config = config or load_config()
        self.guard = guard or AegisGuard(self.config)
        self._config_domains = _domains_from(self.config.guard_allowed_domains)

    def decide(self, raw: Any) -> GateResult:
        """Classify and apply policy. Never executes."""
        parsed = _as_mapping(raw)
        if parsed is None:
            rid, tid = str(uuid.uuid4()), str(uuid.uuid4())
            return self._result(
                ok=False,
                decision="deny",
                reason="malformed request: body must be an object",
                request_id=rid,
                trace_id=tid,
                tool_name="",
                capability=None,
                risk=None,
                would_block=True,
                executed=False,
                rule="malformed",
                policy=["malformed"],
            )

        req = self.normalize(parsed)
        self.guard.guard_context = AegisGuardContext(
            request_id=req.request_id,
            run_id=req.trace_id,
            environment=req.environment,
            provider="hermes",
        )

        if not req.tool_name or not isinstance(parsed.get("args", {}), Mapping):
            if "args" in parsed and not isinstance(parsed.get("args"), Mapping):
                reason = "malformed request: args must be an object"
            else:
                reason = "malformed request: tool_name required"
            return self._finish(
                req,
                ok=False,
                decision="deny",
                reason=reason,
                would_block=True,
                rule="malformed",
                policy=["malformed"],
            )

        if not req.agent or req.agent not in KNOWN_AGENTS:
            return self._finish(
                req,
                ok=False,
                decision="deny",
                reason="identity unknown or untrusted; fail-closed",
                would_block=True,
                rule="identity",
                policy=["identity"],
            )

        if not req.capability or not req.risk:
            return self._finish(
                req,
                ok=False,
                decision="deny",
                reason=f"unknown capability for tool {req.tool_name!r}; fail-closed",
                would_block=True,
                rule="capability",
                policy=["capability"],
            )

        if not req.allowed_domains:
            return self._finish(
                req,
                ok=False,
                decision="deny",
                reason="scope unknown; mission lock requires explicit allowed domains",
                would_block=True,
                rule="scope",
                policy=["scope"],
            )

        scope_hits = _scope_values(req.args)
        if req.capability.startswith("fs.") and not scope_hits:
            return self._finish(
                req,
                ok=False,
                decision="deny",
                reason="ambiguous fs action: path required; fail-closed",
                would_block=True,
                rule="malformed",
                policy=["ambiguous"],
            )
        if req.capability in {"net.fetch", "net.browser"} and not any(
            key == "url" for key, _ in scope_hits
        ):
            return self._finish(
                req,
                ok=False,
                decision="deny",
                reason="ambiguous net action: url required; fail-closed",
                would_block=True,
                rule="malformed",
                policy=["ambiguous"],
            )
        for key, value in scope_hits:
            if not _in_scope(value, req.allowed_domains, is_url=(key == "url")):
                return self._finish(
                    req,
                    ok=False,
                    decision="deny",
                    reason=f"out of scope: {key} not inside mission lock",
                    would_block=True,
                    rule="mission",
                    policy=["mission_lock"],
                )

        if req.risk == "high":
            return self._finish(
                req,
                ok=False,
                decision="require-review",
                reason=f"high-risk capability {req.capability} requires review",
                would_block=True,
                rule="risk",
                policy=["risk", "require-review"],
            )

        return self._finish(
            req,
            ok=True,
            decision="allow",
            reason=f"allowed {req.risk} {req.capability}",
            would_block=False,
            rule="hermes",
            policy=["allow"],
        )

    def handle(
        self,
        raw: Any,
        execute_fn: Optional[Callable[..., Any]] = None,
    ) -> Dict[str, Any]:
        """Decide, then execute only when permitted. Returns structured result."""
        result = self.decide(raw)
        may_run = result.decision == "allow" or (
            self.config.guard_shadow_mode
            and result.decision == "require-review"
            and execute_fn is not None
        )
        # Unknown / malformed / identity / out-of-scope never execute, even
        # in shadow mode. Shadow only observes high-risk review (D-011).
        if not may_run or execute_fn is None:
            return result.as_dict()

        parsed = _as_mapping(raw) or {}
        req = self.normalize(parsed)
        try:
            output = self._invoke(req, execute_fn)
        except Exception as exc:
            result.ok = False
            result.executed = False
            result.output = None
            result.reason = f"{result.reason}; execute error: {type(exc).__name__}"
            self._audit(result, req)
            return result.as_dict()

        result.executed = True
        result.output = redact_value(output) if result.decision != "allow" else output
        if result.decision != "allow":
            result.reason = f"{result.reason}; shadow executed"
        self._audit_outcome(result)
        return result.as_dict()

    def normalize(self, raw: Mapping[str, Any]) -> NormalizedRequest:
        identity = raw.get("identity") if isinstance(raw.get("identity"), Mapping) else {}
        scope = raw.get("scope") if isinstance(raw.get("scope"), Mapping) else {}
        args = raw.get("args") if isinstance(raw.get("args"), Mapping) else {}
        tool_name = str(raw.get("tool_name") or "").strip()
        request_id = str(raw.get("request_id") or "").strip() or str(uuid.uuid4())
        trace_id = str(raw.get("trace_id") or "").strip() or str(uuid.uuid4())
        agent = str(identity.get("agent") or "").strip().lower()
        session_id = str(identity.get("session_id") or "").strip()
        environment = str(raw.get("environment") or "hermes")
        domains = _domains_from(scope.get("allowed_domains"))
        if not domains:
            domains = list(self._config_domains)
        capability, risk = classify_tool(tool_name)
        return NormalizedRequest(
            request_id=request_id,
            trace_id=trace_id,
            tool_name=tool_name,
            args=dict(args),
            agent=agent,
            session_id=session_id,
            environment=environment,
            allowed_domains=domains,
            capability=capability,
            risk=risk,
        )

    def _invoke(self, req: NormalizedRequest, execute_fn: Callable[..., Any]) -> Any:
        def _call(**kwargs: Any) -> Any:
            try:
                return execute_fn(kwargs)
            except TypeError:
                return execute_fn(**kwargs)

        return self.guard.inspect_and_filter(req.tool_name, _call, **req.args)

    def _result(self, **kwargs: Any) -> GateResult:
        kwargs.setdefault("shadow_mode", bool(self.config.guard_shadow_mode))
        kwargs.setdefault("tool_name", "")
        result = GateResult(**kwargs)
        self._audit(result, None)
        return result

    def _finish(self, req: NormalizedRequest, **kwargs: Any) -> GateResult:
        kwargs.setdefault("shadow_mode", bool(self.config.guard_shadow_mode))
        kwargs.setdefault("tool_name", req.tool_name)
        kwargs.setdefault("capability", req.capability)
        kwargs.setdefault("risk", req.risk)
        kwargs.setdefault("request_id", req.request_id)
        kwargs.setdefault("trace_id", req.trace_id)
        kwargs.setdefault("executed", False)
        result = GateResult(**kwargs)
        self._audit(result, req)
        return result

    def _audit(self, result: GateResult, req: Optional[NormalizedRequest]) -> None:
        excerpt = None
        if req is not None:
            excerpt = redact_excerpt(
                {"tool": req.tool_name, "args": req.args, "agent": req.agent}
            )
        action = {
            "allow": "allow",
            "deny": "block",
            "require-review": "block",
        }.get(result.decision, "block")
        self.guard._record_decision(
            rule=result.rule,
            action=action,
            status="ok" if result.decision == "allow" else "halt",
            reason=result.reason,
            input_excerpt=excerpt,
        )

    def _audit_outcome(self, result: GateResult) -> None:
        self.guard._record_decision(
            rule="hermes",
            action="allow" if result.decision == "allow" else "block",
            status="ok" if result.executed else "halt",
            reason=result.reason,
            output_excerpt=redact_excerpt(result.output) if result.output is not None else None,
        )


def hermes_tool_request(**kwargs: Any) -> Optional[Dict[str, Any]]:
    """tool_request middleware: identity-preserving, no arg rewrite."""
    return None


def hermes_tool_execution(**kwargs: Any) -> Any:
    """tool_execution middleware. Must not raise — Hermes is fail-open."""
    wrapper = HermesWrapper()
    request = {
        "tool_name": kwargs.get("tool_name") or "",
        "args": kwargs.get("args") if isinstance(kwargs.get("args"), Mapping) else {},
        "identity": {
            "agent": "hermes",
            "session_id": str(kwargs.get("session_id") or ""),
            "task_id": str(kwargs.get("task_id") or ""),
        },
        "request_id": str(
            kwargs.get("api_request_id") or kwargs.get("tool_call_id") or ""
        ),
        "trace_id": str(kwargs.get("turn_id") or kwargs.get("session_id") or ""),
        "environment": str(kwargs.get("environment") or "hermes"),
    }
    if isinstance(kwargs.get("scope"), Mapping):
        request["scope"] = dict(kwargs["scope"])
    next_call = kwargs.get("next_call")
    result = wrapper.handle(request, execute_fn=next_call if callable(next_call) else None)
    if result.get("executed"):
        return result.get("output")
    return {
        "ok": False,
        "blocked_by": "aegis",
        "decision": result.get("decision"),
        "reason": result.get("reason"),
        "request_id": result.get("request_id"),
        "trace_id": result.get("trace_id"),
        "redaction_version": REDACTION_VERSION,
    }


def register(ctx: Any) -> None:
    """Hermes plugin entry: wrap tool request/execution through this gate."""
    ctx.register_middleware("tool_request", hermes_tool_request)
    ctx.register_middleware("tool_execution", hermes_tool_execution)
