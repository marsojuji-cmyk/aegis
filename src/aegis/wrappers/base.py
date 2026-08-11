"""
Shared intercept layer: validate → (preflight) → call → shrink/store/reuse → ledger.

Both OpenAI and Anti-Gravity wrappers call into this so every completion
hits the same unified output index and economics path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from aegis.output_lane import activate_output, land_output, mode_default_profile
from aegis.output_store import store_stats
from aegis.quality import evaluate_pack
from aegis.router_pipeline import RunResult, run_pipeline


def validate_messages(messages: Sequence[Dict[str, Any]]) -> List[str]:
    """Return list of validation errors (empty = ok)."""
    errs: List[str] = []
    if not messages:
        errs.append("messages empty")
        return errs
    roles = {m.get("role") for m in messages if isinstance(m, dict)}
    if "user" not in roles and "assistant" not in roles:
        # allow system-only only if content present
        has_content = any((m.get("content") or "").strip() for m in messages)
        if not has_content:
            errs.append("no user/assistant content")
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            errs.append(f"message[{i}] not object")
            continue
        if m.get("role") not in ("system", "user", "assistant", "tool", "function"):
            errs.append(f"message[{i}] bad role {m.get('role')!r}")
    return errs


def last_user_text(messages: Sequence[Dict[str, Any]]) -> str:
    for m in reversed(list(messages)):
        if isinstance(m, dict) and m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                # multimodal: join text parts
                parts = []
                for p in c:
                    if isinstance(p, dict) and p.get("type") == "text":
                        parts.append(p.get("text") or "")
                    elif isinstance(p, str):
                        parts.append(p)
                return "\n".join(parts)
    return ""


def system_text(messages: Sequence[Dict[str, Any]]) -> str:
    parts = []
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "system":
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                parts.append(c)
    return "\n\n".join(parts)


def intercept_and_route(
    *,
    provider: str,
    model: str,
    messages: Sequence[Dict[str, Any]],
    task: str = "",
    paths: Optional[Sequence[str]] = None,
    mode: str = "explore",
    targets: Optional[Sequence[str]] = None,
    profile: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    dry_run: bool = False,
    skip_preflight: bool = False,
    skip_validate: bool = False,
) -> Dict[str, Any]:
    """
    Full Aegis intercept for any provider-shaped chat request.

    Returns OpenAI-compatible completion dict + aegis extras.
    """
    errs = [] if skip_validate else validate_messages(messages)
    if errs:
        return {
            "ok": False,
            "error": {"message": "; ".join(errs), "type": "aegis_validation"},
            "aegis": {"validated": False, "errors": errs},
        }

    user = last_user_text(messages)
    system = system_text(messages)
    task_s = (task or user[:80] or f"{provider}-chat").strip()
    prof = profile or mode_default_profile(mode)

    # Optional: activate lane early for estimate bookkeeping
    try:
        activate_output(profile=prof, mode=mode, task=task_s, dry_run=dry_run)
    except Exception:
        pass

    result: RunResult = run_pipeline(
        task=task_s,
        model=model,
        provider=provider,
        paths=list(paths or []),
        mode=mode,
        targets=list(targets or []),
        system=system,
        prompt=user or task_s,
        profile=prof,
        skip_preflight=skip_preflight or not paths,
        dry_run=dry_run,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    content = result.shrunk or result.content or ""
    openai_body = {
        "id": f"aegis-{result.output_id or 'wrap'}",
        "object": "chat.completion",
        "model": result.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop" if result.ok else "error",
            }
        ],
        "usage": result.usage
        or {
            "prompt_tokens": 0,
            "completion_tokens": max(1, len(content) // 4),
            "total_tokens": max(1, len(content) // 4),
        },
        "aegis": {
            "ok": result.ok,
            "provider": result.provider,
            "wrapper": provider,
            "pack_id": result.pack_id,
            "output_id": result.output_id,
            "output_reuse": result.output_reuse,
            "mock": result.mock,
            "error": result.error,
            "store": store_stats(),
            "validated": True,
            "pipeline": [
                "validate",
                "preflight",
                "model",
                "shrink",
                "store",
                "reuse",
                "ledger",
            ],
            "meta": result.meta,
        },
    }
    if not result.ok:
        openai_body["error"] = {
            "message": result.error or "pipeline failed",
            "type": "aegis_pipeline",
        }
    return openai_body


def wrap_raw_completion(
    *,
    provider: str,
    content: str,
    model: str = "",
    profile: str = "brief",
    pack_id: Optional[str] = None,
    task: str = "",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Post-hoc intercept: already have model output → shrink/store/reuse/ledger only.
    Used when outer stack calls the model itself and hands body to Aegis.
    """
    try:
        activate_output(
            profile=profile,
            mode="explore",
            task=task or f"wrap:{provider}",
            dry_run=dry_run,
            pack_id=pack_id,
        )
    except Exception:
        pass
    landed = land_output(
        body=content,
        summary=f"wrap:{provider}:{task[:40]}",
        task=f"wrap:{provider}",
        dry_run=dry_run,
    )
    shrunk = landed.get("shrunk_text") or content
    return {
        "id": f"aegis-{landed.get('output_id') or 'raw'}",
        "object": "chat.completion",
        "model": model or provider,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": shrunk},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": int(landed.get("actual_out") or len(shrunk) // 4),
        },
        "aegis": {
            "ok": True,
            "provider": provider,
            "wrapper": provider,
            "mode": "post_hoc",
            "output_id": landed.get("output_id"),
            "output_reuse": landed.get("output_reuse"),
            "pack_id": pack_id,
            "store": store_stats(),
            "pipeline": ["shrink", "store", "reuse", "ledger"],
        },
    }
