"""Provider-agnostic contracts shared by every pipeline stage.

The models deliberately contain no Airtable SDK or LLM types. They are frozen
dataclasses so a result can be safely passed between workers and serialized to
JSON with :meth:`to_dict`.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Sequence, TypeAlias


class ContractError(ValueError):
    """Raised when a shared contract cannot be constructed safely."""


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    ERROR = "error"


class RecommendationAction(str, Enum):
    REVIEW = "review"
    ADVANCE = "advance"
    ESCALATE = "escalate"
    REQUEST_FEEDBACK = "request_feedback"
    CLOSE = "close"


DateLike: TypeAlias = str


def _require(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a non-empty string")
    return value.strip()


def _date(value: DateLike | None, name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise ContractError(f"{name} must be an ISO-8601 string")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{name} must be an ISO-8601 string") from exc


def _mapping(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be a mapping")
    return dict(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(v) for v in value]
    return value


class Serializable:
    """Mixin exposing deterministic, JSON-compatible dictionaries."""

    # Keep slotted dataclass instances truly immutable: without this empty
    # slots declaration, the mixin contributes an instance ``__dict__`` and
    # callers could inject attributes despite ``frozen=True``.
    __slots__ = ()

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)

    def to_json(self) -> str:
        """Return stable JSON suitable for artifacts or worker messages."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True, slots=True)
class AirtableRecord(Serializable):
    record_id: str
    table: str
    fields: Mapping[str, Any] = field(default_factory=dict)
    created_time: DateLike | None = None
    modified_time: DateLike | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _require(self.record_id, "record_id"))
        object.__setattr__(self, "table", _require(self.table, "table"))
        object.__setattr__(self, "fields", _mapping(self.fields, "fields"))
        _date(self.created_time, "created_time")
        _date(self.modified_time, "modified_time")
        object.__setattr__(self, "attributes", _mapping(self.attributes, "attributes"))


@dataclass(frozen=True, slots=True)
class Department(Serializable):
    department_id: str
    name: str
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "department_id", _require(self.department_id, "department_id"))
        object.__setattr__(self, "name", _require(self.name, "name"))
        object.__setattr__(self, "attributes", _mapping(self.attributes, "attributes"))


@dataclass(frozen=True, slots=True)
class Person(Serializable):
    person_id: str
    name: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "person_id", _require(self.person_id, "person_id"))
        if self.name is not None:
            object.__setattr__(self, "name", _require(self.name, "name"))
        object.__setattr__(self, "attributes", _mapping(self.attributes, "attributes"))


@dataclass(frozen=True, slots=True)
class JobOpening(Serializable):
    job_id: str
    title: str
    department_id: str | None = None
    status: str | None = None
    opened_at: DateLike | None = None
    closed_at: DateLike | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_id", _require(self.job_id, "job_id"))
        object.__setattr__(self, "title", _require(self.title, "title"))
        if self.department_id is not None:
            object.__setattr__(self, "department_id", _require(self.department_id, "department_id"))
        if self.status is not None:
            object.__setattr__(self, "status", _require(self.status, "status"))
        _date(self.opened_at, "opened_at")
        _date(self.closed_at, "closed_at")
        object.__setattr__(self, "attributes", _mapping(self.attributes, "attributes"))


@dataclass(frozen=True, slots=True)
class Candidate(Serializable):
    candidate_id: str
    person_id: str | None = None
    name: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _require(self.candidate_id, "candidate_id"))
        if self.person_id is not None:
            object.__setattr__(self, "person_id", _require(self.person_id, "person_id"))
        if self.name is not None:
            object.__setattr__(self, "name", _require(self.name, "name"))
        object.__setattr__(self, "attributes", _mapping(self.attributes, "attributes"))


@dataclass(frozen=True, slots=True)
class Application(Serializable):
    application_id: str
    candidate_id: str
    job_id: str | None = None
    source: str | None = None
    status: str | None = None
    applied_at: DateLike | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("application_id", "candidate_id"):
            object.__setattr__(self, name, _require(getattr(self, name), name))
        for name in ("job_id", "source", "status"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _require(value, name))
        _date(self.applied_at, "applied_at")
        object.__setattr__(self, "attributes", _mapping(self.attributes, "attributes"))


