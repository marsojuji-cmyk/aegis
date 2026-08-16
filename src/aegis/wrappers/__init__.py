"""Provider wrappers — intercept model I/O through full Aegis pipeline."""

from aegis.wrappers.antigravity_wrapper import AntiGravityWrapper
from aegis.wrappers.base import intercept_and_route
from aegis.wrappers.hermes_wrapper import HermesWrapper, hermes_tool_execution, register
from aegis.wrappers.hermes_telemetry import record_pair as record_hermes_token_pair
from aegis.wrappers.openai_wrapper import OpenAIWrapper

__all__ = [
    "OpenAIWrapper",
    "AntiGravityWrapper",
    "HermesWrapper",
    "hermes_tool_execution",
    "intercept_and_route",
    "record_hermes_token_pair",
    "register",
]
