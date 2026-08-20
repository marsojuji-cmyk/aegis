"""
Universal Aegis pipeline: preflight → model → shrink/store/reuse → ledger.

Used by `aegis run` and the router daemon.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import dataclasses
import hashlib
from typing import Any, Dict, List, Optional, Sequence

from aegis import DEFAULT_BATCH_WORKERS, MAX_BATCH_WORKERS, __version__
from aegis.ledger import record
from aegis.output_lane import activate_output, land_output, mode_default_profile
from aegis.output_store import store_stats
from aegis.preflight import run_preflight
from aegis.providers import ProviderSpec, detect_provider, list_providers
from aegis.router_client import chat_completion
from aegis.guard import AegisGuard, AegisGuardContext, aegis_protect

class AegisConfigurationError(Exception):
    pass

VALID_ENVIRONMENTS = {"test", "development", "staging", "production"}

def resolve_environment() -> str:
    import os
    import sys
    configured = os.environ.get("AEGIS_ENV")
    if configured:
        if configured not in VALID_ENVIRONMENTS:
            raise AegisConfigurationError(f"Unsupported AEGIS_ENV: {configured}")
        return configured

    if "pytest" in sys.modules:
        return "test"

    raise AegisConfigurationError("AEGIS_ENV must be explicitly set outside pytest")



@dataclass
class RunResult:
    ok: bool
    provider: str
    model: str
    content: str
    shrunk: str
    pack_id: Optional[str]
    output_id: Optional[str]
    output_reuse: bool
    mock: bool
    error: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "provider": self.provider,
            "model": self.model,
            "content": self.content,
            "shrunk": self.shrunk,
            "pack_id": self.pack_id,
            "output_id": self.output_id,
            "output_reuse": self.output_reuse,
            "mock": self.mock,
            "error": self.error,
            "usage": self.usage,
            "meta": self.meta,
        }


def run_pipeline(
    *,
    task: str,
    model: str = "mock",
    provider: str = "",
    paths: Optional[Sequence[str]] = None,
    mode: str = "explore",
    targets: Optional[Sequence[str]] = None,
    system: str = "",
    prompt: str = "",
    profile: Optional[str] = None,
    skip_preflight: bool = False,
    dry_run: bool = False,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> RunResult:
    """
    Full route:
      1) optional preflight pack (files)
      2) activate output lane
      3) call model (or mock)
      4) land + shrink/store/reuse unified outputs
      5) ledger everything
    """
    paths = list(paths or [])
    targets = list(targets or [])
    from aegis.routing import apply_route

    route_meta = apply_route(model=model, mode=mode)
    model = str(route_meta.get("model") or model)
    prov = detect_provider(model, provider)
    # Enforce output discipline before dispatch. Post-hoc shrinking cannot
    # recover tokens or context already spent by the upstream model.
    cfg = None
    try:
        from aegis.config import load_config

        cfg = load_config()
        max_tokens = max(1, min(int(max_tokens), int(cfg.output_hard_max)))
    except Exception:  # noqa: BLE001
        max_tokens = max(1, int(max_tokens))
    pack_id = None
    preflight_meta: Dict[str, Any] = {"route": route_meta}

    if paths and not skip_preflight:
        pf = run_preflight(
            paths=paths,
            task=task,
            mode=mode,
            targets=targets,
            strict=False,
            output_profile=profile,
            no_output=False,
            dry_run=dry_run,
            recover=True,
        )
        pack_id = pf.pack_id
        preflight_meta = {
            "preflight_ok": pf.ok,
            "mode_used": pf.mode_used,
            "quality": pf.quality_grade,
            "reserve": pf.reserve_signal,
            "recovered": pf.recovered,
            "route": route_meta,
        }
        if not pf.ok and pf.reserve_signal == "hard_stop":
            return RunResult(
                ok=False,
                provider=prov.name,
                model=model,
                content="",
                shrunk="",
                pack_id=pack_id,
                output_id=None,
                output_reuse=False,
                mock=True,
                error="reserve hard_stop — pipeline aborted",
                meta=preflight_meta,
            )
    else:
        # still open output lane
        try:
            activate_output(
                profile=profile or mode_default_profile(mode),
                mode=mode,
                task=task,
                dry_run=dry_run,
                pack_id=None,
            )
        except Exception:
            pass

    # Build messages
    messages: List[Dict[str, str]] = []
    sys_parts = []
    if system:
        sys_parts.append(system)
    from aegis.agent_contract import AEGIS_AGENT_CONTRACT

    sys_parts.append(AEGIS_AGENT_CONTRACT)
    # cross-model memory (any provider can benefit)
    try:
        from aegis.config import load_config
        from aegis.memory import memory_context_block

        if load_config().auto_memory:
            mem = memory_context_block(task or prompt, project="aegis", limit=6)
            if mem:
                sys_parts.append(mem)
    except Exception:  # noqa: BLE001
        pass
    # inject pack bento if preflight ran
    if pack_id and not skip_preflight and paths:
        from aegis.pack_cache import load_pack

        cached = load_pack(pack_id) or {}
        comps = cached.get("bento_components") or []
        if comps:
            ctx = [f"## {c.get('path')}\n{c.get('payload_snippet')}" for c in comps]
            sys_parts.append("AEGIS PACK CONTEXT:\n" + "\n\n".join(ctx))
    messages.append({"role": "system", "content": "\n\n".join(sys_parts)})
    user_content = prompt or task
    messages.append({"role": "user", "content": user_content})
    from aegis.context_governor import meter_context

    context = meter_context(
        messages, expected_output_tokens=max_tokens,
        capacity=int(getattr(cfg, "context_window_tokens", 258_000)),
    )
    preflight_meta["context"] = context.as_dict()
    if context.band in {"transfer", "red"}:
        # Do not spend the final context reserve.  This is deliberately a
        # provisional receipt: only a human/agent that checks the work may
        # promote facts into the verified list for the next task.
        from aegis.context_governor import persist_capsule, state_capsule

        capsule = state_capsule(
            objective=task or prompt,
            constraints=["Resume from this receipt; re-open only cited evidence."],
            artifacts=([{"kind": "pack", "id": pack_id}] if pack_id else []),
            current_defect="Context reserve reached; no model request dispatched.",
            next_action="Start a clean task, inspect the cited pack, then continue.",
            verification_status="provisional",
        )
        capsule_path = persist_capsule(capsule)
        preflight_meta["transfer_capsule"] = str(capsule_path)
        return RunResult(
            ok=False, provider=prov.name, model=model, content="", shrunk="",
            pack_id=pack_id, output_id=None, output_reuse=False,
            mock=prov.kind == "mock",
            error=("context transfer — start clean task from provisional capsule"
                   if context.band == "transfer"
                   else "context red — recover from last verified capsule"),
            meta=preflight_meta,
        )

    # Build AegisGuardContext
    import uuid
    import os
    import sys
    req_id = str(uuid.uuid4())
    
    # 1. run_id: explicit AEGIS_RUN_ID, otherwise process-level UUID
    _PROCESS_RUN_ID = os.environ.get("AEGIS_RUN_ID")
    if not _PROCESS_RUN_ID:
        _PROCESS_RUN_ID = getattr(sys.modules[__name__], '_LOCAL_PROCESS_ID', None)
        if not _PROCESS_RUN_ID:
            _PROCESS_RUN_ID = str(uuid.uuid4())
            setattr(sys.modules[__name__], '_LOCAL_PROCESS_ID', _PROCESS_RUN_ID)
            
    run_id = _PROCESS_RUN_ID

    # 2. environment: explicit AEGIS_ENV, otherwise validated default
    try:
        env = resolve_environment()
    except AegisConfigurationError as exc:
        return RunResult(
            ok=False,
            provider=prov.name,
            model=model,
            content="",
            shrunk="",
            pack_id=pack_id,
            output_id=None,
            output_reuse=False,
            mock=prov.kind == "mock",
            error=str(exc),
            meta=preflight_meta,
        )

    ctx_dict = dataclasses.asdict(AegisGuardContext(
        request_id=req_id,
        run_id=run_id,
        environment=env,
        provider=prov.name
    ))
    
    # Contract checks: assert only safe boundary fields exist
    assert ctx_dict.get("request_id"), "request_id is required"
    assert ctx_dict.get("run_id"), "run_id is required"
    assert ctx_dict.get("environment") in {"test", "development", "staging", "production"}, f"Invalid environment: {env}"
    assert "raw_prompt" not in ctx_dict, "raw_prompt must not be passed to guard context"
    assert "provider_response" not in ctx_dict, "provider_response must not be passed to guard context"

    ctx = AegisGuardContext(**ctx_dict)
    guard = AegisGuard(cfg, context=ctx)
    protected_chat = aegis_protect(
        guard=guard,
        tool_name="chat_completion",
        mission_scope="model_inference",
        budget_category="model_calls"
    )(chat_completion)

    try:
        if dry_run:
            resp = protected_chat(
                detect_provider("mock", "mock"),
                model="mock",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                use_responses=bool(getattr(cfg, "openai_use_responses", True)),
                service_tier=str(getattr(cfg, "openai_service_tier", "auto")),
                prompt_cache_key=hashlib.sha256(messages[0]["content"].encode("utf-8")).hexdigest()[:32],
            )
            # stamp intended provider in meta
            resp["provider"] = prov.name
            resp["model"] = resolve_model_safe(prov, model)
        else:
            resp = protected_chat(
                prov,
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                use_responses=bool(getattr(cfg, "openai_use_responses", True)),
                service_tier=str(getattr(cfg, "openai_service_tier", "auto")),
                prompt_cache_key=hashlib.sha256(messages[0]["content"].encode("utf-8")).hexdigest()[:32],
            )
    except Exception as exc:  # noqa: BLE001
        record(
            kind="router_error",
            task=f"run:{prov.name}:{task[:40]}",
            mode="router",
            raw_in=0,
            processed_in=0,
            meta={"error": str(exc), "provider": prov.name, "model": model},
        )
        return RunResult(
            ok=False,
            provider=prov.name,
            model=model,
            content="",
            shrunk="",
            pack_id=pack_id,
            output_id=None,
            output_reuse=False,
            mock=prov.kind == "mock",
            error=str(exc),
            meta=preflight_meta,
        )

    content = resp.get("content") or ""
    # Land through shrink/store/reuse (unified ~/.aegis/outputs/)
    try:
        landed = land_output(
            body=content,
            summary=f"router:{prov.name}:{task[:60]}",
            task=f"run:{prov.name}:{task[:40]}",
            dry_run=dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        landed = {
            "output_id": None,
            "output_reuse": False,
            "shrunk_text": content,
            "error": str(exc),
        }

    usage = resp.get("usage") or {}
    # book router txn for visibility
    if not dry_run:
        raw_out = int(usage.get("completion_tokens") or max(1, len(content) // 4))
        observed = not bool(resp.get("mock"))
        record(
            kind="router_run",
            task=f"run:{prov.name}:{task[:40]}",
            mode="router",
            raw_in=int(usage.get("prompt_tokens") or 0),
            processed_in=int(usage.get("prompt_tokens") or 0),
            raw_out=raw_out,
            processed_out=raw_out,
            source="provider_observed" if observed else "local_counterfactual",
            request_id=resp.get("request_id"),
            meta={
                "provider": prov.name,
                "model": resp.get("model"),
                "pack_id": pack_id,
                "output_id": landed.get("output_id"),
                "output_reuse": landed.get("output_reuse"),
                "mock": resp.get("mock"),
                "cached_tokens": int(usage.get("cached_tokens") or 0),
                "cache_write_tokens": int(usage.get("cache_write_tokens") or 0),
                "reasoning_tokens": int(usage.get("reasoning_tokens") or 0),
                **preflight_meta,
            },
        )

    # auto-capture cross-model memory from successful runs
    try:
        from aegis.config import load_config
        from aegis.memory import auto_capture_from_run

        if load_config().auto_memory:
            auto_capture_from_run(
                task=task,
                provider=str(resp.get("provider") or prov.name),
                model=str(resp.get("model") or model),
                pack_id=pack_id,
                shrunk=str(landed.get("shrunk_text") or "")[:200],
                ok=True,
            )
    except Exception:  # noqa: BLE001
        pass

    return RunResult(
        ok=True,
        provider=resp.get("provider") or prov.name,
        model=str(resp.get("model") or model),
        content=content,
        shrunk=str(landed.get("shrunk_text") or content),
        pack_id=pack_id,
        output_id=landed.get("output_id"),
        output_reuse=bool(landed.get("output_reuse")),
        mock=bool(resp.get("mock")),
        usage=usage,
        meta={
            **preflight_meta,
            "request_id": req_id,
            "run_id": run_id,
            "store": store_stats(),
            "landed": {
                k: landed.get(k)
                for k in (
                    "tokens_saved",
                    "bytes_raw",
                    "bytes_shrunk",
                    "output_reuse",
                )
            },
        },
    )


def resolve_model_safe(prov: ProviderSpec, model: str) -> str:
    from aegis.providers import resolve_model

    return resolve_model(prov, model)


def run_batch(
    jobs: List[Dict[str, Any]],
    *,
    max_workers: int = DEFAULT_BATCH_WORKERS,
) -> List[RunResult]:
    """
    Concurrent multi-model runs (default DEFAULT_BATCH_WORKERS, cap MAX_BATCH_WORKERS).
    Each job is kwargs for run_pipeline.
    Budget-aware mode may soft-cap workers when burn is warn/critical.
    """
    requested = int(max_workers or DEFAULT_BATCH_WORKERS)
    try:
        from aegis.burn import budget_aware_workers

        requested = min(requested, budget_aware_workers(requested))
    except Exception:  # noqa: BLE001
        pass
    workers = max(1, min(requested, MAX_BATCH_WORKERS))
    results: List[Optional[RunResult]] = [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(run_pipeline, **job): idx for idx, job in enumerate(jobs)
        }
        for fut in as_completed(futs):
            idx = futs[fut]
            try:
                results[idx] = fut.result()
            except Exception as exc:  # noqa: BLE001
                results[idx] = RunResult(
                    ok=False,
                    provider="?",
                    model="?",
                    content="",
                    shrunk="",
                    pack_id=None,
                    output_id=None,
                    output_reuse=False,
                    mock=True,
                    error=str(exc),
                )
    return [r for r in results if r is not None]


def router_status() -> Dict[str, Any]:
    from aegis.ledger import generate_report
    from aegis.output_store import store_stats
    from aegis.paths import outputs_dir

    rep = generate_report()
    return {
        "version": __version__,
        "providers": list_providers(),
        "outputs": store_stats(),
        "reuse_hit_rate_percent": rep.get("reuse_hit_rate_percent"),
        "pack_reuse_aim_percent": 50.0,
        "reserve_signal": rep.get("reserve_signal"),
        "remaining_pct": rep.get("remaining_weekly_capacity_percent"),
        "max_concurrent_default": DEFAULT_BATCH_WORKERS,
        "max_concurrent_cap": MAX_BATCH_WORKERS,
        "unified_output_dir": str(outputs_dir()),
        "endpoints": [
            "POST /v1/chat/completions",
            "POST /v1/aegis/run",
            "POST /v1/aegis/intel/tick",
            "GET /v1/aegis/status",
            "GET /v1/aegis/budget",
            "GET /v1/aegis/ledger",
            "GET /v1/aegis/intel",
            "GET /v1/aegis/forecast",
            "GET /v1/aegis/burn",
            "GET /v1/aegis/budget-aware",
            "GET /v1/aegis/continuity",
            "GET /v1/models",
            "GET /healthz",
        ],
    }
