"""Provider-agnostic interface and base error types.

Decouples agent logic from concrete LLM APIs. Defines the core protocol
and exceptions used by offline mock and remote model providers.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain import AgentRequest, AgentResult


class ProviderError(RuntimeError):
    """Base class for provider failures."""


class ProviderConfigurationError(ProviderError):
    """Raised when a provider cannot be used safely in the current process."""


@runtime_checkable
class ModelProvider(Protocol):
    """Minimal provider contract used by every specialist and orchestrator."""

    def generate(self, request: AgentRequest) -> AgentResult:
        """Generate a structured result for ``request``."""


__all__ = [
    "ModelProvider",
    "ProviderConfigurationError",
    "ProviderError",
]
