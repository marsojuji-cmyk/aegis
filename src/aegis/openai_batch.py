"""OpenAI Batch/Flex request builders; submission stays explicit and auditable."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List

from aegis.router_client import _http_json


def build_response_batch(
    jobs: Iterable[Dict[str, Any]], *, model: str, service_tier: str = "flex"
) -> str:
    """Return JSONL for `/v1/responses`; caller uploads it to OpenAI Files."""
    lines: List[str] = []
    for idx, job in enumerate(jobs):
        body = {
            "model": job.get("model") or model,
            "input": job["input"],
            "max_output_tokens": int(job.get("max_output_tokens") or 800),
            "service_tier": service_tier,
        }
        if job.get("prompt_cache_key"):
            body["prompt_cache_key"] = job["prompt_cache_key"]
        lines.append(json.dumps({"custom_id": job.get("id") or f"aegis-{idx}", "method": "POST", "url": "/v1/responses", "body": body}))
    return "\n".join(lines) + ("\n" if lines else "")


def create_batch(*, input_file_id: str, completion_window: str = "24h") -> Dict[str, Any]:
    """Create a Batch API job from an already-uploaded JSONL file."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("openai: missing OPENAI_API_KEY")
    return _http_json(
        "POST", "https://api.openai.com/v1/batches",
        {"input_file_id": input_file_id, "endpoint": "/v1/responses", "completion_window": completion_window},
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, 120.0,
    )
