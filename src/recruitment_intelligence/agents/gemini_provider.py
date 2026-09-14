"""Optional Gemini adapter with dependency/key injection and secret redaction."""
from __future__ import annotations

import os
from typing import Any, Callable, Mapping

from ..domain import AgentRequest, AgentResult
from .provider import ModelProvider, ProviderConfigurationError, ProviderError


class GeminiProvider:
    """Optional Gemini adapter with dependency/key injection.

    ``transport`` receives a provider-neutral request mapping and returns a
    JSON object/string. Applications can inject their SDK call later; no SDK
    import or network activity occurs during module import.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-1.5-flash",
        transport: Callable[[Mapping[str, Any]], Mapping[str, Any] | str] | None = None,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self.model = model
        self.transport = transport

    def generate(self, request: AgentRequest) -> AgentResult:
        if not self.api_key:
            raise ProviderConfigurationError("Gemini API key is not configured")
        if self.transport is None:
            raise ProviderConfigurationError("Gemini transport is not configured")

        # Never include the API key in the envelope sent to the transport.
        envelope = {"model": self.model, "request": request.to_dict()}
        try:
            response = self.transport(envelope)
            from .core import result_from_json

            result = response if isinstance(response, AgentResult) else result_from_json(response)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"Gemini provider failed: {type(exc).__name__}") from exc

        return AgentResult(
            request_id=request.request_id,
            agent=result.agent or request.agent,
            status=result.status,
            claims=result.claims,
            recommendations=result.recommendations,
            evidence=result.evidence or request.evidence,
            errors=result.errors,
            message=result.message,
        )

    respond = generate


__all__ = ["GeminiProvider"]
