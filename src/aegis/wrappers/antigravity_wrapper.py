"""
Anti-Gravity (Gemini) wrapper — intercept through full Aegis pipeline.

Anti-Gravity / Gemini can speak OpenAI-compatible chat at:
  generativelanguage.googleapis.com/v1beta/openai/

Env:
  GEMINI_API_KEY or GOOGLE_API_KEY or ANTIGRAVITY_API_KEY
  ANTIGRAVITY_BASE_URL (optional override)
  AEGIS_ANTIGRAVITY_MODEL (default gemini-2.0-flash)

Usage:
  from aegis.wrappers import AntiGravityWrapper
  ag = AntiGravityWrapper()
  resp = ag.chat(prompt="…", paths=["a.py"], task="fix")
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

from aegis.wrappers.base import intercept_and_route, wrap_raw_completion


def _antigravity_key() -> str:
    for k in (
        "ANTIGRAVITY_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        v = os.environ.get(k, "")
        if v:
            return v
    return ""


class AntiGravityWrapper:
    """Aegis-intercepted Anti-Gravity / Gemini client."""

    def __init__(
        self,
        *,
        default_model: str = "",
        default_mode: str = "explore",
        default_paths: Optional[List[str]] = None,
        profile: str = "brief",
        dry_run: bool = False,
    ):
        self.default_model = default_model or os.environ.get(
            "AEGIS_ANTIGRAVITY_MODEL", "gemini-2.0-flash"
        )
        self.default_mode = default_mode
        self.default_paths = list(default_paths or [])
        self.profile = profile
        # dry if no credentials unless forced
        self.dry_run = dry_run or not bool(_antigravity_key())

    def chat(
        self,
        prompt: str,
        *,
        model: str = "",
        system: str = "",
        messages: Optional[Sequence[Dict[str, Any]]] = None,
        task: str = "",
        paths: Optional[Sequence[str]] = None,
        mode: str = "",
        targets: Optional[Sequence[str]] = None,
        profile: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        dry_run: Optional[bool] = None,
        skip_preflight: bool = False,
    ) -> Dict[str, Any]:
        """Full pipeline chat for Anti-Gravity / Gemini."""
        if messages is None:
            msgs: List[Dict[str, Any]] = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
        else:
            msgs = list(messages)

        return intercept_and_route(
            provider="antigravity",
            model=model or self.default_model,
            messages=msgs,
            task=task or prompt[:80],
            paths=list(paths if paths is not None else self.default_paths),
            mode=mode or self.default_mode,
            targets=list(targets or []),
            profile=profile or self.profile,
            max_tokens=max_tokens,
            temperature=temperature,
            dry_run=self.dry_run if dry_run is None else dry_run,
            skip_preflight=skip_preflight,
        )

    def complete(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        return self.chat(prompt, **kwargs)

    @staticmethod
    def intercept_output(
        content: str,
        *,
        model: str = "gemini-2.0-flash",
        profile: str = "brief",
        pack_id: Optional[str] = None,
        task: str = "",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Post-hoc intercept after Anti-Gravity already produced text."""
        return wrap_raw_completion(
            provider="antigravity",
            content=content,
            model=model,
            profile=profile,
            pack_id=pack_id,
            task=task,
            dry_run=dry_run,
        )
