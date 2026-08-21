"""AEGIS Middleware Guard for tool enforcement."""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
import uuid
import os
import sys
from typing import Any, Callable, Dict, List, Optional

from aegis.config import AegisConfig
from aegis.mission_lock import evaluate as evaluate_mission_lock, parse_domains
from pathlib import Path

_ACTIVE_GUARD: Optional[AegisGuard] = None

# Persistent guard log path (JSONL format)
GUARD_LOG_PATH = Path.home() / ".aegis" / "guard_log.jsonl"


def rotate_guard_log(log_path: Path, if_larger_mb: Optional[float] = None) -> Dict[str, Any]:
    """Rotate a guard JSONL log to a timestamped archive plus manifest.

    Writers open/append/close per event (see _persist_decision), so the live
    log is recreated on the next write — no daemon restart required.
    """
    result: Dict[str, Any] = {"rotated": False, "log_path": str(log_path)}
    if not log_path.exists() or log_path.stat().st_size == 0:
        result["reason"] = "empty_log"
        return result

    size_bytes = log_path.stat().st_size
    result["size_bytes"] = size_bytes
    if if_larger_mb is not None and size_bytes < if_larger_mb * 1024 * 1024:
        result["reason"] = "below_threshold"
        return result

    sha = hashlib.sha256()
    lines = 0
    with open(log_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
            lines += chunk.count(b"\n")

    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    n = 1
    while True:
        suffix = "" if n == 1 else f"-{n}"
        archive = log_path.with_name(f"guard_log.v2-archive-{ts}{suffix}.jsonl")
        manifest_path = log_path.with_name(f"guard_log.v2-split-{ts}{suffix}.manifest.json")
        if not archive.exists() and not manifest_path.exists():
            break
        n += 1

    os.replace(log_path, archive)
    manifest = {
        "source_sha256": sha.hexdigest(),
        "source_lines": lines,
        "source_bytes": size_bytes,
        "archive_file": archive.name,
        "rotation_reason": "aegis guard rotate",
        "timestamp_utc": ts,
        "tool_version": "1.0",
        "paused_concurrent_writers": False,
        "writer_model": "per-event open/append/close; fresh live log auto-created on next write",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    result.update({
        "rotated": True,
        "archive": str(archive),
        "manifest": str(manifest_path),
        "source_lines": lines,
        "source_sha256": manifest["source_sha256"],
    })
    return result


class AegisGuardError(Exception):
    """Raised when an AEGIS middleware guard policy is violated."""


@dataclasses.dataclass
class GuardDecision:
    event_id: str
    request_id: str
    run_id: str
    environment: str
    provider: str
    rule: str
    action: str
    would_block: bool
    shadow_mode: bool
    timestamp: float
    timestamp_iso: str
    reason: str
    redaction_version: str
    score: Optional[float] = None
    input_excerpt: Optional[str] = None
    output_excerpt: Optional[str] = None

@dataclasses.dataclass
class AegisGuardContext:
    request_id: str = "unknown"
    run_id: str = "unknown"
    environment: str = "unknown"
    provider: str = "unknown"


@dataclasses.dataclass
class AegisState:
    total_calls: int = 0
    call_timestamps: List[float] = dataclasses.field(default_factory=list)
    recent_calls: List[str] = dataclasses.field(default_factory=list)
    decisions: List[GuardDecision] = dataclasses.field(default_factory=list)


class AegisGuard:
    def __init__(self, config: AegisConfig, context: Optional[AegisGuardContext] = None) -> None:
        self.config = config
        self.guard_context = context or AegisGuardContext()
        self.state = AegisState()
        self._allowed_domains: List[str] = parse_domains(config.guard_allowed_domains)
        
        # Register in global state for CLI inspection
        global _ACTIVE_GUARD
        _ACTIVE_GUARD = self

    def _record_decision(
        self,
        rule: str,
        action: str,
        status: str,
        reason: str,
        score: Optional[float] = None,
        input_excerpt: Optional[str] = None,
        output_excerpt: Optional[str] = None
    ) -> None:
        ts = time.time()
        shadow = self.config.guard_shadow_mode
        if rule == "signal":
            shadow = getattr(self.config, "guard_signal_shadow_mode", shadow)
        
        would_block = (action == "block" or status == "halt")

        decision = GuardDecision(
            event_id=str(uuid.uuid4()),
            request_id=self.guard_context.request_id,
            run_id=self.guard_context.run_id,
            environment=self.guard_context.environment,
            provider=self.guard_context.provider,
            rule=rule,
            action=action,
            would_block=would_block,
            shadow_mode=shadow,
            timestamp=ts,
            timestamp_iso=time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(ts)),
            reason=reason,
            redaction_version="1.0",
            score=score,
            input_excerpt=input_excerpt,
            output_excerpt=output_excerpt
        )
        self.state.decisions.append(decision)
        
        # Trim ring buffer
        limit = self.config.guard_audit_limit
        if len(self.state.decisions) > limit:
            self.state.decisions = self.state.decisions[-limit:]
            
        # Persist to disk (JSONL format)
        self._persist_decision(decision)

    def _persist_decision(self, decision: GuardDecision) -> None:
        """Append decision to persistent JSONL log file."""
        # Enforce redaction contract before serialization
        assert decision.redaction_version is not None, "redaction_version missing"
        assert isinstance(decision.redaction_version, str), "redaction_version must be a string"
        
        # Serialize the record
        serialized_record = json.dumps(dataclasses.asdict(decision))
        
        # Assert no sensitive payload properties leaked into the serialized shape
        assert "raw_prompt" not in serialized_record, "raw_prompt leaked into telemetry"
        assert "provider_payload" not in serialized_record, "provider_payload leaked into telemetry"

        try:
            # Ensure directory exists
            GUARD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            with open(GUARD_LOG_PATH, "a") as f:
                f.write(serialized_record + "\n")
        except Exception as e:
            # Don't fail on logging errors, but warn
            import sys
            print(f"[AEGIS GUARD] Warning: Failed to persist decision log: {e}", file=sys.stderr)

    def _check_budget_and_velocity(self, tool_name: str) -> None:
        """Rule 1: Guard Budget and Velocity."""
        if self.state.total_calls >= self.config.guard_max_tool_calls:
            msg = f"Global tool budget ({self.config.guard_max_tool_calls}) exhausted."
            self._record_decision(rule="budget", action="block", status="halt", reason=msg)
            if not self.config.guard_shadow_mode:
                raise AegisGuardError(f"[AEGIS BLOCK - RULE 1 (BUDGET)]: {msg}")

        # Check velocity
        now = time.time()
        self.state.call_timestamps = [t for t in self.state.call_timestamps if now - t < 60]
        if len(self.state.call_timestamps) >= self.config.guard_max_velocity_calls_per_min:
            msg = f"Per-minute velocity limit ({self.config.guard_max_velocity_calls_per_min}/min) exceeded."
            self._record_decision(rule="budget", action="block", status="halt", reason=msg)
            if not self.config.guard_shadow_mode:
                raise AegisGuardError(f"[AEGIS BLOCK - RULE 1 (VELOCITY)]: {msg}")
            
        self._record_decision(rule="budget", action="allow", status="ok", reason=f"Tool {tool_name} under budget")

    def _check_loops(self, tool_name: str, args: tuple[Any, ...], kwargs: Dict[str, Any]) -> None:
        """Rule 1b: Loop detection."""
        # Simple deterministic signature
        # Convert values to strings safely for sorting/hashing
        safe_kwargs = {k: str(v) for k, v in kwargs.items()}
        safe_args = [str(a) for a in args]
        signature = f"{tool_name}:args={json.dumps(safe_args)}:kwargs={json.dumps(safe_kwargs, sort_keys=True)}"
        self.state.recent_calls.append(signature)
        
        # Keep only the last 3
        self.state.recent_calls = self.state.recent_calls[-3:]
        
        if len(self.state.recent_calls) == 3:
            if self.state.recent_calls[0] == self.state.recent_calls[1] == self.state.recent_calls[2]:
                msg = f"Tool '{tool_name}' invoked 3 times consecutively with identical arguments."
                self._record_decision(rule="loop", action="block", status="halt", reason=msg, input_excerpt=signature[:100])
                if not self.config.guard_shadow_mode:
                    raise AegisGuardError(f"[AEGIS BLOCK - RULE 1 (LOOP)]: Infinite loop detected! {msg}")
                
        self._record_decision(rule="loop", action="allow", status="ok", reason=f"Tool {tool_name} not looping")

    def _check_mission_lock(self, tool_name: str, kwargs: Dict[str, Any]) -> None:
        """Rule 3: Mission Lock Enforcement (shared with HermesWrapper)."""
        require = bool(getattr(self.config, "guard_require_mission_lock", False))
        mission = str(getattr(self.config, "guard_mission", "") or "")
        verdict = evaluate_mission_lock(
            self._allowed_domains,
            kwargs,
            mission=mission,
            tool_name=tool_name,
            require=require,
        )
        excerpt = str(list(kwargs.values())[:1])[:120]
        if not verdict.allowed:
            self._record_decision(
                rule="mission",
                action="block",
                status="halt",
                reason=verdict.reason,
                score=verdict.drift_score,
                input_excerpt=excerpt,
            )
            if not self.config.guard_shadow_mode:
                raise AegisGuardError(
                    f"[AEGIS BLOCK - RULE 3 (MISSION LOCK)]: {verdict.reason}"
                )
            return
        self._record_decision(
            rule="mission",
            action="allow" if verdict.drift_status != "quarantine" else "warn",
            status="ok" if verdict.allowed else "halt",
            reason=verdict.reason,
            score=verdict.drift_score,
            input_excerpt=excerpt,
        )
        if (
            require
            and verdict.drift_status == "quarantine"
            and not self.config.guard_shadow_mode
        ):
            raise AegisGuardError(
                f"[AEGIS BLOCK - RULE 3 (MISSION LOCK)]: {verdict.reason}"
            )

    def evaluate_signal(self, text: str, keywords: List[str]) -> float:
        """Calculate a deterministic signal score (0.0 to 1.0) for a block of text."""
        if not text:
            return 0.0

        # Normalize whitespace for analysis
        cleaned = " ".join(text.split())
        words = cleaned.split()
        if not words:
            return 0.0

        score = 1.0

        # 1. Length / Density penalty (penalize extremely long outputs with little structure)
        # We'll just slightly penalize massive length, as length itself isn't terrible if it has info.
        if len(text) > self.config.guard_max_output_length * 2:
            score -= 0.2

        # 2. Repetition Ratio (n-gram repeats or word entropy)
        # A simple check: ratio of unique words to total words
        unique_words = set(words)
        vocab_ratio = len(unique_words) / len(words)
        if vocab_ratio < 0.2:
            score -= 0.5  # Heavy penalty for spam/repetition
        elif vocab_ratio < 0.4:
            score -= 0.2

        # 3. Keyword Preservation boost
        if keywords:
            lower_text = text.lower()
            keyword_hits = sum(1 for kw in keywords if kw.lower() in lower_text)
            if keyword_hits > 0:
                score += 0.4 * (keyword_hits / len(keywords))

        return max(0.0, min(1.0, score))

    def _preserve_signal(self, tool_name: str, raw_output: Any) -> Any:
        """Rule 2: Signal Preservation."""
        is_dict = isinstance(raw_output, dict)
        
        # If it's a dict, we only prune the "content" field if present.
        text_to_evaluate = str(raw_output.get("content", "")) if is_dict else str(raw_output)
        
        # Fast path for short output
        max_len = self.config.guard_max_output_length
        if len(text_to_evaluate) <= max_len:
            return raw_output
        
        # Normalize whitespace
        cleaned = " ".join(text_to_evaluate.split())
        
        # It's over max_len, evaluate it
        keywords = [kw.strip() for kw in self.config.guard_signal_preserve_keywords.split(",") if kw.strip()]
        score = self.evaluate_signal(cleaned, keywords)

        if score >= self.config.guard_min_signal_score and keywords:
            # High signal, try to preserve the area around keywords
            # For simplicity, we just grab snippets around the first keyword found
            for kw in keywords:
                idx = cleaned.lower().find(kw.lower())
                if idx != -1:
                    start = max(0, idx - max_len // 2)
                    end = min(len(cleaned), idx + max_len // 2)
                    snippet = cleaned[start:end]
                    prefix = "..." if start > 0 else ""
                    suffix = "..." if end < len(cleaned) else ""
                    self._record_decision(rule="signal", action="prune", status="pruned", reason="Preserved critical snippet", score=score)
                    if getattr(self.config, "guard_signal_shadow_mode", self.config.guard_shadow_mode):
                        return raw_output
                    pruned_text = f"[AEGIS SIGNAL PRUNED (Score: {score:.2f})]: Preserved critical snippet:\n{prefix}{snippet}{suffix}"
                    if is_dict:
                        raw_output["content"] = pruned_text
                        return raw_output
                    return pruned_text

        # Otherwise, just hard-truncate
        truncated = cleaned[:max_len]
        self._record_decision(rule="signal", action="prune", status="pruned", reason="Hard truncated repetitive/filler output", score=score)
        if getattr(self.config, "guard_signal_shadow_mode", self.config.guard_shadow_mode):
            return raw_output
        pruned_text = (
            f"[AEGIS SIGNAL PRUNED (Score: {score:.2f})]: Output exceeded {max_len} chars. "
            f"Truncated content:\n{truncated}..."
        )
        if is_dict:
            raw_output["content"] = pruned_text
            return raw_output
        return pruned_text

    def _check_memory_provenance(self, tool_name: str, kwargs: Dict[str, Any]) -> None:
        """Rule 4: durable memory writes require admitted record id when enforced."""
        if not bool(getattr(self.config, "guard_require_memory_provenance", False)):
            return
        if tool_name != "memory" and "memory_record_id" not in kwargs:
            return
        record_id = str(kwargs.get("memory_record_id") or kwargs.get("record_id") or "")
        if not record_id:
            msg = "durable memory write requires memory_record_id from aegis memory admit"
            self._record_decision(rule="memory", action="block", status="halt", reason=msg)
            if not self.config.guard_shadow_mode:
                raise AegisGuardError(f"[AEGIS BLOCK - RULE 4 (MEMORY)]: {msg}")
            return
        try:
            from aegis.memory_admit import list_records

            known = {str(r.get("id")) for r in list_records(limit=500)}
            if record_id not in known:
                msg = f"memory_record_id not admitted: {record_id}"
                self._record_decision(rule="memory", action="block", status="halt", reason=msg)
                if not self.config.guard_shadow_mode:
                    raise AegisGuardError(f"[AEGIS BLOCK - RULE 4 (MEMORY)]: {msg}")
                return
        except Exception as exc:
            msg = f"memory provenance check failed: {type(exc).__name__}"
            self._record_decision(rule="memory", action="block", status="halt", reason=msg)
            if not self.config.guard_shadow_mode:
                raise AegisGuardError(f"[AEGIS BLOCK - RULE 4 (MEMORY)]: {msg}")
            return
        self._record_decision(rule="memory", action="allow", status="ok", reason="admitted record id present")

    def _check_agency(self, tool_name: str, kwargs: Dict[str, Any]) -> None:
        """Rule 5: bounded agency mode gate."""
        from aegis.agency import gate_decision, normalize_mode
        from aegis.wrappers.hermes_wrapper import classify_tool

        capability, risk = classify_tool(tool_name)
        if not capability:
            self._record_decision(
                rule="agency",
                action="allow",
                status="ok",
                reason="tool not in Hermes catalog; agency check skipped",
            )
            return
        mode = normalize_mode(getattr(self.config, "guard_agency_mode", "assistive"))
        durable = tool_name == "memory" and bool(
            getattr(self.config, "guard_require_memory_provenance", False)
        )
        decision, reason = gate_decision(
            mode, capability, risk, durable_memory=durable,
        )
        if decision == "allow":
            self._record_decision(rule="agency", action="allow", status="ok", reason=reason)
            return
        if decision == "require-review":
            self._record_decision(rule="agency", action="block", status="halt", reason=reason)
            if not self.config.guard_shadow_mode:
                raise AegisGuardError(f"[AEGIS BLOCK - RULE 5 (AGENCY)]: {reason}")
            return
        self._record_decision(rule="agency", action="block", status="halt", reason=reason)
        if not self.config.guard_shadow_mode:
            raise AegisGuardError(f"[AEGIS BLOCK - RULE 5 (AGENCY)]: {reason}")

    def inspect_and_filter(self, tool_name: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
        """Execute the tool through the AEGIS middleware."""
        self._check_budget_and_velocity(tool_name)
        self._check_mission_lock(tool_name, kwargs)
        self._check_memory_provenance(tool_name, kwargs)
        self._check_agency(tool_name, kwargs)
        self._check_loops(tool_name, args, kwargs)

        self.state.total_calls += 1
        self.state.call_timestamps.append(time.time())

        # Execute
        try:
            raw_result = func(*args, **kwargs)
        except Exception as e:
            # We don't record raw exceptions in guard unless they are AegisGuardError
            raise e

        return self._preserve_signal(tool_name, raw_result)


def aegis_protect(
    guard: Optional[AegisGuard] = None,
    tool_name: str = "",
    mission_scope: str = "",
    budget_category: str = "",
) -> Callable[..., Any]:
    """Decorator to wrap any Python tool function with AEGIS governance."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            global _ACTIVE_GUARD
            active_guard = guard or _ACTIVE_GUARD
            if not active_guard:
                from aegis.config import AegisConfig
                # Just use default config if no active guard exists
                active_guard = AegisGuard(AegisConfig())
                _ACTIVE_GUARD = active_guard

            name = tool_name or func.__name__
            return active_guard.inspect_and_filter(name, func, *args, **kwargs)
        return wrapper

    if callable(guard):
        func = guard
        guard = None
        return decorator(func)
    return decorator
