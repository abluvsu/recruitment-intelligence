import json

import pytest

from recruitment_intelligence.agents import (
    AdvisoryActionQueue,
    AgentMemory,
    AgentRuntime,
    CriticAgent,
    GeminiProvider,
    InterpretationAgent,
    MockProvider,
    ModelProvider,
    ProviderConfigurationError,
    ProviderError,
    RecommendationAgent,
    build_advisory_queue,
    generate_advisory_actions,
    normalize_action,
    request_from_json,
    result_from_json,
)
from recruitment_intelligence.agents.gemini_provider import GeminiProvider as SubmoduleGeminiProvider
from recruitment_intelligence.agents.mock_provider import MockProvider as SubmoduleMockProvider
from recruitment_intelligence.agents.provider import (
    ModelProvider as SubmoduleModelProvider,
    ProviderConfigurationError as SubmoduleProviderConfigError,
    ProviderError as SubmoduleProviderError,
)
from recruitment_intelligence.domain import (
    AgentRequest,
    AgentResult,
    AgentStatus,
    CandidateRecommendation,
    Confidence,
    ContractError,
    EvidenceReference,
    MetricClaim,
    RecommendationAction,
)


EVIDENCE = EvidenceReference(source="analytics.source_effectiveness", table="Applications")


# ---------------------------------------------------------------------------
# 1. Provider-Agnostic Abstraction & Direct Module Imports
# ---------------------------------------------------------------------------


def test_submodule_imports():
    """Verify dedicated provider modules conform to PROJECT.md code layout."""
    assert SubmoduleModelProvider is ModelProvider
    assert SubmoduleProviderError is ProviderError
    assert SubmoduleProviderConfigError is ProviderConfigurationError
    assert SubmoduleMockProvider is MockProvider
    assert SubmoduleGeminiProvider is GeminiProvider


def test_mock_provider_is_deterministic_and_offline():
    request = AgentRequest("r1", "analytics", {"metrics": []}, evidence=(EVIDENCE,))
    first = MockProvider().generate(request)
    second = MockProvider().generate(request)
    assert first.to_dict() == second.to_dict()
    assert first.status is AgentStatus.OK
    assert first.evidence == (EVIDENCE,)


def test_mock_provider_template_heuristic_with_prompt():
    """When prompt is supplied with no canned response, MockProvider produces deterministic text."""
    request = AgentRequest("r-prompt-1", "founder_summary", {}, prompt="Summarize Q2 source yield", evidence=(EVIDENCE,))
    result = MockProvider().generate(request)
    assert result.status is AgentStatus.OK
    assert "[MockProvider]" in result.message
    assert "founder_summary" in result.message
    assert "r-prompt-1" in result.message
    assert "evidence_count: 1" in result.message


def test_mock_provider_preserves_canned_message_and_claims():
    """Canned responses preserve textual messages, claims, and recommendations."""
    canned = {
        "request_id": "r-canned",
        "agent": "advisory",
        "status": "ok",
        "message": "Founder briefing takeaway: referral efficiency is 3x higher than job boards.",
        "claims": [{"name": "referral_efficiency", "value": 3.0, "confidence": "high"}],
    }
    provider = MockProvider({"r-canned": canned})
    req = AgentRequest("r-canned", "advisory", {})
    result = provider.generate(req)
    assert result.message == "Founder briefing takeaway: referral efficiency is 3x higher than job boards."
    assert len(result.claims) == 1
    assert result.claims[0].name == "referral_efficiency"


def test_gemini_adapter_requires_explicit_configuration_and_never_logs_key():
    with pytest.raises(ProviderConfigurationError):
        GeminiProvider().generate(AgentRequest("r7", "a", {}))

    seen = {}

    def transport(payload):
        seen.update(payload)
        return {"request_id": "r7", "agent": "a", "status": "ok"}

    GeminiProvider(api_key="secret-value", transport=transport).generate(AgentRequest("r7", "a", {}))
    assert "secret-value" not in json.dumps(seen)


def test_gemini_provider_environment_variable_fallback(monkeypatch):
    """GeminiProvider resolves API key from GEMINI_API_KEY or GOOGLE_API_KEY environment variables."""
    monkeypatch.setenv("GEMINI_API_KEY", "env-gemini-key")
    provider = GeminiProvider(transport=lambda env: {"request_id": "r-env", "agent": "a", "status": "ok"})
    assert provider.api_key == "env-gemini-key"
    result = provider.generate(AgentRequest("r-env", "a", {}))
    assert result.status is AgentStatus.OK

    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GOOGLE_API_KEY", "env-google-key")
    provider2 = GeminiProvider(transport=lambda env: {"request_id": "r-env2", "agent": "a", "status": "ok"})
    assert provider2.api_key == "env-google-key"


