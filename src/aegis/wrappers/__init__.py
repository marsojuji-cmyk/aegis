"""Provider wrappers — intercept model I/O through full Aegis pipeline."""

from aegis.wrappers.antigravity_wrapper import AntiGravityWrapper
from aegis.wrappers.base import intercept_and_route
from aegis.wrappers.openai_wrapper import OpenAIWrapper

__all__ = [
    "OpenAIWrapper",
    "AntiGravityWrapper",
    "intercept_and_route",
]
