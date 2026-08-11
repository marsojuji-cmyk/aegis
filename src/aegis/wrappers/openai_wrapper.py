"""
OpenAI wrapper — drop-in intercept for chat.completions.

Usage:
  from aegis.wrappers import OpenAIWrapper
  client = OpenAIWrapper()
  resp = client.chat.completions.create(model="gpt-4o-mini", messages=[...],
                                        aegis={"paths": ["a.py"], "task": "fix"})

Or post-hoc:
  OpenAIWrapper.intercept_output(content, profile="diff")
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence

from aegis.wrappers.base import intercept_and_route, wrap_raw_completion


class _Completions:
    def __init__(self, wrapper: "OpenAIWrapper"):
        self._w = wrapper

    def create(
        self,
        *,
        model: str = "",
        messages: Optional[Sequence[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        aegis: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        OpenAI-shaped create(). Extra `aegis` dict:
          paths, task, mode, targets, profile, dry_run, skip_preflight
        """
        aegis = aegis or {}
        model = model or self._w.default_model
        # dry if no key and not explicit
        dry = bool(aegis.get("dry_run") or self._w.dry_run)
        return intercept_and_route(
            provider="openai",
            model=model,
            messages=list(messages or []),
            task=aegis.get("task") or "",
            paths=aegis.get("paths") or self._w.default_paths,
            mode=aegis.get("mode") or self._w.default_mode,
            targets=aegis.get("targets") or [],
            profile=aegis.get("profile") or self._w.profile,
            max_tokens=int(max_tokens or 1024),
            temperature=float(temperature if temperature is not None else 0.2),
            dry_run=dry,
            skip_preflight=bool(aegis.get("skip_preflight")),
        )


class _Chat:
    def __init__(self, wrapper: "OpenAIWrapper"):
        self.completions = _Completions(wrapper)


class OpenAIWrapper:
    """Aegis-intercepted OpenAI-compatible client surface."""

    def __init__(
        self,
        *,
        default_model: str = "gpt-4o-mini",
        default_mode: str = "explore",
        default_paths: Optional[List[str]] = None,
        profile: str = "brief",
        dry_run: bool = False,
    ):
        self.default_model = default_model
        self.default_mode = default_mode
        self.default_paths = list(default_paths or [])
        self.profile = profile
        self.dry_run = dry_run or not bool(os.environ.get("OPENAI_API_KEY"))
        self.chat = _Chat(self)

    @staticmethod
    def intercept_output(
        content: str,
        *,
        model: str = "gpt-4o-mini",
        profile: str = "brief",
        pack_id: Optional[str] = None,
        task: str = "",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Post-hoc: model already ran; shrink/store/reuse/ledger only."""
        return wrap_raw_completion(
            provider="openai",
            content=content,
            model=model,
            profile=profile,
            pack_id=pack_id,
            task=task,
            dry_run=dry_run,
        )

    def complete(
        self,
        prompt: str,
        *,
        model: str = "",
        system: str = "",
        **aegis_kwargs: Any,
    ) -> Dict[str, Any]:
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat.completions.create(
            model=model or self.default_model,
            messages=messages,
            aegis=aegis_kwargs,
        )
