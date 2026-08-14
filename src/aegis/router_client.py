"""HTTP/model clients for the universal router (stdlib only)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from aegis.providers import ProviderSpec, resolve_model

def chat_completion(
    provider: ProviderSpec,
    *,
    model: str = "",
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: float = 120.0,
    use_responses: bool = False,
    service_tier: str = "auto",
    prompt_cache_key: str = "",
) -> Dict[str, Any]:
    """
    Call upstream chat. Returns unified:
      {provider, model, content, raw_response, usage, mock}
    """
    model_id = resolve_model(provider, model)
    if provider.kind == "mock" or provider.api_style == "mock":
        return _mock_chat(provider, model_id, messages)

    if provider.api_style == "anthropic":
        return _anthropic_chat(
            provider, model_id, messages, temperature, max_tokens, timeout
        )
    if provider.kind == "openai" and use_responses:
        return _openai_responses(
            provider, model_id, messages, temperature, max_tokens, timeout,
            service_tier=service_tier, prompt_cache_key=prompt_cache_key,
        )
    # openai_chat (OpenAI, Grok/xAI, Ollama /v1)
    return _openai_chat(
        provider, model_id, messages, temperature, max_tokens, timeout
    )


def _mock_chat(
    provider: ProviderSpec, model: str, messages: List[Dict[str, str]]
) -> Dict[str, Any]:
    user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user = m.get("content") or ""
            break
    # Deterministic slim reply for reuse testing
    content = (
        f"[mock:{provider.name}/{model}] "
        f"Done.\n\n"
        f"Summary: processed request ({len(user)} chars).\n"
    )
    return {
        "provider": provider.name,
        "model": model,
        "content": content,
        "raw_response": {"mock": True, "content": content},
        "usage": {
            "prompt_tokens": max(1, len(user) // 4),
            "completion_tokens": max(1, len(content) // 4),
        },
        "mock": True,
        "request_id": None,
    }


def _openai_chat(
    provider: ProviderSpec,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> Dict[str, Any]:
    url = provider.base_url.rstrip("/") + "/chat/completions"
    # Ollama openai compat is at host/v1/chat/completions
    if provider.kind == "ollama" and "/v1" not in provider.base_url:
        url = provider.base_url.rstrip("/") + "/v1/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    headers = {"Content-Type": "application/json"}
    if provider.env_key or provider.kind == "antigravity":
        key = ""
        if provider.kind == "antigravity":
            for k in (
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "ANTIGRAVITY_API_KEY",
            ):
                key = os.environ.get(k, "")
                if key:
                    break
        else:
            key = os.environ.get(provider.env_key, "")
        if not key:
            raise RuntimeError(
                f"{provider.name}: missing API key "
                f"(use --model mock for dry pipeline)"
            )
        headers["Authorization"] = f"Bearer {key}"
    data = _http_json("POST", url, body, headers, timeout)
    content = ""
    try:
        content = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        content = json.dumps(data)[:2000]
    usage = data.get("usage") or {}
    return {
        "provider": provider.name,
        "model": model,
        "content": content,
        "raw_response": data,
        "usage": usage,
        "mock": False,
        "request_id": data.get("id"),
    }


def _anthropic_chat(
    provider: ProviderSpec,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> Dict[str, Any]:
    url = provider.base_url.rstrip("/") + "/v1/messages"
    key = os.environ.get(provider.env_key, "")
    if not key:
        raise RuntimeError(
            f"claude: missing env {provider.env_key} (use --model mock)"
        )
    system = ""
    conv = []
    for m in messages:
        if m.get("role") == "system":
            system = (system + "\n" + (m.get("content") or "")).strip()
        else:
            conv.append({"role": m.get("role"), "content": m.get("content") or ""})
    body: Dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": conv or [{"role": "user", "content": "hi"}],
        "temperature": temperature,
    }
    if system:
        body["system"] = system
    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    data = _http_json("POST", url, body, headers, timeout)
    content = ""
    try:
        parts = data.get("content") or []
        content = "".join(
            p.get("text", "") for p in parts if isinstance(p, dict)
        )
    except (TypeError, AttributeError):
        content = json.dumps(data)[:2000]
    usage = data.get("usage") or {}
    # normalize usage keys
    norm = {
        "prompt_tokens": usage.get("input_tokens", usage.get("prompt_tokens", 0)),
        "completion_tokens": usage.get(
            "output_tokens", usage.get("completion_tokens", 0)
        ),
    }
    return {
        "provider": provider.name,
        "model": model,
        "content": content,
        "raw_response": data,
        "usage": norm,
        "mock": False,
        "request_id": data.get("id"),
    }


def _openai_responses(
    provider: ProviderSpec, model: str, messages: List[Dict[str, str]],
    temperature: float, max_tokens: int, timeout: float, *, service_tier: str,
    prompt_cache_key: str,
) -> Dict[str, Any]:
    key = os.environ.get(provider.env_key, "")
    if not key:
        raise RuntimeError("openai: missing API key (use --model mock for dry pipeline)")
    body: Dict[str, Any] = {
        "model": model,
        "input": messages,
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if service_tier in ("auto", "flex", "priority"):
        body["service_tier"] = service_tier
    if prompt_cache_key:
        body["prompt_cache_key"] = prompt_cache_key
    data = _http_json(
        "POST", provider.base_url.rstrip("/") + "/responses", body,
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}, timeout,
    )
    usage = data.get("usage") or {}
    details = usage.get("input_tokens_details") or {}
    normalized = {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "cached_tokens": details.get("cached_tokens", 0),
        "cache_write_tokens": details.get("cache_write_tokens", 0),
        "reasoning_tokens": (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0),
    }
    content = data.get("output_text") or ""
    if not content:
        content = "".join(
            part.get("text", "")
            for item in data.get("output") or [] if isinstance(item, dict)
            for part in item.get("content") or [] if isinstance(part, dict)
        )
    return {"provider": provider.name, "model": model, "content": content,
            "raw_response": data, "usage": normalized, "mock": False,
            "request_id": data.get("id")}


def _http_json(
    method: str,
    url: str,
    body: Dict[str, Any],
    headers: Dict[str, str],
    timeout: float,
) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} {url}: {err_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"connect failed {url}: {exc}") from exc