def test_gemini_provider_preserves_message_from_transport():
    """GeminiProvider forwards textual messages returned by transport without erasure."""
    def transport(payload):
        return {
            "request_id": "r-msg",
            "agent": "gemini_agent",
            "status": "ok",
            "message": "Synthesized executive takeaway from Gemini transport.",
        }

    provider = GeminiProvider(api_key="mock-key", transport=transport)
    result = provider.generate(AgentRequest("r-msg", "gemini_agent", {}))
    assert result.message == "Synthesized executive takeaway from Gemini transport."


def test_gemini_provider_wraps_transport_exceptions():
    """Transport exceptions are safely wrapped into ProviderError."""
    def broken_transport(payload):
        raise ConnectionResetError("Connection dropped by peer")

    provider = GeminiProvider(api_key="mock-key", transport=broken_transport)
    with pytest.raises(ProviderError) as exc_info:
        provider.generate(AgentRequest("r-err", "a", {}))
    assert "Gemini provider failed: ConnectionResetError" in str(exc_info.value)


def test_gemini_provider_reraises_existing_provider_error():
    """Explicit ProviderError instances from transport pass through directly."""
    def provider_error_transport(payload):
        raise ProviderConfigurationError("Quota exceeded in transport")

    provider = GeminiProvider(api_key="mock-key", transport=provider_error_transport)
    with pytest.raises(ProviderConfigurationError):
        provider.generate(AgentRequest("r-err2", "a", {}))


# ---------------------------------------------------------------------------
# 2. Deserialization & Serialization Fidelity
# ---------------------------------------------------------------------------


def test_json_contracts_round_trip_and_validate():
    request = AgentRequest("r6", "agent", {"x": 1}, evidence=(EVIDENCE,))
    parsed = request_from_json(request.to_json())
    assert parsed.to_dict() == request.to_dict()
    with pytest.raises(ContractError):
        request_from_json({"request_id": "", "agent": "a", "payload": {}})
    rec = CandidateRecommendation("c1", RecommendationAction.REVIEW, "Inspect", Confidence.LOW, evidence=(EVIDENCE,))
    result = result_from_json({"request_id": "r", "agent": "a", "status": "ok", "recommendations": [rec.to_dict()]})
    assert result.recommendations[0].requires_human_review


def test_request_deserialization_preserves_prompt_and_provider():
    """request_from_json must preserve prompt and provider attributes."""
    raw = {
        "request_id": "r-preserve",
        "agent": "market_analyst",
        "payload": {"param": 42},
        "prompt": "Evaluate funnel drop-off between screen and onsite",
        "provider": "gemini",
    }
    parsed = request_from_json(raw)
    assert parsed.prompt == "Evaluate funnel drop-off between screen and onsite"
    assert parsed.provider == "gemini"

    # Also verify round-trip via to_dict
    parsed_dict = request_from_json(parsed.to_dict())
    assert parsed_dict.prompt == parsed.prompt
    assert parsed_dict.provider == parsed.provider


def test_result_deserialization_preserves_message():
    """result_from_json must preserve message string."""
    raw = {
        "request_id": "res-preserve",
        "agent": "briefing_agent",
        "status": "ok",
        "message": "Candidate bottleneck detected in technical screening stage.",
    }
    parsed = result_from_json(raw)
    assert parsed.message == "Candidate bottleneck detected in technical screening stage."


# ---------------------------------------------------------------------------
# 3. Advisory Candidate Action Queue & Vocabulary Guardrails
# ---------------------------------------------------------------------------


def test_candidate_recommendation_strictly_forbids_human_review_false():
    """Contract invariant: requires_human_review=False must trigger ContractError."""
    with pytest.raises(ContractError, match="must require human review"):
        CandidateRecommendation(
            candidate_id="cand-forbid",
            action=RecommendationAction.REVIEW,
            rationale="Forbidden autonomous action",
            confidence=Confidence.HIGH,
            requires_human_review=False,
        )


