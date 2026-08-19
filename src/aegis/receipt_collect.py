"""Collect consecutive billed provider receipts. Does not authorize routing.

Reads API keys from process env, or bills via local Hermes OAuth proxy when running.
Refuses chat-leaked denylisted keys. Does not estimate USD from tokens.
Missing billed USD fails closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional

from aegis.cost_provenance import provider_window_status
from aegis.outcomes import outcome_report, record_outcome

DEFAULT_BASE_URL = "https://inference-api.nousresearch.com/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
DEFAULT_COUNT = 5
DEFAULT_PAIRS = 10
COST_SOURCE = "nous_api"
WORKFLOW = "provider_receipt_window"
PAIR_WORKFLOW = "matched_provider_pairs"
KEY_ENVS = ("NOUS_API_KEY", "AGIS_API_KEY")
HERMES_PROXY_HOST = os.environ.get("AEGIS_HERMES_PROXY_HOST", "127.0.0.1")
HERMES_PROXY_PORT = int(os.environ.get("AEGIS_HERMES_PROXY_PORT", "8645"))
HERMES_PROXY_TOKEN = "aegis-local"
HERMES_PROXY_BASE = f"http://{HERMES_PROXY_HOST}:{HERMES_PROXY_PORT}/v1"
# SHA-256 of a Nous key pasted into chat 2026-08-18. Plaintext is not stored.
BURNED_KEY_SHA256 = frozenset(
    {
        "127150bd3170821d0e5c55efa33eab9bae896d7f3b82c6b1e7d3c80335a80c1e",
    }
)
COST_FIELDS = ("cost", "total_cost", "cost_usd", "total_cost_usd")
PostJson = Callable[[str, Mapping[str, str], Mapping[str, Any]], Dict[str, Any]]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def extract_billed_usd(payload: Mapping[str, Any]) -> Optional[float]:
    """Return billed USD from the provider body. Token counts are not a bill."""
    usage = payload.get("usage")
    blobs: List[Any] = [payload, usage]
    if isinstance(usage, Mapping):
        blobs.append(usage.get("cost_details"))
    for blob in blobs:
        if not isinstance(blob, Mapping):
            continue
        for key in COST_FIELDS:
            raw = blob.get(key)
            if isinstance(raw, bool) or raw is None:
                continue
            if isinstance(raw, (int, float)):
                return max(0.0, float(raw))
            if isinstance(raw, str):
                try:
                    return max(0.0, float(raw.strip()))
                except ValueError:
                    continue
    return None


def load_api_key(
    environ: Optional[Mapping[str, str]] = None,
    *,
    burned: Optional[frozenset] = None,
) -> Dict[str, Any]:
    """Locate a non-denylisted env key. Never returns the secret to callers of probe."""
    env = environ if environ is not None else os.environ
    denylist = burned if burned is not None else BURNED_KEY_SHA256
    found_env = ""
    found_key = ""
    for name in KEY_ENVS:
        value = str(env.get(name) or "").strip()
        if value:
            found_env = name
            found_key = value
            break
    if not found_key:
        return {
            "ok": False,
            "blocked": "missing_key",
            "env_name": "",
            "key": "",
            "reason": "set NOUS_API_KEY or AGIS_API_KEY in process env; do not paste keys into chat",
        }
    if _sha256_text(found_key) in denylist:
        return {
            "ok": False,
            "blocked": "burned_key",
            "env_name": found_env,
            "key": "",
            "reason": "env key matches a chat-leaked denylist hash; rotate and export the new key",
        }
    return {
        "ok": True,
        "blocked": "",
        "env_name": found_env,
        "key": found_key,
        "reason": "",
    }


def _proxy_ready(host: str = HERMES_PROXY_HOST, port: int = HERMES_PROXY_PORT, timeout: float = 1.5) -> bool:
    """True when Hermes OAuth proxy accepts OpenAI-compatible requests."""
    url = f"http://{host}:{port}/v1/models"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {HERMES_PROXY_TOKEN}",
            "User-Agent": "curl/8.7.1",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError):
        return False


def resolve_billing_client(
    environ: Optional[Mapping[str, str]] = None,
    *,
    burned: Optional[frozenset] = None,
) -> Dict[str, Any]:
    """Env API key first; else Hermes proxy bearer (any token accepted locally)."""
    loaded = load_api_key(environ, burned=burned)
    env = environ if environ is not None else os.environ
    base = (env.get("NOUS_BASE_URL") or env.get("AGIS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    if loaded["ok"]:
        return {
            **loaded,
            "base_url": base,
            "via": "env_key",
            "cost_source": COST_SOURCE,
        }
    proxy_base = (env.get("AEGIS_HERMES_PROXY_BASE") or HERMES_PROXY_BASE).rstrip("/")
    host = env.get("AEGIS_HERMES_PROXY_HOST", HERMES_PROXY_HOST)
    port = int(env.get("AEGIS_HERMES_PROXY_PORT", HERMES_PROXY_PORT))
    if _proxy_ready(str(host), port):
        return {
            "ok": True,
            "blocked": "",
            "env_name": "hermes_proxy",
            "key": HERMES_PROXY_TOKEN,
            "reason": "",
            "base_url": proxy_base,
            "via": "hermes_proxy",
            "cost_source": COST_SOURCE,
        }
    return {**loaded, "base_url": base, "via": "none", "cost_source": COST_SOURCE}


def probe(environ: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Ready check. Does not call the provider and does not write the ledger."""
    loaded = resolve_billing_client(environ)
    reason = loaded["reason"]
    if loaded["via"] == "hermes_proxy":
        reason = "billing via Hermes proxy (hermes proxy start --provider nous)"
    return {
        "ok": loaded["ok"],
        "ready_to_execute": loaded["ok"],
        "blocked": loaded["blocked"],
        "env_name": loaded["env_name"],
        "reason": reason,
        "billing_via": loaded.get("via"),
        "provider": "nous",
        "model": os.environ.get("AEGIS_RECEIPT_MODEL", DEFAULT_MODEL),
        "count": DEFAULT_COUNT,
        "cost_source": COST_SOURCE,
        "routing_authorized": False,
        "rows_written": 0,
    }


