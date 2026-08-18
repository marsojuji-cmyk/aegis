"""Collect consecutive billed provider receipts. Does not authorize routing.

Reads API keys from process env only. Refuses chat-leaked denylisted keys.
Does not estimate USD from tokens. Missing billed USD fails closed.
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
COST_SOURCE = "nous_api"
WORKFLOW = "provider_receipt_window"
KEY_ENVS = ("NOUS_API_KEY", "AGIS_API_KEY")
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


def probe(environ: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Ready check. Does not call the provider and does not write the ledger."""
    loaded = load_api_key(environ)
    return {
        "ok": loaded["ok"],
        "ready_to_execute": loaded["ok"],
        "blocked": loaded["blocked"],
        "env_name": loaded["env_name"],
        "reason": loaded["reason"],
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
    loaded = load_api_key(environ)
    if not loaded["ok"]:
        status.update({k: loaded[k] for k in ("ok", "blocked", "reason", "env_name")})
        return status
    if count <= 0:
        status["ok"] = False
        status["blocked"] = "invalid_count"
        status["reason"] = "count must be > 0"
        return status
    base = (os.environ.get("NOUS_BASE_URL") or os.environ.get("AGIS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
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
    for idx in range(count):
        body = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Reply with one word: ok"}],
            "max_tokens": 8,
            "temperature": 0,
        }
        started = time.perf_counter()
        try:
            payload = poster(url, headers, body)
        except Exception as exc:
            errors.append(f"call_{idx}: {exc}")
            break
        elapsed = time.perf_counter() - started
        usd = extract_billed_usd(payload if isinstance(payload, Mapping) else {})
        if usd is None:
            errors.append(f"call_{idx}: billed USD missing; refusing token-rate estimate")
            break
        status_label = "verified_zero" if usd == 0.0 else "observed"
        request_id = ""
        if isinstance(payload, Mapping):
            request_id = str(payload.get("id") or "")
        row = record_outcome(
            task_id=f"RR037-{stamp}-{idx:02d}",
            variant="baseline",
            accepted=True,
            elapsed_seconds=elapsed,
            cost_usd=usd,
            cost_status=status_label,
            cost_source=COST_SOURCE,
            workflow=WORKFLOW,
            notes=f"model={model_id} request_id={request_id}".strip(),
        )
        written.append(
            {
                "task_id": row["task_id"],
                "cost_usd": row["cost_usd"],
                "cost_status": row["cost_status"],
                "cost_source": row["cost_source"],
            }
        )
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