def test_recommendations_are_advisory_even_if_input_requests_autonomy():
    request = AgentRequest(
        "r3",
        "recommendation",
        {"candidates": [{"candidate_id": "cand-1", "action": "reject", "rationale": "Needs review"}]},
        evidence=(EVIDENCE,),
    )
    result = RecommendationAgent().run(request)
    recommendation = result.recommendations[0]
    assert recommendation.action is RecommendationAction.REVIEW
    assert recommendation.requires_human_review is True


def test_normalize_action_handles_natural_variations():
    assert normalize_action("close current process") == RecommendationAction.CLOSE
    assert normalize_action("close_current_process") == RecommendationAction.CLOSE
    assert normalize_action("request feedback") == RecommendationAction.REQUEST_FEEDBACK
    assert normalize_action("request_feedback") == RecommendationAction.REQUEST_FEEDBACK
    assert normalize_action("advance") == RecommendationAction.ADVANCE
    assert normalize_action("escalate") == RecommendationAction.ESCALATE
    assert normalize_action("review") == RecommendationAction.REVIEW
    assert normalize_action("reject") == RecommendationAction.REVIEW
    assert normalize_action("rejected") == RecommendationAction.REVIEW
    assert normalize_action("withdraw") == RecommendationAction.REVIEW
    assert normalize_action("withdrawn") == RecommendationAction.REVIEW
    assert normalize_action("unknown_string") == RecommendationAction.REVIEW


def test_interview_score_prioritization_high_score_advances():
    """Candidates with completed interviews scoring >= 4 must be prioritized for ADVANCE."""
    tables = {
        "Applications": [
            {"id": "app-high", "candidate_id": "cand-star", "status": "interview", "applied_at": "2025-01-01", "updated_at": "2025-01-05"},
        ],
        "Interviews": [
            {"id": "iv-high", "application_id": "app-high", "status": "completed", "completed_at": "2025-01-08", "score": 5},
        ],
    }
    actions = generate_advisory_actions(tables, as_of="2025-01-15")
    advance_actions = [a for a in actions if a.action is RecommendationAction.ADVANCE]
    assert len(advance_actions) == 1
    assert advance_actions[0].candidate_id == "cand-star"
    assert "top interview score" in advance_actions[0].rationale
    assert advance_actions[0].evidence[0].method == "high_score_advance"
    assert advance_actions[0].requires_human_review is True


def test_interview_score_prioritization_low_score_reviews():
    """Candidates with completed interviews scoring <= 2 trigger REVIEW with hiring manager."""
    tables = {
        "Applications": [
            {"id": "app-low", "candidate_id": "cand-struggle", "status": "interview", "applied_at": "2025-01-01", "updated_at": "2025-01-05"},
        ],
        "Interviews": [
            {"id": "iv-low", "application_id": "app-low", "status": "completed", "completed_at": "2025-01-08", "score": 2},
        ],
    }
    actions = generate_advisory_actions(tables, as_of="2025-01-15")
    review_actions = [a for a in actions if a.action is RecommendationAction.REVIEW]
    assert len(review_actions) == 1
    assert review_actions[0].candidate_id == "cand-struggle"
    assert "below-threshold interview score" in review_actions[0].rationale
    assert review_actions[0].evidence[0].method == "low_score_review"
    assert review_actions[0].requires_human_review is True


def test_interview_without_score_requests_feedback():
    """Completed interviews lacking a score prompt for interviewer feedback."""
    tables = {
        "Applications": [
            {"id": "app-noscore", "candidate_id": "cand-wait", "status": "interview", "applied_at": "2025-01-01", "updated_at": "2025-01-05"},
        ],
        "Interviews": [
            {"id": "iv-noscore", "application_id": "app-noscore", "status": "completed", "completed_at": "2025-01-08"},
        ],
    }
    actions = generate_advisory_actions(tables, as_of="2025-01-15")
    fb_actions = [a for a in actions if a.action is RecommendationAction.REQUEST_FEEDBACK]
    assert len(fb_actions) == 1
    assert "request interviewer scorecard" in fb_actions[0].rationale


