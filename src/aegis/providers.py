"""Model provider registry — detect & route Ollama / Grok / Claude / OpenAI."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ProviderSpec:
    name: str
    kind: str  # ollama | grok | claude | openai | mock
    base_url: str
    api_style: str  # openai_chat | anthropic | ollama_native
    env_key: str
    default_model: str


PROVIDERS: Dict[str, ProviderSpec] = {
    "ollama": ProviderSpec(
        name="ollama",
        kind="ollama",
        base_url=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
        api_style="openai_chat",  # Ollama supports /v1/chat/completions
        env_key="",
        default_model=os.environ.get("AEGIS_OLLAMA_MODEL", "llama3.2"),
    ),
    "grok": ProviderSpec(
        name="grok",
        kind="grok",
        base_url=os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1"),
        api_style="openai_chat",
        env_key="XAI_API_KEY",
        default_model=os.environ.get("AEGIS_GROK_MODEL", "grok-4.6"),
    ),
    "xai": ProviderSpec(
        name="xai",
        kind="grok",
        base_url=os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1"),
        api_style="openai_chat",
        env_key="XAI_API_KEY",
        default_model=os.environ.get("AEGIS_GROK_MODEL", "grok-4.6"),
    ),
    "openai": ProviderSpec(
        name="openai",
        kind="openai",
        base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_style="openai_chat",
        env_key="OPENAI_API_KEY",
        default_model=os.environ.get("AEGIS_OPENAI_MODEL", "gpt-4o-mini"),
    ),
    "claude": ProviderSpec(
        name="claude",
        kind="claude",
        base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        api_style="anthropic",
        env_key="ANTHROPIC_API_KEY",
        default_model=os.environ.get("AEGIS_CLAUDE_MODEL", "claude-sonnet-4-20250514"),
    ),
    "anthropic": ProviderSpec(
        name="anthropic",
        kind="claude",
        base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        api_style="anthropic",
        env_key="ANTHROPIC_API_KEY",
        default_model=os.environ.get("AEGIS_CLAUDE_MODEL", "claude-sonnet-4-20250514"),
    ),
    "mock": ProviderSpec(
        name="mock",
        kind="mock",
        base_url="mock://local",
        api_style="mock",
        env_key="",
        default_model="mock-aegis",
    ),
    # Google Anti-Gravity / Gemini (OpenAI-compatible endpoint)
    "antigravity": ProviderSpec(
        name="antigravity",
        kind="antigravity",
        base_url=os.environ.get(
            "ANTIGRAVITY_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai",
        ),
        api_style="openai_chat",
        env_key="GEMINI_API_KEY",  # also accept GOOGLE/ANTIGRAVITY via client
        default_model=os.environ.get("AEGIS_ANTIGRAVITY_MODEL", "gemini-2.0-flash"),
    ),
    "gemini": ProviderSpec(
        name="gemini",
        kind="antigravity",
        base_url=os.environ.get(
            "ANTIGRAVITY_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai",
        ),
        api_style="openai_chat",
        env_key="GEMINI_API_KEY",
        default_model=os.environ.get("AEGIS_ANTIGRAVITY_MODEL", "gemini-2.0-flash"),
    ),
}


def detect_provider(model: str = "", explicit: str = "") -> ProviderSpec:
    """Detect provider from explicit name or model string."""
    if explicit:
        key = explicit.strip().lower()
        if key in PROVIDERS:
            return PROVIDERS[key]
    m = (model or "").strip().lower()
    if not m or m in ("mock", "dry", "test"):
        return PROVIDERS["mock"]
    if m.startswith("ollama/") or m.startswith("llama") or "ollama" in m:
        return PROVIDERS["ollama"]
    if m.startswith("grok") or m.startswith("xai/"):
        return PROVIDERS["grok"]
    if m.startswith("claude") or m.startswith("anthropic/"):
        return PROVIDERS["claude"]
    if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("openai/"):
        return PROVIDERS["openai"]
    if (
        m.startswith("gemini")
        or m.startswith("antigravity")
        or m.startswith("google/")
    ):
        return PROVIDERS["antigravity"]
    # bare ollama tags often have no slash
    if re.match(r"^[a-z0-9._-]+:[a-z0-9._-]+$", m) or m in ("llama3", "llama3.2", "mistral", "phi3"):
        return PROVIDERS["ollama"]
    return PROVIDERS.get(m, PROVIDERS["mock"])


def resolve_model(provider: ProviderSpec, model: str = "") -> str:
    m = (model or "").strip()
    if not m or m in ("mock", "dry", "test"):
        return provider.default_model
    # strip provider prefix
    for prefix in ("ollama/", "openai/", "xai/", "anthropic/", "grok/", "claude/"):
        if m.lower().startswith(prefix):
            return m[len(prefix) :]
    return m


def list_providers() -> List[Dict[str, Any]]:
    out = []
    for p in PROVIDERS.values():
        if p.name in ("xai", "anthropic", "gemini"):
            continue  # aliases
        if p.env_key:
            # antigravity accepts several key names
            if p.kind == "antigravity":
                key_set = any(
                    os.environ.get(k)
                    for k in (
                        "GEMINI_API_KEY",
                        "GOOGLE_API_KEY",
                        "ANTIGRAVITY_API_KEY",
                    )
                )
            else:
                key_set = bool(os.environ.get(p.env_key))
        else:
            key_set = True
        out.append(
            {
                "name": p.name,
                "kind": p.kind,
                "base_url": p.base_url,
                "default_model": p.default_model,
                "credentials": key_set,
                "api_style": p.api_style,
            }
        )
    return out