def _post_json(
    url: str, headers: Mapping[str, str], body: Mapping[str, Any], timeout: float = 60.0
) -> Dict[str, Any]:
    merged = {
        "User-Agent": "curl/8.7.1",
        "Accept": "application/json",
        **dict(headers),
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(dict(body)).encode("utf-8"),
        headers=merged,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} {url}: {err_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"connect failed {url}: {exc}") from exc


def _row_summary(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": row["task_id"],
        "variant": row.get("variant"),
        "cost_usd": row["cost_usd"],
        "cost_status": row["cost_status"],
        "cost_source": row["cost_source"],
        "elapsed_seconds": row.get("elapsed_seconds"),
    }


def _bill_and_record(
    poster: PostJson,
    url: str,
    headers: Mapping[str, str],
    model_id: str,
    *,
    task_id: str,
    variant: str,
    workflow: str,
) -> Dict[str, Any]:
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with one word: ok"}],
        "max_tokens": 8,
        "temperature": 0,
    }
    started = time.perf_counter()
    payload = poster(url, headers, body)
    elapsed = time.perf_counter() - started
    usd = extract_billed_usd(payload if isinstance(payload, Mapping) else {})
    if usd is None:
        raise RuntimeError("billed USD missing; refusing token-rate estimate")
    status_label = "verified_zero" if usd == 0.0 else "observed"
    request_id = ""
    if isinstance(payload, Mapping):
        request_id = str(payload.get("id") or "")
    return record_outcome(
        task_id=task_id,
        variant=variant,
        accepted=True,
        elapsed_seconds=elapsed,
        cost_usd=usd,
        cost_status=status_label,
        cost_source=COST_SOURCE,
        workflow=workflow,
        notes=f"model={model_id} request_id={request_id}".strip(),
    )