@dataclass(frozen=True, slots=True)
class Interview(Serializable):
    interview_id: str
    application_id: str
    status: str | None = None
    scheduled_at: DateLike | None = None
    completed_at: DateLike | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("interview_id", "application_id"):
            object.__setattr__(self, name, _require(getattr(self, name), name))
        if self.status is not None:
            object.__setattr__(self, "status", _require(self.status, "status"))
        _date(self.scheduled_at, "scheduled_at")
        _date(self.completed_at, "completed_at")
        object.__setattr__(self, "attributes", _mapping(self.attributes, "attributes"))


@dataclass(frozen=True, slots=True)
class Offer(Serializable):
    offer_id: str
    application_id: str
    status: str | None = None
    offered_at: DateLike | None = None
    responded_at: DateLike | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("offer_id", "application_id"):
            object.__setattr__(self, name, _require(getattr(self, name), name))
        if self.status is not None:
            object.__setattr__(self, "status", _require(self.status, "status"))
        _date(self.offered_at, "offered_at")
        _date(self.responded_at, "responded_at")
        object.__setattr__(self, "attributes", _mapping(self.attributes, "attributes"))


@dataclass(frozen=True, slots=True)
class EvidenceReference(Serializable):
    source: str
    table: str | None = None
    filters: Mapping[str, Any] = field(default_factory=dict)
    record_ids: tuple[str, ...] = ()
    method: str | None = None
    query: str | None = None
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _require(self.source, "source"))
        if self.table is not None:
            object.__setattr__(self, "table", _require(self.table, "table"))
        object.__setattr__(self, "filters", _mapping(self.filters, "filters"))
        object.__setattr__(self, "record_ids", tuple(_require(v, "record_id") for v in self.record_ids))
        if self.method is not None:
            object.__setattr__(self, "method", _require(self.method, "method"))
        if self.query is not None:
            object.__setattr__(self, "query", _require(self.query, "query"))
        object.__setattr__(self, "caveats", tuple(str(v) for v in self.caveats))


