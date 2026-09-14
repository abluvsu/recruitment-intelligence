"""Small, testable runtime for structured recruitment agents.

No provider-specific objects cross the domain boundary.  ``MockProvider`` is
the default and is deterministic/offline; ``GeminiProvider`` only performs a
call when an explicit transport and API key are supplied.  A transport is
injected so importing this module never requires the Google SDK.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

from ..domain import (
    AgentRequest,
    AgentResult,
    AgentStatus,
    CandidateRecommendation,
    Confidence,
    ContractError,
    EvidenceReference,
    Finding,
    MetricClaim,
    RecommendationAction,
)
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



def _evidence(items: Any, fallback: Sequence[EvidenceReference] = ()) -> tuple[EvidenceReference, ...]:
    """Convert JSON evidence into domain references without dropping context."""
    if items is None:
        return tuple(fallback)
    if not isinstance(items, (list, tuple)):
        items = [items]
    out: list[EvidenceReference] = []
    for item in items:
        if isinstance(item, EvidenceReference):
            out.append(item)
        elif isinstance(item, Mapping):
            out.append(
                EvidenceReference(
                    source=str(item.get("source", "agent.payload")),
                    table=item.get("table"),
                    filters=item.get("filters", {}),
                    record_ids=tuple(str(v) for v in item.get("record_ids", item.get("records", []))),
                    method=item.get("method"),
                )
            )
    return tuple(out) or tuple(fallback)


def request_from_json(value: str | bytes | Mapping[str, Any]) -> AgentRequest:
    """Parse a JSON object into :class:`AgentRequest` with strict validation."""
    if isinstance(value, (str, bytes)):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise ContractError("agent request must be a JSON object")
    return AgentRequest(
        request_id=str(value.get("request_id", "")),
        agent=str(value.get("agent", "")),
        payload=value.get("payload", {}),
        evidence=_evidence(value.get("evidence")),
        prompt=value.get("prompt"),
        provider=str(value.get("provider", "mock")),
    )



def _metric(value: Mapping[str, Any], fallback_evidence: Sequence[EvidenceReference]) -> MetricClaim:
    return MetricClaim(
        name=str(value.get("name", "")),
        value=value.get("value"),
        confidence=value.get("confidence", Confidence.INSUFFICIENT.value),
        numerator=value.get("numerator"),
        denominator=value.get("denominator"),
        unit=value.get("unit"),
        evidence=_evidence(value.get("evidence"), fallback_evidence),
        caveats=tuple(str(v) for v in value.get("caveats", ())),
    )


def _finding(value: Mapping[str, Any], fallback_evidence: Sequence[EvidenceReference]) -> Finding:
    metric = value.get("metric")
    return Finding(
        finding_id=str(value.get("finding_id", value.get("id", ""))),
        title=str(value.get("title", "")),
        observed_fact=str(value.get("observed_fact", value.get("claim", ""))),
        confidence=value.get("confidence", Confidence.INSUFFICIENT.value),
        evidence=_evidence(value.get("evidence"), fallback_evidence),
        interpretation=value.get("interpretation"),
        recommendation=value.get("recommendation"),
        caveats=tuple(str(v) for v in value.get("caveats", ())),
        severity=value.get("severity", "medium"),
        metric=_metric(metric, fallback_evidence) if isinstance(metric, Mapping) else None,
    )


def _recommendation(value: Mapping[str, Any], fallback_evidence: Sequence[EvidenceReference]) -> CandidateRecommendation:
    return CandidateRecommendation(
        candidate_id=str(value.get("candidate_id", "")),
        action=value.get("action", RecommendationAction.REVIEW.value),
        rationale=str(value.get("rationale", "Review candidate record")),
        confidence=value.get("confidence", Confidence.INSUFFICIENT.value),
        evidence=_evidence(value.get("evidence"), fallback_evidence),
        # Deliberately ignore false values: the domain contract rejects them.
        requires_human_review=True,
        caveats=tuple(str(v) for v in value.get("caveats", ())),
    )


def result_from_json(value: str | bytes | Mapping[str, Any]) -> AgentResult:
    """Parse a provider response into a domain ``AgentResult``.

    Unknown keys are ignored by design; known evidence and errors are retained
    so providers can evolve without leaking provider-specific types inward.
    """
    if isinstance(value, (str, bytes)):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise ContractError("agent result must be a JSON object")
    evidence = _evidence(value.get("evidence"))
    claims: list[MetricClaim | Finding] = []
    for claim in value.get("claims", ()):
        if not isinstance(claim, Mapping):
            continue
        kind = claim.get("kind")
        if kind == "finding" or "finding_id" in claim or "observed_fact" in claim:
            claims.append(_finding(claim, evidence))
        else:
            claims.append(_metric(claim, evidence))
    return AgentResult(
        request_id=str(value.get("request_id", "")),
        agent=str(value.get("agent", "")),
        status=value.get("status", AgentStatus.ERROR.value),
        claims=tuple(claims),
        recommendations=tuple(
            _recommendation(item, evidence)
            for item in value.get("recommendations", ())
            if isinstance(item, Mapping)
        ),
        evidence=evidence,
        errors=tuple(str(v) for v in value.get("errors", ())),
        message=str(value.get("message", "")),
    )


class AgentMemory:
    """Bounded in-process memory of structured results (no raw prompts/PII)."""

    def __init__(self, max_items: int = 100):
        self.max_items = max(1, int(max_items))
        self._items: list[AgentResult] = []

    def add(self, result: AgentResult) -> None:
        self._items.append(result)
        if len(self._items) > self.max_items:
            del self._items[: len(self._items) - self.max_items]

    def recent(self, limit: int | None = None) -> tuple[AgentResult, ...]:
        return tuple(self._items[-limit:] if limit else self._items)

    def find(self, request_id: str) -> AgentResult | None:
        return next((item for item in reversed(self._items) if item.request_id == request_id), None)


class InterpretationAgent:
    """Turn already-computed metrics into evidence-backed claims."""

    def __init__(self, provider: ModelProvider | None = None):
        self.provider = provider or MockProvider()

    def run(self, request: AgentRequest) -> AgentResult:
        metrics = request.payload.get("metrics", ())
        claims: list[MetricClaim] = []
        for item in metrics if isinstance(metrics, (list, tuple)) else ():
            if not isinstance(item, Mapping):
                continue
            try:
                claims.append(_metric(item, request.evidence))
            except (ContractError, ValueError):
                continue
        if claims:
            return AgentResult(request.request_id, request.agent, AgentStatus.OK, tuple(claims), evidence=request.evidence)
        return self.provider.generate(request)


class RecommendationAgent:
    """Create advisory candidate actions from supplied evidence only."""

    def __init__(self, provider: ModelProvider | None = None):
        self.provider = provider or MockProvider()

    def run(self, request: AgentRequest) -> AgentResult:
        actions: list[CandidateRecommendation] = []
        candidates = request.payload.get("candidates", ())
        for item in candidates if isinstance(candidates, (list, tuple)) else ():
            if not isinstance(item, Mapping) or not item.get("candidate_id"):
                continue
            try:
                raw_action = item.get("action", RecommendationAction.REVIEW.value)
                action = normalize_action(raw_action).value
                actions.append(
                    _recommendation(
                        {
                            **item,
                            "action": action,
                            "rationale": item.get("rationale", "Review candidate record"),
                            "confidence": item.get("confidence", Confidence.LOW.value),
                        },
                        request.evidence,
                    )
                )
            except (ContractError, ValueError):
                continue
        if not actions and "tables" in request.payload:
            tables = request.payload.get("tables", {})
            as_of = request.payload.get("as_of")
            actions.extend(generate_advisory_actions(tables, as_of=as_of))
        if actions:
            return AgentResult(request.request_id, request.agent, AgentStatus.OK, recommendations=tuple(actions), evidence=request.evidence)
        return self.provider.generate(request)


@dataclass(frozen=True, slots=True)
class Critique:
    """Skeptical review of a structured result."""

    decision: str
    blocking_issues: tuple[str, ...] = ()
    important_issues: tuple[str, ...] = ()
    minor_improvements: tuple[str, ...] = ()
    missing_tests: tuple[str, ...] = ()

    @property
    def approved(self) -> bool:
        return self.decision == "approve"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "blocking_issues": list(self.blocking_issues),
            "important_issues": list(self.important_issues),
            "minor_improvements": list(self.minor_improvements),
            "missing_tests": list(self.missing_tests),
        }


class CriticAgent:
    """Reject unsupported, uncited, or unsafe claims before output rendering."""

    def review(self, result: AgentResult) -> Critique:
        blocking: list[str] = []
        important: list[str] = []
        for claim in result.claims:
            if not claim.evidence:
                blocking.append(f"claim {getattr(claim, 'name', getattr(claim, 'finding_id', 'unknown'))} has no evidence")
            if isinstance(claim, MetricClaim) and claim.denominator == 0 and claim.value not in (0, 0.0, None):
                blocking.append(f"metric {claim.name} has denominator zero with non-zero value")
        for recommendation in result.recommendations:
            if not recommendation.requires_human_review:
                blocking.append(f"candidate {recommendation.candidate_id} action lacks human review")
            if not recommendation.evidence:
                important.append(f"candidate {recommendation.candidate_id} recommendation has no evidence")
        if result.status == AgentStatus.ERROR:
            blocking.append("agent returned error status")
        return Critique(
            decision="reject" if blocking else "revise" if important else "approve",
            blocking_issues=tuple(blocking),
            important_issues=tuple(important),
        )

    def run(self, request: AgentRequest) -> AgentResult:
        raw = request.payload.get("result")
        result = raw if isinstance(raw, AgentResult) else result_from_json(raw or {})
        critique = self.review(result)
        return AgentResult(
            request_id=request.request_id,
            agent=request.agent or "critic",
            status=AgentStatus.OK if critique.approved else AgentStatus.PARTIAL,
            evidence=result.evidence,
            errors=tuple(critique.blocking_issues + critique.important_issues),
        )


class AgentRuntime:
    """Sol-compatible sequential runtime for structured specialist agents."""

    def __init__(self, provider: ModelProvider | None = None, memory: AgentMemory | None = None):
        self.provider = provider or MockProvider()
        self.memory = memory or AgentMemory()

    def run(self, request: AgentRequest, stages: Sequence[Any] | None = None) -> tuple[AgentResult, ...]:
        current = request
        results: list[AgentResult] = []
        selected = tuple(stages or (InterpretationAgent(self.provider), RecommendationAgent(self.provider)))
        for stage in selected:
            result = stage.run(current) if hasattr(stage, "run") else self.provider.generate(current)
            self.memory.add(result)
            results.append(result)
            current = AgentRequest(
                request_id=f"{request.request_id}:{result.agent}",
                agent="next",
                payload={"result": result.to_dict(), **current.payload},
                evidence=result.evidence or current.evidence,
            )
        return tuple(results)

