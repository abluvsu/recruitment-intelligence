"""Adversarial stress-test suite for Milestone M1 (Domain Validation & Baseline).

This module subjects all domain models, contracts, serialization mechanisms,
and boundary guards to hostile inputs, mutation attempts, serialization edge cases,
and numerical extremes.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
import math
from typing import Any

import pytest

from recruitment_intelligence.domain import (
    AgentRequest,
    AgentResult,
    AgentStatus,
    AirtableRecord,
    Application,
    Briefing,
    Candidate,
    CandidateRecommendation,
    Confidence,
    ContractError,
    Department,
    EvidenceReference,
    Finding,
    Interview,
    JobOpening,
    MetricClaim,
    Offer,
    Person,
    RecommendationAction,
    Severity,
)


# =============================================================================
# Helper Fixtures & Generators
# =============================================================================

@pytest.fixture
def sample_instances() -> list[Any]:
    """Instances of all 15 domain classes with minimal valid parameters."""
    ev = EvidenceReference(source="airtable.test", table="Applications")
    claim = MetricClaim(name="acceptance_rate", value=0.8, confidence=Confidence.HIGH, numerator=4, denominator=5)
    finding = Finding(finding_id="F-001", title="Title", observed_fact="Observed fact", confidence=Confidence.HIGH)
    rec = CandidateRecommendation(
        candidate_id="c-1",
        action=RecommendationAction.REVIEW,
        rationale="Review candidate",
        confidence=Confidence.MEDIUM,
    )
    briefing = Briefing(generated_at="2025-01-01T00:00:00Z", period="2025-W01")
    req = AgentRequest(request_id="req-1", agent="agent_x", payload={"k": "v"})
    res = AgentResult(request_id="res-1", agent="agent_x", status=AgentStatus.OK)

    return [
        Department("dept-1", "Engineering"),
        Person("p-1"),
        JobOpening("j-1", "Staff Engineer"),
        Candidate("cand-1"),
        Application("app-1", "cand-1"),
        Interview("int-1", "app-1"),
        Offer("off-1", "app-1"),
        AirtableRecord("rec-1", "Applications"),
        ev,
        claim,
        finding,
        rec,
        briefing,
        req,
        res,
    ]


# =============================================================================
# 1. Slotted Immutability & Attribute Injection Stress-Tests
# =============================================================================

class TestSlottedImmutability:
    """Stress-test memory slots, frozenness, and mutation resistance."""

    def test_instances_lack_dict_and_have_slots(self, sample_instances: list[Any]):
        """True slotted classes must not allocate an instance __dict__."""
        for instance in sample_instances:
            cls = type(instance)
            assert hasattr(cls, "__slots__"), f"{cls.__name__} must define __slots__"
            # In Python slotted classes without '__dict__' in slots, hasattr(inst, '__dict__') is False
            assert not hasattr(instance, "__dict__"), (
                f"{cls.__name__} instance exposes __dict__, violating slot memory optimization"
            )

    def test_reassignment_of_every_slot_attribute_is_blocked(self, sample_instances: list[Any]):
        """Attempting to reassign any declared slot attribute must raise FrozenInstanceError or AttributeError."""
        for instance in sample_instances:
            cls = type(instance)
            for slot in cls.__slots__:
                with pytest.raises((FrozenInstanceError, AttributeError)):
                    setattr(instance, slot, "adversarial_overwrite")

    def test_deletion_of_slot_attributes_is_blocked(self, sample_instances: list[Any]):
        """Attempting to delete any attribute on frozen slotted instance must fail."""
        for instance in sample_instances:
            cls = type(instance)
            for slot in cls.__slots__:
                with pytest.raises((FrozenInstanceError, AttributeError)):
                    delattr(instance, slot)

    def test_dynamic_attribute_injection_is_blocked(self, sample_instances: list[Any]):
        """Attempting to inject undeclared attributes must raise FrozenInstanceError or AttributeError."""
        hostile_attributes = [
            "__injected__",
            "evil_payload",
            "_unauthorized",
            "admin_mode",
            "bypass_validation",
        ]
        for instance in sample_instances:
            for attr in hostile_attributes:
                with pytest.raises((FrozenInstanceError, AttributeError)):
                    setattr(instance, attr, True)

    def test_constructor_input_mutation_isolation(self):
        """Mutating source collections after passing them to models must not corrupt model state."""
        # 1. Mapping isolation in Department
        external_attrs = {"env": "prod", "nested": {"team": "core"}}
        dept = Department("d1", "Platform", attributes=external_attrs)
        external_attrs["env"] = "compromised"
        external_attrs["injected_key"] = "leak"
        assert dept.attributes["env"] == "prod"
        assert "injected_key" not in dept.attributes

        # 2. Fields isolation in AirtableRecord
        external_fields = {"Status": "Active", "Count": 42}
        rec = AirtableRecord("r1", "Candidates", fields=external_fields)
        external_fields["Status"] = "Deleted"
        external_fields["NewField"] = "Injected"
        assert rec.fields["Status"] == "Active"
        assert "NewField" not in rec.fields

        # 3. Tuple sequence isolation in EvidenceReference
        external_ids = ["rec_1", "rec_2"]
        external_caveats = ["sample limited"]
        ev = EvidenceReference("source", record_ids=external_ids, caveats=external_caveats)
        external_ids.append("rec_3")
        external_caveats.append("unsupported claim")
        assert ev.record_ids == ("rec_1", "rec_2")
        assert ev.caveats == ("sample limited",)

        # 4. Sequence isolation in Briefing
        external_actions = ["action_1"]
        b = Briefing(generated_at="2025-01-01T00:00:00Z", period="2025-W01", next_actions=external_actions)
        external_actions.append("action_2")
        assert b.next_actions == ("action_1",)


# =============================================================================
# 2. Serialization & Deserialization Edge Cases
# =============================================================================

class TestSerializationEdgeCases:
    """Stress-test JSON serialization with nested dicts, None values, and unusual characters."""

    def test_direct_dict_injection_bypasses_frozen_guarantee(self, sample_instances: list[Any]):
        """Check whether hasattr(__dict__) allows bypassing frozen immutability.
        
        This vulnerability occurs because `Serializable` does not define `__slots__ = ()`.
        Consequently, all 15 models inherit `__dict__`, permitting attribute injection.
        """
        bypasses = []
        for instance in sample_instances:
            if hasattr(instance, "__dict__"):
                try:
                    instance.__dict__["_injected_via_dict"] = "EXPLOIT"
                    if getattr(instance, "_injected_via_dict", None) == "EXPLOIT":
                        bypasses.append(type(instance).__name__)
                except Exception:
                    pass
        # Any instance that allows bypassing frozen immutability via __dict__ is recorded
        assert not bypasses, f"Frozen immutability bypassed via __dict__ on: {bypasses}"

    def test_slots_without_dict_mechanism_proof(self):
        """Demonstrate that defining __slots__ = () on Serializable eliminates __dict__ entirely."""
        from dataclasses import dataclass

        class DummySerializableWithSlots:
            __slots__ = ()

        @dataclass(frozen=True, slots=True)
        class SlottedChild(DummySerializableWithSlots):
            name: str

        child = SlottedChild("safe")
        assert hasattr(child, "__slots__")
        assert not hasattr(child, "__dict__"), "Defining __slots__ = () on mixin eliminates __dict__"
        with pytest.raises(AttributeError):
            child.__dict__["hacked"] = True

    def test_deeply_nested_dict_in_attributes(self):
        """Attributes nested 10 levels deep must serialize and roundtrip cleanly."""
        nested = {"level": 10, "data": "bottom", "flag": True, "items": [1, 2, 3]}
        for i in range(9, 0, -1):
            nested = {f"level_{i}": nested, "id": i}

        dept = Department("dept-deep", "R&D", attributes=nested)
        as_dict = dept.to_dict()
        assert as_dict["attributes"]["id"] == 1
        assert as_dict["attributes"]["level_1"]["id"] == 2

        as_json = dept.to_json()
        assert isinstance(as_json, str)
        decoded = json.loads(as_json)
        # Walk down 10 levels
        curr = decoded["attributes"]
        for i in range(1, 10):
            assert curr["id"] == i
            curr = curr[f"level_{i}"]
        assert curr["data"] == "bottom"

    def test_all_optional_none_fields_serialized_accurately(self):
        """All optional fields set to None must serialize to JSON null without omission or crash."""
        job = JobOpening("j-none", "Role", department_id=None, status=None, opened_at=None, closed_at=None)
        d = job.to_dict()
        assert d["department_id"] is None
        assert d["status"] is None
        assert d["opened_at"] is None
        assert d["closed_at"] is None
        j_str = job.to_json()
        assert '"department_id": null' in j_str

        claim = MetricClaim(name="empty_claim", value=None, confidence=Confidence.INSUFFICIENT, numerator=None, denominator=None, unit=None)
        c_dict = claim.to_dict()
        assert c_dict["value"] is None
        assert c_dict["numerator"] is None
        assert c_dict["denominator"] is None
        assert c_dict["unit"] is None

        cand_rec = CandidateRecommendation("c1", RecommendationAction.REVIEW, "test", Confidence.LOW, application_id=None)
        assert cand_rec.to_dict()["application_id"] is None

        briefing = Briefing(
            generated_at="2025-01-01T00:00:00Z",
            period="2025-W01",
            briefing_id=None,
            period_start=None,
            period_end=None,
            executive_summary=None,
            cost_appendix=None,
        )
        b_dict = briefing.to_dict()
        assert b_dict["briefing_id"] is None
        assert b_dict["executive_summary"] is None
        assert b_dict["cost_appendix"] is None

    def test_unusual_characters_unicode_and_adversarial_strings(self):
        """Handle international unicode, emojis, bidirectional overrides, and special characters."""
        adversarial_strings = {
            "emoji": "🚀 🔥 💡 👨‍💻 🎯 ⚠️",
            "chinese": "招聘智能与候选人推荐",
            "japanese": "採用インテリジェンスと分析",
            "arabic": "ذكاء التوظيف وتحليل البيانات",
            "hindi": "भर्ती आसूचना और उम्मीदवार ट्रैकिंग",
            "russian": "Интеллект найма и аналитика воронки",
            "zero_width": "zero\u200bwidth\u200cjoiner\u200dtest",
            "rtl_override": "text\u202eoverride\u202cdirection",
            "quotes_and_escapes": 'Path: C:\\Program Files\\App "with quotes" and \\backslashes\\',
            "html_script": '<script>alert("xss")</script><img src=x onerror=alert(1)>',
            "sql_injection": "'; DROP TABLE Applications; SELECT * FROM '1'='1",
            "json_injection": '{"injected": true, "roles": ["admin"]}',
            "whitespace_mix": "Line1\nLine2\r\nLine3\tTabbed\u00a0NonBreaking",
        }

        for label, text in adversarial_strings.items():
            # Test in Finding observed_fact and title
            finding = Finding(
                finding_id=f"F-{label}",
                title=f"Title {text[:20]}",
                observed_fact=text,
                confidence=Confidence.HIGH,
                caveats=(text,),
            )
            as_dict = finding.to_dict()
            assert as_dict["observed_fact"] == text
            assert as_dict["caveats"] == [text]

            as_json = finding.to_json()
            decoded = json.loads(as_json)
            assert decoded["observed_fact"] == text
            assert decoded["caveats"] == [text]

    def test_extreme_length_string_serialization(self):
        """Very large string inputs (e.g. 50k chars) must serialize and parse without buffer limits."""
        huge_text = "A" * 50_000
        cand = CandidateRecommendation(
            candidate_id="cand-huge",
            action=RecommendationAction.REVIEW,
            rationale=huge_text,
            confidence=Confidence.LOW,
        )
        as_json = cand.to_json()
        decoded = json.loads(as_json)
        assert decoded["rationale"] == huge_text
        assert len(decoded["rationale"]) == 50_000

    def test_roundtrip_rehydration_of_entity_models(self):
        """Entity models serialized to dict must successfully re-hydrate via keyword unpacking."""
        dept = Department("d100", "Analytics", attributes={"region": "US-East"})
        d_dict = dept.to_dict()
        reconstructed_dept = Department(**d_dict)
        assert reconstructed_dept == dept

        person = Person("p100", name="Alex Doe", attributes={"skill": "Python"})
        assert Person(**person.to_dict()) == person

        job = JobOpening("j100", "Principal", department_id="d100", status="open", opened_at="2025-01-01", attributes={"lvl": 6})
        assert JobOpening(**job.to_dict()) == job

        cand = Candidate("c100", person_id="p100", name="Alex Doe", attributes={"vip": True})
        assert Candidate(**cand.to_dict()) == cand

        app = Application("a100", "c100", job_id="j100", source="LinkedIn", status="screen", applied_at="2025-01-05")
        assert Application(**app.to_dict()) == app

        interview = Interview("i100", "a100", status="passed", scheduled_at="2025-01-10T10:00:00Z", completed_at="2025-01-10T11:00:00Z")
        assert Interview(**interview.to_dict()) == interview

        offer = Offer("o100", "a100", status="accepted", offered_at="2025-01-15", responded_at="2025-01-18")
        assert Offer(**offer.to_dict()) == offer

        rec = AirtableRecord("r100", "Offers", fields={"Bonus": 25000}, created_time="2025-01-15T00:00:00Z")
        assert AirtableRecord(**rec.to_dict()) == rec


# =============================================================================
# 3. MetricClaim Boundary & Numerical Extremes
# =============================================================================

class TestMetricClaimEdgeCases:
    """Stress-test MetricClaim numerical boundaries, float representations, and edge cases."""

    def test_numerator_greater_than_denominator_raises_contract_error(self):
        """Various representations of numerator > denominator must always raise ContractError."""
        bad_ratios = [
            (11, 10),
            (1, 0),
            (100, 99),
            (10.0, 9.99999),
            (1.0000000000001, 1.0),
            (1e9 + 1, 1e9),
            (0.1, 0.0),
            (0.00000002, 0.00000001),
        ]
        for num, denom in bad_ratios:
            with pytest.raises(ContractError, match="numerator cannot exceed denominator"):
                MetricClaim(name="bad_ratio", value=1.1, confidence=Confidence.HIGH, numerator=num, denominator=denom)

    def test_negative_bounds_raise_contract_error(self):
        """Negative numerator or denominator in integer or float format must raise ContractError."""
        negatives = [
            (-1, 10, "numerator cannot be negative"),
            (-0.00001, 1.0, "numerator cannot be negative"),
            (-1e-8, 10, "numerator cannot be negative"),
            (5, -1, "denominator cannot be negative"),
            (5.0, -0.00001, "denominator cannot be negative"),
            (1, -100, "denominator cannot be negative"),
            (-5, -5, "numerator cannot be negative"),  # First check hits numerator
        ]
        for num, denom, match_msg in negatives:
            with pytest.raises(ContractError, match=match_msg):
                MetricClaim(name="neg_metric", value=0.0, confidence=Confidence.LOW, numerator=num, denominator=denom)

    def test_zero_values_and_identical_bounds(self):
        """Zero values and equality edge cases must evaluate safely."""
        # 0 / 0 (e.g. empty cohort where conversion cannot be computed)
        m_zero = MetricClaim(name="empty_cohort", value=None, confidence=Confidence.INSUFFICIENT, numerator=0, denominator=0)
        assert m_zero.numerator == 0
        assert m_zero.denominator == 0

        # 0.0 / 0.0
        m_fzero = MetricClaim(name="float_zero", value=0.0, confidence=Confidence.LOW, numerator=0.0, denominator=0.0)
        assert m_fzero.numerator == 0.0
        assert m_fzero.denominator == 0.0

        # 0 / 100 (0% conversion rate)
        m_none_converted = MetricClaim(name="zero_pct", value=0.0, confidence=Confidence.HIGH, numerator=0, denominator=100)
        assert m_none_converted.numerator == 0
        assert m_none_converted.denominator == 100

        # 100 / 100 (100% conversion rate)
        m_all_converted = MetricClaim(name="full_pct", value=1.0, confidence=Confidence.HIGH, numerator=100, denominator=100)
        assert m_all_converted.numerator == 100
        assert m_all_converted.denominator == 100

        # 1.0 / 1.0 float equality
        m_float_full = MetricClaim(name="full_float", value=1.0, confidence=Confidence.HIGH, numerator=1.0, denominator=1.0)
        assert m_float_full.numerator == 1.0
        assert m_float_full.denominator == 1.0

    def test_floating_point_precision_and_extremes(self):
        """Fractional numbers, tiny floats, and large scale floats."""
        # Tiny floats
        m_tiny = MetricClaim(name="tiny", value=0.1, confidence=Confidence.MEDIUM, numerator=1e-12, denominator=1e-11)
        assert m_tiny.numerator == 1e-12
        assert m_tiny.denominator == 1e-11

        # Very large numbers
        m_huge = MetricClaim(name="huge", value=0.5, confidence=Confidence.HIGH, numerator=5e14, denominator=1e15)
        assert m_huge.numerator == 5e14
        assert m_huge.denominator == 1e15

        # Mixed types (int numerator, float denominator)
        m_mixed = MetricClaim(name="mixed", value=0.4, confidence=Confidence.HIGH, numerator=2, denominator=5.0)
        assert m_mixed.numerator == 2
        assert m_mixed.denominator == 5.0

    def test_metric_claim_value_diversity(self):
        """Value field can accept float, int, str, None, bool, or structured data."""
        test_values = [
            0,
            0.0,
            -42,
            -3.14159,
            "Unknown — insufficient evidence",
            "N/A",
            None,
            True,
            False,
            {"tier": "gold", "score": 98},
        ]
        for val in test_values:
            claim = MetricClaim(name="diverse_metric", value=val, confidence=Confidence.HIGH)
            assert claim.value == val
            as_dict = claim.to_dict()
            assert as_dict["value"] == val
            as_json = claim.to_json()
            decoded = json.loads(as_json)
            assert decoded["value"] == val

    def test_metric_claim_nan_inf_and_precision(self):
        """Test behavior of NaN, Inf, and IEEE 754 precision in MetricClaim."""
        # 1. math.nan in numerator or denominator or float value must raise ContractError
        with pytest.raises(ContractError, match="numerator cannot be NaN"):
            MetricClaim(name="nan_num", value=0.0, confidence=Confidence.LOW, numerator=math.nan, denominator=10.0)

        with pytest.raises(ContractError, match="denominator cannot be NaN"):
            MetricClaim(name="nan_denom", value=0.0, confidence=Confidence.LOW, numerator=1.0, denominator=math.nan)

        with pytest.raises(ContractError, match="value cannot be NaN"):
            MetricClaim(name="nan_val", value=math.nan, confidence=Confidence.LOW)

        with pytest.raises(ContractError, match="value cannot be NaN"):
            MetricClaim(metric="nan_val_metric", value=float("nan"), confidence=Confidence.LOW)

        # 2. math.inf in numerator
        with pytest.raises(ContractError, match="numerator cannot exceed denominator"):
            MetricClaim(name="inf_claim", value=0.0, confidence=Confidence.LOW, numerator=math.inf, denominator=10.0)

        # 3. -math.inf in numerator
        with pytest.raises(ContractError, match="numerator cannot be negative"):
            MetricClaim(name="neg_inf", value=0.0, confidence=Confidence.LOW, numerator=-math.inf, denominator=10.0)

        # 4. IEEE 754 rounding: 0.1 + 0.2 is 0.30000000000000004
        # In a strict > comparison without tolerance, 0.1 + 0.2 > 0.3 is True!
        # When calculating metrics from fractions (e.g. 1/10 + 2/10 vs 3/10),
        # strict > will reject valid equivalent sums unless math.isclose or rounding is used.
        with pytest.raises(ContractError, match="numerator cannot exceed denominator"):
            MetricClaim(name="precision_claim", value=1.0, confidence=Confidence.HIGH, numerator=0.1 + 0.2, denominator=0.3)

    def test_metric_claim_metric_kwarg_and_slotted_immutability(self):
        """MetricClaim accepts metric keyword arg matching PROJECT.md contract while maintaining slots."""
        claim1 = MetricClaim(metric="offer_acceptance_rate", value=0.85, confidence=Confidence.HIGH, numerator=17, denominator=20)
        assert claim1.metric == "offer_acceptance_rate"
        assert claim1.name == "offer_acceptance_rate"
        assert not hasattr(claim1, "__dict__")

        claim2 = MetricClaim(name="source_efficiency", value=0.4, confidence=Confidence.MEDIUM)
        assert claim2.metric == "source_efficiency"
        assert claim2.name == "source_efficiency"
        assert not hasattr(claim2, "__dict__")

        claim3 = MetricClaim(metric="same", name="same", value=1.0, confidence=Confidence.HIGH)
        assert claim3.metric == "same"

        with pytest.raises(ContractError, match="conflicting 'name' and 'metric'"):
            MetricClaim(name="alpha", metric="beta", value=0.5, confidence=Confidence.LOW)


# =============================================================================
# 4. Operational Contracts & Security / Safety Edge Cases
# =============================================================================

class TestOperationalContractsGuardrails:
    """Stress-test CandidateRecommendation human review guardrails and contract rules."""

    def test_candidate_recommendation_falsy_review_values_all_fail(self):
        """Any falsy value passed to requires_human_review must raise ContractError."""
        falsy_values = [False, 0, 0.0, "", None, (), [], {}]
        for falsy in falsy_values:
            with pytest.raises(ContractError, match="candidate recommendations must require human review"):
                CandidateRecommendation(
                    candidate_id="c-falsy",
                    action=RecommendationAction.REVIEW,
                    rationale="Test falsy review",
                    confidence=Confidence.LOW,
                    requires_human_review=falsy,
                )

    def test_unauthorized_candidate_action_verbs_blocked(self):
        """Hostile / autonomous action verbs must be rejected."""
        unauthorized = [
            "reject",
            "auto_reject",
            "terminate",
            "hire",
            "fire",
            "dismiss",
            "delete",
            "drop",
            "pass",
            "fail",
            "offer",
            "extend",
            "APPROVED",
            "REJECTED",
        ]
        for verb in unauthorized:
            with pytest.raises(ContractError, match="invalid recommendation action"):
                CandidateRecommendation(
                    candidate_id="c-bad",
                    action=verb,
                    rationale="Attempting unauthorized action",
                    confidence=Confidence.MEDIUM,
                )

    def test_calendar_date_edge_cases_rigor(self):
        """Rigorous validation of calendar dates (leap years, month days, timestamps)."""
        # Valid leap day
        app_leap = Application("a-leap", "c1", applied_at="2024-02-29")
        assert app_leap.applied_at == "2024-02-29"

        # Invalid leap day in non-leap year (2023)
        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Application("a-bad-leap", "c1", applied_at="2023-02-29")

        # Invalid month 13
        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Application("a-bad-month", "c1", applied_at="2025-13-01")

        # Invalid day 32
        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Application("a-bad-day", "c1", applied_at="2025-01-32")

        # Invalid day in 30-day month (April 31)
        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Application("a-bad-apr", "c1", applied_at="2025-04-31")

        # Invalid timestamp hour 25
        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Interview("i-bad-hr", "a1", scheduled_at="2025-01-10T25:00:00Z")

        # Epoch numeric timestamps (must be rejected - ISO-8601 string required)
        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Offer("o-epoch", "a1", offered_at=1700000000)

    def test_mapping_type_validation_on_records_and_evidence(self):
        """Passing non-mapping objects to fields, attributes, filters, or payload must raise ContractError."""
        bad_mappings = ["not_a_dict", [("key", "val")], 12345, True]
        for bad in bad_mappings:
            with pytest.raises(ContractError, match="fields must be a mapping"):
                AirtableRecord("r1", "Candidates", fields=bad)

            with pytest.raises(ContractError, match="attributes must be a mapping"):
                Department("d1", "Eng", attributes=bad)

            with pytest.raises(ContractError, match="filters must be a mapping"):
                EvidenceReference("source", filters=bad)

            with pytest.raises(ContractError, match="payload must be a mapping"):
                AgentRequest("req1", "agent", payload=bad)
