"""Provider-agnostic recruitment intelligence agents.

The agent layer is deliberately thin: deterministic analytics and quality
checks happen before this package is called.  Agents may explain validated
values and propose advisory actions, but they never calculate new metrics or
make autonomous candidate decisions.
"""

from .advisory_queue import (
    AdvisoryActionQueue,
    build_advisory_queue,
    generate_advisory_actions,
    normalize_action,
)
from .provider import (
    ModelProvider,
    ProviderConfigurationError,
    ProviderError,
)
from .mock_provider import MockProvider
from .gemini_provider import GeminiProvider
from .core import (
    AgentMemory,
    AgentRuntime,
    Critique,
    CriticAgent,
    InterpretationAgent,
    RecommendationAgent,
    request_from_json,
    result_from_json,
)


__all__ = [
    "AdvisoryActionQueue",
    "AgentMemory",
    "AgentRuntime",
    "Critique",
    "CriticAgent",
    "GeminiProvider",
    "InterpretationAgent",
    "ModelProvider",
    "MockProvider",
    "ProviderConfigurationError",
    "ProviderError",
    "RecommendationAgent",
    "build_advisory_queue",
    "generate_advisory_actions",
    "normalize_action",
    "request_from_json",
    "result_from_json",
]