def collect_receipts(
    *,
    execute: bool = False,
    count: int = DEFAULT_COUNT,
    model: str = "",
    environ: Optional[Mapping[str, str]] = None,
    post_json: Optional[PostJson] = None,
) -> Dict[str, Any]:
    """Probe by default. --execute bills `count` tiny completions and records them.

    routing_authorized is always false. Ready window is a precondition only.
    """
    status = probe(environ)
    status["count"] = count
    if model.strip():
        status["model"] = model.strip()
    if not execute:
        status["mode"] = "probe"
        return status
    status["mode"] = "execute"
    if not status["ok"]:
        return status
    loaded = resolve_billing_client(environ)
    if not loaded["ok"]:
        status.update({k: loaded[k] for k in ("ok", "blocked", "reason", "env_name")})
        return status
    if count <= 0:
        status["ok"] = False
        status["blocked"] = "invalid_count"
        status["reason"] = "count must be > 0"
        return status
    base = str(loaded["base_url"]).rstrip("/")
    url = base + "/chat/completions"
    model_id = status["model"]
    poster = post_json or (lambda u, h, b: _post_json(u, h, b))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    written: List[Dict[str, Any]] = []
    errors: List[str] = []
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {loaded['key']}",
    }
    status["billing_via"] = loaded.get("via")
    for idx in range(count):
        try:
            row = _bill_and_record(
                poster, url, headers, model_id,
                task_id=f"RR037-{stamp}-{idx:02d}",
                variant="baseline",
                workflow=WORKFLOW,
            )
        except Exception as exc:
            errors.append(f"call_{idx}: {exc}")
            break
        written.append(_row_summary(row))
    window = provider_window_status(limit=DEFAULT_COUNT)
    report = outcome_report()
    status["ok"] = len(written) == count and not errors
    status["rows_written"] = len(written)
    status["rows"] = written
    status["errors"] = errors
    status["provider_window_ready"] = window["provider_window_ready"]
    status["trustworthy_for_routing"] = window["trustworthy_for_routing"]
    status["routing_authorized"] = False
    status["outcome_routing_authorized"] = bool(report.get("routing_authorized"))
    if not status["ok"] and not status.get("blocked"):
        status["blocked"] = "incomplete_window"
        status["reason"] = errors[-1] if errors else "wrote fewer than requested billed rows"
    return status


def collect_matched_pairs(
    *,
    execute: bool = False,
    pairs: int = DEFAULT_PAIRS,
    model: str = "",
    governed_model: str = "",
    environ: Optional[Mapping[str, str]] = None,
    post_json: Optional[PostJson] = None,
) -> Dict[str, Any]:
    """Bill baseline+governed for N tasks. Does not authorize routing.

    Cost delta is observed, not staged. Optional governed_model may be cheaper.
    Uses workflow matched_provider_pairs so incomplete production pairs stay isolated.
    """
    status = probe(environ)
    status["count"] = pairs
    status["pairs"] = pairs
    status["workflow"] = PAIR_WORKFLOW
    if model.strip():
        status["model"] = model.strip()
    status["governed_model"] = governed_model.strip() or status["model"]
    if not execute:
        status["mode"] = "probe"
        return status
    status["mode"] = "execute_pairs"
    if not status["ok"]:
        return status
    loaded = resolve_billing_client(environ)
    if not loaded["ok"]:
        status.update({k: loaded[k] for k in ("ok", "blocked", "reason", "env_name")})
        return status
    if pairs <= 0:
        status["ok"] = False
        status["blocked"] = "invalid_count"
        status["reason"] = "pairs must be > 0"
        return status
    base = str(loaded["base_url"]).rstrip("/")
    url = base + "/chat/completions"
    baseline_id = status["model"]
    governed_id = status["governed_model"]
    poster = post_json or (lambda u, h, b: _post_json(u, h, b))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    written: List[Dict[str, Any]] = []
    errors: List[str] = []
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {loaded['key']}",
    }
    status["billing_via"] = loaded.get("via")
    for idx in range(pairs):
        task_id = f"MP039-{stamp}-{idx:02d}"
        for variant, model_id in (("baseline", baseline_id), ("governed", governed_id)):
            try:
                row = _bill_and_record(
                    poster, url, headers, model_id,
                    task_id=task_id, variant=variant, workflow=PAIR_WORKFLOW,
                )
            except Exception as exc:
                errors.append(f"{task_id}/{variant}: {exc}")
                break
            written.append(_row_summary(row))
        if errors:
            break
    window = provider_window_status(limit=DEFAULT_COUNT)
    report = outcome_report(workflow=PAIR_WORKFLOW)
    status["ok"] = len(written) == pairs * 2 and not errors
    status["rows_written"] = len(written)
    status["rows"] = written
    status["errors"] = errors
    status["paired_tasks"] = report.get("paired_tasks")
    status["pair_decision"] = report.get("decision")
    status["provider_window_ready"] = window["provider_window_ready"]
    status["trustworthy_for_routing"] = window["trustworthy_for_routing"]
    status["routing_authorized"] = False
    status["outcome_routing_authorized"] = bool(report.get("routing_authorized"))
    if not status["ok"] and not status.get("blocked"):
        status["blocked"] = "incomplete_pairs"
        status["reason"] = errors[-1] if errors else "wrote fewer than requested billed pairs"
    return status