@dataclass(frozen=True, slots=True)
class MetricClaim(Serializable):
    name: str
    value: float | int | str | None
    confidence: Confidence
    numerator: float | int | None = None
    denominator: float | int | None = None
    unit: str | None = None
    evidence: tuple[EvidenceReference, ...] = ()
    caveats: tuple[str, ...] = ()

    def __init__(
        self,
        name: str = "",
        value: float | int | str | None = None,
        confidence: Confidence | str = Confidence.INSUFFICIENT,
        numerator: float | int | None = None,
        denominator: float | int | None = None,
        unit: str | None = None,
        evidence: tuple[EvidenceReference, ...] | Sequence[EvidenceReference] = (),
        caveats: tuple[str, ...] | Sequence[str] = (),
        *,
        metric: str | None = None,
    ) -> None:
        if metric is not None and name and metric != name:
            raise ContractError(f"conflicting 'name' and 'metric' arguments provided: name={name!r}, metric={metric!r}")
        resolved_name = metric if metric is not None else name
        clean_name = _require(resolved_name, "name")

        if not isinstance(confidence, Confidence):
            try:
                confidence = Confidence(confidence)
            except ValueError as exc:
                raise ContractError(f"invalid confidence: {confidence}") from exc

        if isinstance(value, float) and math.isnan(value):
            raise ContractError("value cannot be NaN")

        if numerator is not None:
            if isinstance(numerator, bool) or not isinstance(numerator, (int, float)):
                raise ContractError("numerator must be a number")
            if math.isnan(numerator):
                raise ContractError("numerator cannot be NaN")
            if numerator < 0:
                raise ContractError("numerator cannot be negative")

        if denominator is not None:
            if isinstance(denominator, bool) or not isinstance(denominator, (int, float)):
                raise ContractError("denominator must be a number")
            if math.isnan(denominator):
                raise ContractError("denominator cannot be NaN")
            if denominator < 0:
                raise ContractError("denominator cannot be negative")

        if numerator is not None and denominator is not None and numerator > denominator:
            raise ContractError("numerator cannot exceed denominator")

        object.__setattr__(self, "name", clean_name)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "numerator", numerator)
        object.__setattr__(self, "denominator", denominator)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "evidence", tuple(evidence) if evidence else ())
        object.__setattr__(self, "caveats", tuple(str(v) for v in caveats) if caveats else ())

    @property
    def metric(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class Finding(Serializable):
    finding_id: str
    title: str
    observed_fact: str
    confidence: Confidence
    evidence: tuple[EvidenceReference, ...] = ()
    interpretation: str | None = None
    recommendation: str | None = None
    caveats: tuple[str, ...] = ()
    severity: Severity = Severity.MEDIUM
    metric: MetricClaim | None = None
    category: str | None = None
    description: str | None = None
    affected_records: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("finding_id", "title", "observed_fact"):
            object.__setattr__(self, name, _require(getattr(self, name), name))
        if self.category is not None:
            object.__setattr__(self, "category", _require(self.category, "category"))
        if self.description is not None:
            object.__setattr__(self, "description", _require(self.description, "description"))
        if self.interpretation is not None:
            object.__setattr__(self, "interpretation", _require(self.interpretation, "interpretation"))
        # Synchronize description and interpretation
        if self.interpretation is None and self.description is not None:
            object.__setattr__(self, "interpretation", self.description)
        elif self.description is None and self.interpretation is not None:
            object.__setattr__(self, "description", self.interpretation)
        if not isinstance(self.confidence, Confidence):
            try:
                object.__setattr__(self, "confidence", Confidence(self.confidence))
            except ValueError as exc:
                raise ContractError(f"invalid confidence: {self.confidence}") from exc
        if not isinstance(self.severity, Severity):
            try:
                object.__setattr__(self, "severity", Severity(self.severity))
            except ValueError as exc:
                raise ContractError(f"invalid severity: {self.severity}") from exc
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "caveats", tuple(str(v) for v in self.caveats))
        object.__setattr__(self, "affected_records", tuple(str(v) for v in self.affected_records))
        object.__setattr__(self, "recommendations", tuple(str(v) for v in self.recommendations))
        # Synchronize recommendation and recommendations
        if self.recommendation is None and self.recommendations:
            object.__setattr__(self, "recommendation", self.recommendations[0])
        elif self.recommendation is not None and not self.recommendations:
            object.__setattr__(self, "recommendations", (self.recommendation,))


@dataclass(frozen=True, slots=True)
class CandidateRecommendation(Serializable):
    candidate_id: str
    action: RecommendationAction
    rationale: str
    confidence: Confidence
    evidence: tuple[EvidenceReference, ...] = ()
    requires_human_review: bool = True
    caveats: tuple[str, ...] = ()
    application_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _require(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "rationale", _require(self.rationale, "rationale"))
        if self.application_id is not None:
            cleaned_app = str(self.application_id).strip()
            if cleaned_app:
                object.__setattr__(self, "application_id", cleaned_app)
            else:
                object.__setattr__(self, "application_id", None)
        if not isinstance(self.action, RecommendationAction):
            try:
                object.__setattr__(self, "action", RecommendationAction(self.action))
            except ValueError as exc:
                normalized = str(self.action).strip().lower().replace(" ", "_").replace("-", "_")
                if normalized in ("request_feedback", "feedback"):
                    object.__setattr__(self, "action", RecommendationAction.REQUEST_FEEDBACK)
                elif normalized in ("close", "close_current_process", "close_process"):
                    object.__setattr__(self, "action", RecommendationAction.CLOSE)
                elif normalized == "review":
                    object.__setattr__(self, "action", RecommendationAction.REVIEW)
                elif normalized == "advance":
                    object.__setattr__(self, "action", RecommendationAction.ADVANCE)
                elif normalized == "escalate":
                    object.__setattr__(self, "action", RecommendationAction.ESCALATE)
                else:
                    raise ContractError(f"invalid recommendation action: {self.action}") from exc
        if not isinstance(self.confidence, Confidence):
            try:
                object.__setattr__(self, "confidence", Confidence(self.confidence))
            except ValueError as exc:
                raise ContractError(f"invalid confidence: {self.confidence}") from exc
        if not self.requires_human_review:
            raise ContractError("candidate recommendations must require human review")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "caveats", tuple(str(v) for v in self.caveats))