def test_stalled_application_escalates_at_28_days():
    """Active applications stalled >= 28 days generate ESCALATE recommendations."""
    tables = {
        "Applications": [
            {"id": "app-urgent", "candidate_id": "cand-urgent", "status": "onsite", "applied_at": "2025-01-01", "updated_at": "2025-01-01"},
        ],
    }
    actions = generate_advisory_actions(tables, as_of="2025-02-05")  # 35 days stalled
    escalate_actions = [a for a in actions if a.action is RecommendationAction.ESCALATE]
    assert len(escalate_actions) == 1
    assert ">= 28 days threshold" in escalate_actions[0].rationale
    assert escalate_actions[0].confidence is Confidence.HIGH


def test_stalled_application_reviews_under_28_days():
    """Active applications stalled 14-27 days generate REVIEW recommendations."""
    tables = {
        "Applications": [
            {"id": "app-mod", "candidate_id": "cand-mod", "status": "technical", "applied_at": "2025-01-01", "updated_at": "2025-01-10"},
        ],
    }
    actions = generate_advisory_actions(tables, as_of="2025-01-26")  # 16 days stalled
    review_actions = [a for a in actions if a.action is RecommendationAction.REVIEW]
    assert len(review_actions) == 1
    assert "Hiring manager review recommended" in review_actions[0].rationale


def test_pending_offer_advances():
    """Active applications with pending offers generate ADVANCE recommendations."""
    tables = {
        "Applications": [
            {"id": "app-off", "candidate_id": "cand-off", "status": "offer", "applied_at": "2025-01-01", "updated_at": "2025-01-15"},
        ],
        "Offers": [
            {"id": "off-pending", "application_id": "app-off", "status": "extended"},
        ],
    }
    actions = generate_advisory_actions(tables, as_of="2025-01-20")
    advance_actions = [a for a in actions if a.action is RecommendationAction.ADVANCE]
    assert len(advance_actions) == 1
    assert "Confirm candidate decision and advance onboarding" in advance_actions[0].rationale


def test_terminal_application_closes_without_rejection_language():
    """Terminal applications generate CLOSE recommendations with zero autonomous rejection phrasing."""
    tables = {
        "Applications": [
            {"id": "app-term", "candidate_id": "cand-term", "status": "rejected", "applied_at": "2025-01-01", "updated_at": "2025-01-10"},
        ],
    }
    actions = generate_advisory_actions(tables, as_of="2025-01-20")
    close_actions = [a for a in actions if a.action is RecommendationAction.CLOSE]
    assert len(close_actions) == 1
    assert "Close current process in tracking system (human confirmation required)" in close_actions[0].rationale
    # Ensure no autonomous rejection verbs in rationale
    assert "reject candidate" not in close_actions[0].rationale.lower()
    assert "auto-reject" not in close_actions[0].rationale.lower()


def test_advisory_action_generation_from_tables():
    tables = {
        "Applications": [
            {"id": "app-1", "candidate_id": "c1", "status": "interview", "applied_at": "2025-01-01", "updated_at": "2025-01-05"},
            {"id": "app-2", "candidate_id": "c2", "status": "rejected", "applied_at": "2025-01-01", "updated_at": "2025-01-10"},
        ],
        "Interviews": [
            {"id": "iv-1", "application_id": "app-1", "status": "completed", "completed_at": "2025-01-08"},
        ],
        "Offers": [
            {"id": "off-1", "application_id": "app-1", "status": "pending"},
        ],
    }
    actions = generate_advisory_actions(tables, as_of="2025-02-15")
    assert len(actions) > 0
    for action in actions:
        assert action.requires_human_review is True
        assert action.action in RecommendationAction

    queue = build_advisory_queue(tables, as_of="2025-02-15")
    assert isinstance(queue, AdvisoryActionQueue)
    assert queue.total_count == len(actions)
    assert len(queue.actions_by_type(RecommendationAction.CLOSE)) >= 1


def test_advisory_queue_actions_by_type_filtering():
    """AdvisoryActionQueue.actions_by_type correctly filters by enum member or string variation."""
    tables = {
        "Applications": [
            {"id": "app-close", "candidate_id": "c-close", "status": "withdrawn", "applied_at": "2025-01-01"},
            {"id": "app-offer", "candidate_id": "c-offer", "status": "offer", "applied_at": "2025-01-01"},
        ],
        "Offers": [
            {"id": "off-1", "application_id": "app-offer", "status": "pending"},
        ],
    }
    queue = build_advisory_queue(tables, as_of="2025-01-15")
    assert len(queue.actions_by_type(RecommendationAction.CLOSE)) == 1
    assert len(queue.actions_by_type("close current process")) == 1
    assert len(queue.actions_by_type(RecommendationAction.ADVANCE)) == 1
    assert len(queue.actions_by_type("advance")) == 1


