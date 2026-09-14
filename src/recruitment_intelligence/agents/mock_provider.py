"""Deterministic mock LLM provider running 100% offline."""
from __future__ import annotations

from typing import Any, Mapping

from ..domain import AgentRequest, AgentResult, AgentStatus
from .provider import ModelProvider


class MockProvider:
    """Deterministic provider used for tests and offline production runs.

    Responses may be keyed by request_id or agent name. Without a supplied
    response, it returns a deterministic result and preserves evidence.
    If a prompt is provided, it generates a deterministic template message.
    """

    def __init__(self, responses: Mapping[str, AgentResult | Mapping[str, Any]] | None = None):
        self._responses = dict(responses or {})

    def generate(self, request: AgentRequest) -> AgentResult:
        raw = self._responses.get(request.request_id, self._responses.get(request.agent))
        if raw is None:
            default_message = (
                f"[MockProvider] Processed prompt for agent '{request.agent}' "
                f"(request_id: {request.request_id}, evidence_count: {len(request.evidence)})"
                if request.prompt
                else ""
            )
            return AgentResult(
                request_id=request.request_id,
                agent=request.agent,
                status=AgentStatus.OK,
                evidence=request.evidence,
                message=default_message,
            )
        from .core import result_from_json

        result = raw if isinstance(raw, AgentResult) else result_from_json(raw)
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


__all__ = ["MockProvider"]