@dataclass(frozen=True, slots=True)
class Briefing(Serializable):
    generated_at: DateLike
    period: str
    what_changed: tuple[str, ...] = ()
    urgent_items: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    candidate_actions: tuple[CandidateRecommendation, ...] = ()
    quality_warnings: tuple[Finding, ...] = ()
    next_actions: tuple[str, ...] = ()
    confidence: Confidence = Confidence.MEDIUM
    briefing_id: str | None = None
    period_start: DateLike | None = None
    period_end: DateLike | None = None
    executive_summary: str | None = None
    metrics: tuple[MetricClaim, ...] = ()
    cost_appendix: str | None = None

    def __post_init__(self) -> None:
        _date(self.generated_at, "generated_at")
        _date(self.period_start, "period_start")
        _date(self.period_end, "period_end")
        object.__setattr__(self, "period", _require(self.period, "period"))
        if self.briefing_id is not None:
            object.__setattr__(self, "briefing_id", _require(self.briefing_id, "briefing_id"))
        if self.executive_summary is not None:
            object.__setattr__(self, "executive_summary", _require(self.executive_summary, "executive_summary"))
        if not isinstance(self.confidence, Confidence):
            try:
                object.__setattr__(self, "confidence", Confidence(self.confidence))
            except ValueError as exc:
                raise ContractError(f"invalid confidence: {self.confidence}") from exc
        object.__setattr__(self, "what_changed", tuple(str(v) for v in self.what_changed))
        object.__setattr__(self, "urgent_items", tuple(str(v) for v in self.urgent_items))
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "candidate_actions", tuple(self.candidate_actions))
        object.__setattr__(self, "quality_warnings", tuple(self.quality_warnings))
        object.__setattr__(self, "next_actions", tuple(str(v) for v in self.next_actions))
        object.__setattr__(self, "metrics", tuple(self.metrics))


@dataclass(frozen=True, slots=True)
class AgentRequest(Serializable):
    request_id: str
    agent: str
    payload: Mapping[str, Any]
    evidence: tuple[EvidenceReference, ...] = ()
    prompt: str | None = None
    provider: str = "mock"

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require(self.request_id, "request_id"))
        object.__setattr__(self, "agent", _require(self.agent, "agent"))
        object.__setattr__(self, "payload", _mapping(self.payload, "payload"))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if self.prompt is not None:
            object.__setattr__(self, "prompt", _require(self.prompt, "prompt"))


@dataclass(frozen=True, slots=True)
class AgentResult(Serializable):
    request_id: str
    agent: str
    status: AgentStatus
    claims: tuple[MetricClaim | Finding, ...] = ()
    recommendations: tuple[CandidateRecommendation, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    errors: tuple[str, ...] = ()
    message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require(self.request_id, "request_id"))
        object.__setattr__(self, "agent", _require(self.agent, "agent"))
        if not isinstance(self.status, AgentStatus):
            try:
                object.__setattr__(self, "status", AgentStatus(self.status))
            except ValueError as exc:
                raise ContractError(f"invalid status: {self.status}") from exc
        object.__setattr__(self, "claims", tuple(self.claims))
        object.__setattr__(self, "recommendations", tuple(self.recommendations))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "errors", tuple(str(v) for v in self.errors))


# Contract vocabulary aliases keep imports concise and make the public API
# resilient to the names used in worker specifications.
Evidence = EvidenceReference
Metric = MetricClaim
Recommendation = CandidateRecommendation
AgentInput = AgentRequest
ConfidenceBucket = Confidence