def test_empty_tables_advisory_queue_graceful_handling():
    """Empty or missing tables degrade gracefully without errors."""
    assert generate_advisory_actions({}) == ()
    queue = build_advisory_queue({})
    assert queue.total_count == 0
    assert queue.actions == ()


# ---------------------------------------------------------------------------
# 4. Agent Runtime & Specialist Operations
# ---------------------------------------------------------------------------


def test_interpretation_agent_only_passes_validated_metrics_through():
    request = AgentRequest(
        "r2",
        "source_analytics",
        {"metrics": [{"name": "hire_conversion_rate", "value": 0.2, "numerator": 2, "denominator": 10, "confidence": "medium"}]},
        evidence=(EVIDENCE,),
    )
    result = InterpretationAgent().run(request)
    assert result.claims[0].name == "hire_conversion_rate"
    assert result.claims[0].value == 0.2
    assert result.claims[0].evidence == (EVIDENCE,)


def test_critic_rejects_uncited_claims_and_accepts_cited_claims():
    uncited = AgentRequest("r4", "critic", {"result": {"request_id": "x", "agent": "a", "status": "ok", "claims": [{"name": "x", "value": 1, "confidence": "low"}]}})
    critique = CriticAgent().review(result_from_json(uncited.payload["result"]))
    assert critique.decision == "reject"
    cited = MetricClaim("x", 1, Confidence.LOW, evidence=(EVIDENCE,))
    result = MockProvider({"ok": {"request_id": "ok", "agent": "a", "status": "ok", "claims": [{"name": "x", "value": 1, "confidence": "low", "evidence": [EVIDENCE.to_dict()]}]}}).generate(AgentRequest("ok", "a", {}))
    assert CriticAgent().review(result).approved


def test_runtime_chains_stages_and_keeps_bounded_memory():
    memory = AgentMemory(max_items=1)
    runtime = AgentRuntime(memory=memory)
    request = AgentRequest("r5", "analytics", {"metrics": [{"name": "offers", "value": 3, "confidence": "low"}]}, evidence=(EVIDENCE,))
    results = runtime.run(request)
    assert len(results) == 2
    assert len(memory.recent()) == 1


def test_recommendation_agent_with_tables_payload():
    tables = {
        "Applications": [
            {"id": "app-stalled", "candidate_id": "cand-s", "status": "screening", "applied_at": "2025-01-01", "updated_at": "2025-01-02"},
        ]
    }
    request = AgentRequest("r-tables", "recommender", {"tables": tables, "as_of": "2025-02-01"}, evidence=(EVIDENCE,))
    result = RecommendationAgent().run(request)
    assert len(result.recommendations) >= 1
    assert result.recommendations[0].requires_human_review is True


def test_candidate_recommendation_natural_advisory_strings():
    """CandidateRecommendation accepts natural advisory phrase variations."""
    r1 = CandidateRecommendation("c1", "request feedback", "Need notes", Confidence.HIGH, evidence=(EVIDENCE,))
    assert r1.action == RecommendationAction.REQUEST_FEEDBACK

    r2 = CandidateRecommendation("c2", "close current process", "Candidate withdrew", Confidence.HIGH, evidence=(EVIDENCE,))
    assert r2.action == RecommendationAction.CLOSE

    # Non-advisory actions still raise ContractError
    with pytest.raises(ContractError):
        CandidateRecommendation("c3", "reject", "Auto reject", Confidence.HIGH, evidence=(EVIDENCE,))


def test_generate_advisory_actions_missing_ids_robustness():
    """generate_advisory_actions handles records with missing IDs gracefully without crashing."""
    tables = {
        "Applications": [
            {"status": "rejected"},
            {"status": "interview", "updated_at": "2020-01-01"},
        ],
        "Interviews": [
            {"status": "scheduled", "completed_at": "2020-01-02"},
        ],
        "Offers": [
            {"status": "pending"},
        ],
    }
    actions = generate_advisory_actions(tables, as_of="2025-01-01")
    assert len(actions) > 0
    for a in actions:
        assert isinstance(a, CandidateRecommendation)
        assert bool(a.candidate_id)
        assert len(a.evidence) > 0
        for ev in a.evidence:
            assert all(bool(str(rid).strip()) for rid in ev.record_ids)
