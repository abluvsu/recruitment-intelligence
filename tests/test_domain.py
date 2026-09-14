from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import pytest

from recruitment_intelligence.domain import (
    AgentInput,
    AgentRequest,
    AgentResult,
    AgentStatus,
    AirtableRecord,
    Application,
    Briefing,
    Candidate,
    CandidateRecommendation,
    Confidence,
    ConfidenceBucket,
    ContractError,
    Department,
    Evidence,
    EvidenceReference,
    Finding,
    Interview,
    JobOpening,
    Metric,
    MetricClaim,
    Offer,
    Person,
    Recommendation,
    RecommendationAction,
    Severity,
)
import recruitment_intelligence.domain.contracts as contracts


# =============================================================================
# 1. Imports, Aliases & Error Types
# =============================================================================

def test_domain_aliases_and_backward_compatible_module():
    """Verify vocabulary aliases and contracts module re-exports."""
    assert Evidence is EvidenceReference
    assert Metric is MetricClaim
    assert Recommendation is CandidateRecommendation
    assert AgentInput is AgentRequest
    assert ConfidenceBucket is Confidence

    # contracts.py re-exports all domain models
    assert contracts.Department is Department
    assert contracts.Person is Person
    assert contracts.JobOpening is JobOpening
    assert contracts.Candidate is Candidate
    assert contracts.Application is Application
    assert contracts.Interview is Interview
    assert contracts.Offer is Offer
    assert contracts.AirtableRecord is AirtableRecord
    assert contracts.MetricClaim is MetricClaim
    assert contracts.Finding is Finding
    assert contracts.CandidateRecommendation is CandidateRecommendation
    assert contracts.Briefing is Briefing
    assert contracts.AgentRequest is AgentRequest
    assert contracts.AgentResult is AgentResult


def test_contract_error_hierarchy():
    """ContractError must inherit from ValueError for standard exception catching."""
    assert issubclass(ContractError, ValueError)
    err = ContractError("test violation")
    assert isinstance(err, ValueError)


# =============================================================================
# 2. Enums
# =============================================================================

def test_enums_values_and_types():
    """Verify all domain enum members and string compatibility."""
    assert set(Confidence) == {
        Confidence.HIGH,
        Confidence.MEDIUM,
        Confidence.LOW,
        Confidence.INSUFFICIENT,
    }
    assert Confidence.HIGH.value == "high"
    assert Confidence.HIGH == "high"

    assert set(Severity) == {
        Severity.LOW,
        Severity.MEDIUM,
        Severity.HIGH,
        Severity.CRITICAL,
    }
    assert Severity.CRITICAL.value == "critical"
    assert Severity.CRITICAL == "critical"

    assert set(AgentStatus) == {
        AgentStatus.OK,
        AgentStatus.PARTIAL,
        AgentStatus.ERROR,
    }
    assert AgentStatus.OK.value == "ok"
    assert AgentStatus.OK == "ok"

    assert set(RecommendationAction) == {
        RecommendationAction.REVIEW,
        RecommendationAction.ADVANCE,
        RecommendationAction.ESCALATE,
        RecommendationAction.REQUEST_FEEDBACK,
        RecommendationAction.CLOSE,
    }
    assert RecommendationAction.REVIEW.value == "review"
    assert RecommendationAction.REVIEW == "review"
    assert RecommendationAction.ADVANCE == "advance"
    assert RecommendationAction.ESCALATE == "escalate"
    assert RecommendationAction.REQUEST_FEEDBACK == "request_feedback"
    assert RecommendationAction.CLOSE == "close"


# =============================================================================
# 3. Entity Models: Creation & Defaults
# =============================================================================

def test_all_entity_models_instantiation():
    """Verify all 8 entity models instantiate cleanly with valid fields."""
    dept = Department("dept-1", "Engineering")
    assert dept.department_id == "dept-1"
    assert dept.name == "Engineering"
    assert dept.attributes == {}

    person = Person("p-1")
    assert person.person_id == "p-1"
    assert person.name is None
    assert person.attributes == {}

    job = JobOpening("j-1", "Senior Backend Engineer")
    assert job.job_id == "j-1"
    assert job.title == "Senior Backend Engineer"
    assert job.department_id is None
    assert job.status is None
    assert job.opened_at is None
    assert job.closed_at is None
    assert job.attributes == {}

    cand = Candidate("c-1")
    assert cand.candidate_id == "c-1"
    assert cand.person_id is None
    assert cand.name is None
    assert cand.attributes == {}

    app = Application("app-1", "c-1")
    assert app.application_id == "app-1"
    assert app.candidate_id == "c-1"
    assert app.job_id is None
    assert app.source is None
    assert app.status is None
    assert app.applied_at is None
    assert app.attributes == {}

    interview = Interview("int-1", "app-1")
    assert interview.interview_id == "int-1"
    assert interview.application_id == "app-1"
    assert interview.status is None
    assert interview.scheduled_at is None
    assert interview.completed_at is None
    assert interview.attributes == {}

    offer = Offer("off-1", "app-1")
    assert offer.offer_id == "off-1"
    assert offer.application_id == "app-1"
    assert offer.status is None
    assert offer.offered_at is None
    assert offer.responded_at is None
    assert offer.attributes == {}

    rec = AirtableRecord("rec-1", "Applications")
    assert rec.record_id == "rec-1"
    assert rec.table == "Applications"
    assert rec.fields == {}
    assert rec.created_time is None
    assert rec.modified_time is None
    assert rec.attributes == {}


def test_entity_models_full_fields():
    """Verify entities with all optional fields and mappings populated."""
    dept = Department("dept-1", "Sales", attributes={"cost_center": "CC-101"})
    person = Person("p-1", name="Jane Doe", attributes={"email": "jane@example.com"})
    job = JobOpening(
        "j-1",
        "Lead Dev",
        department_id="dept-1",
        status="open",
        opened_at="2025-01-01",
        closed_at="2025-06-01",
        attributes={"headcount": 1},
    )
    cand = Candidate("c-1", person_id="p-1", name="Jane Doe", attributes={"rating": 5})
    app = Application(
        "app-1",
        "c-1",
        job_id="j-1",
        source="Referral",
        status="interview",
        applied_at="2025-01-10",
        attributes={"channel_detail": "Employee Referral"},
    )
    interview = Interview(
        "int-1",
        "app-1",
        status="completed",
        scheduled_at="2025-01-15T14:00:00Z",
        completed_at="2025-01-15T15:00:00Z",
        attributes={"interviewer": "Alice"},
    )
    offer = Offer(
        "off-1",
        "app-1",
        status="extended",
        offered_at="2025-01-20",
        responded_at="2025-01-22",
        attributes={"salary": 140000},
    )
    rec = AirtableRecord(
        "rec-1",
        "Offers",
        fields={"Amount": 140000},
        created_time="2025-01-20T09:00:00Z",
        modified_time="2025-01-22T10:00:00Z",
        attributes={"custom_tag": "vip"},
    )

    assert dept.attributes["cost_center"] == "CC-101"
    assert person.name == "Jane Doe"
    assert job.status == "open"
    assert cand.person_id == "p-1"
    assert app.source == "Referral"
    assert interview.status == "completed"
    assert offer.status == "extended"
    assert rec.fields["Amount"] == 140000
    assert rec.attributes["custom_tag"] == "vip"


# =============================================================================
# 4. Immutability & Slots Verification
# =============================================================================

@pytest.fixture
def all_model_instances():
    """Provide an instance of every domain model and operational contract."""
    evidence = EvidenceReference(source="airtable.Applications", table="Applications")
    claim = MetricClaim(name="hire_rate", value=0.25, confidence=Confidence.HIGH, numerator=1, denominator=4)
    finding = Finding("F-1", "Funnel Bottleneck", "Drop-off at screening", Confidence.HIGH)
    rec = CandidateRecommendation("c-1", RecommendationAction.REVIEW, "Needs screening", Confidence.MEDIUM)

    return [
        Department("dept-1", "Engineering"),
        Person("p-1"),
        JobOpening("j-1", "Dev"),
        Candidate("c-1"),
        Application("app-1", "c-1"),
        Interview("int-1", "app-1"),
        Offer("off-1", "app-1"),
        AirtableRecord("rec-1", "Applications"),
        evidence,
        claim,
        finding,
        rec,
        Briefing(generated_at="2025-01-01T00:00:00Z", period="2025-W01"),
        AgentRequest("req-1", "orchestrator", payload={"k": "v"}),
        AgentResult("res-1", "orchestrator", status=AgentStatus.OK),
    ]


def test_models_are_slotted_and_frozen(all_model_instances):
    """Verify all domain models define __slots__ and reject mutation."""
    for instance in all_model_instances:
        cls = type(instance)
        # Verify slots exist on class
        assert hasattr(cls, "__slots__"), f"{cls.__name__} must define __slots__"
        assert len(cls.__slots__) > 0, f"{cls.__name__} slots must not be empty"

        # Mutation of existing attribute must raise FrozenInstanceError (or AttributeError)
        first_slot = next(iter(cls.__slots__))
        with pytest.raises((FrozenInstanceError, AttributeError)):
            setattr(instance, first_slot, "mutated_value")

        # Adding new attribute must raise FrozenInstanceError or AttributeError
        with pytest.raises((FrozenInstanceError, AttributeError)):
            setattr(instance, "new_undeclared_attribute", 12345)


# =============================================================================
# 5. Serialization & Unknown Fields Preservation
# =============================================================================

def test_serialization_and_unknown_fields_in_attributes():
    """Verify .to_dict() and .to_json() preserve arbitrary custom attributes."""
    custom_metadata = {
        "legacy_id": "LEGACY-888",
        "tags": ["alpha", "beta"],
        "extra_info": {"notes": "Urgent hire", "score": 9.5},
    }

    dept = Department("d1", "Eng", attributes=custom_metadata)
    d_dict = dept.to_dict()
    assert d_dict["department_id"] == "d1"
    assert d_dict["name"] == "Eng"
    assert d_dict["attributes"] == custom_metadata

    d_json = dept.to_json()
    assert isinstance(d_json, str)
    decoded = json.loads(d_json)
    assert decoded["attributes"]["legacy_id"] == "LEGACY-888"
    assert decoded["attributes"]["tags"] == ["alpha", "beta"]
    assert decoded["attributes"]["extra_info"]["score"] == 9.5

    # AirtableRecord unknown fields in attributes and fields
    rec = AirtableRecord(
        "rec1",
        "Applications",
        fields={"CustomFieldA": 100, "CustomFieldB": [1, 2, 3]},
        attributes={"raw_hash": "abcdef123456"},
    )
    rec_dict = rec.to_dict()
    assert rec_dict["fields"]["CustomFieldA"] == 100
    assert rec_dict["attributes"]["raw_hash"] == "abcdef123456"

    rec_json = rec.to_json()
    decoded_rec = json.loads(rec_json)
    assert decoded_rec["fields"]["CustomFieldB"] == [1, 2, 3]
    assert decoded_rec["attributes"]["raw_hash"] == "abcdef123456"


def test_serialization_all_models_roundtrip(all_model_instances):
    """Verify every model serializes to a valid dict and stable JSON string."""
    for instance in all_model_instances:
        as_dict = instance.to_dict()
        assert isinstance(as_dict, dict)

        as_json = instance.to_json()
        assert isinstance(as_json, str)

        parsed = json.loads(as_json)
        assert isinstance(parsed, dict)


def test_serialization_enums_and_sequences():
    """Enums must serialize to string values and tuples to lists."""
    finding = Finding(
        finding_id="F-1",
        title="High Attrition",
        observed_fact="Screening drops 80%",
        confidence=Confidence.HIGH,
        severity=Severity.CRITICAL,
        evidence=(EvidenceReference("source1", table="Applications"),),
        caveats=("small sample size",),
    )
    d = finding.to_dict()
    assert d["confidence"] == "high"
    assert d["severity"] == "critical"
    assert isinstance(d["evidence"], list)
    assert d["evidence"][0]["source"] == "source1"
    assert d["caveats"] == ["small sample size"]


# =============================================================================
# 6. MetricClaim Validation
# =============================================================================

def test_metric_claim_valid_cases():
    """Valid claims with non-negative numerator and denominator where numerator <= denominator."""
    # 0 <= 10
    m1 = MetricClaim(name="zero_claim", value=0.0, confidence=Confidence.HIGH, numerator=0, denominator=10)
    assert m1.numerator == 0
    assert m1.denominator == 10

    # 5 <= 10
    m2 = MetricClaim(name="half_claim", value=0.5, confidence=Confidence.MEDIUM, numerator=5, denominator=10)
    assert m2.numerator == 5
    assert m2.denominator == 10

    # 10 <= 10
    m3 = MetricClaim(name="full_claim", value=1.0, confidence=Confidence.LOW, numerator=10, denominator=10)
    assert m3.numerator == 10
    assert m3.denominator == 10

    # 0 <= 0
    m4 = MetricClaim(name="zero_zero", value=None, confidence=Confidence.INSUFFICIENT, numerator=0, denominator=0)
    assert m4.numerator == 0
    assert m4.denominator == 0

    # None values
    m5 = MetricClaim(name="no_ratio", value="N/A", confidence=Confidence.LOW)
    assert m5.numerator is None
    assert m5.denominator is None

    # Floats: 2.5 <= 5.0
    m6 = MetricClaim(name="float_ratio", value=0.5, confidence=Confidence.HIGH, numerator=2.5, denominator=5.0)
    assert m6.numerator == 2.5
    assert m6.denominator == 5.0

    # .metric property aliases .name
    assert m6.metric == "float_ratio"


def test_metric_claim_numerator_exceeds_denominator_raises_contract_error():
    """Numerator > denominator must raise ContractError."""
    with pytest.raises(ContractError, match="numerator cannot exceed denominator"):
        MetricClaim(name="invalid", value=1.5, confidence=Confidence.HIGH, numerator=11, denominator=10)

    with pytest.raises(ContractError, match="numerator cannot exceed denominator"):
        MetricClaim(name="invalid_zero_denom", value=1.0, confidence=Confidence.HIGH, numerator=1, denominator=0)


def test_metric_claim_negative_numerator_or_denominator_raises_contract_error():
    """Negative numerator or denominator must raise ContractError."""
    with pytest.raises(ContractError, match="numerator cannot be negative"):
        MetricClaim(name="neg_num", value=-0.1, confidence=Confidence.LOW, numerator=-1, denominator=10)

    with pytest.raises(ContractError, match="denominator cannot be negative"):
        MetricClaim(name="neg_denom", value=0.5, confidence=Confidence.LOW, numerator=5, denominator=-10)

    with pytest.raises(ContractError, match="numerator cannot be negative"):
        MetricClaim(name="both_neg", value=1.0, confidence=Confidence.LOW, numerator=-5, denominator=-10)


def test_metric_claim_invalid_name_or_confidence():
    """Empty name or invalid confidence raises ContractError."""
    with pytest.raises(ContractError, match="name must be a non-empty string"):
        MetricClaim(name="", value=0.5, confidence=Confidence.HIGH)

    with pytest.raises(ContractError, match="name must be a non-empty string"):
        MetricClaim(name="   ", value=0.5, confidence=Confidence.HIGH)

    with pytest.raises(ContractError, match="invalid confidence"):
        MetricClaim(name="valid", value=0.5, confidence="ultra_high")


def test_metric_claim_metric_and_name_interchangeability():
    """Verify MetricClaim can be constructed with either 'metric' or 'name' keyword."""
    m_name = MetricClaim(name="conversion_rate", value=0.75, confidence=Confidence.HIGH)
    assert m_name.name == "conversion_rate"
    assert m_name.metric == "conversion_rate"

    m_metric = MetricClaim(metric="conversion_rate", value=0.75, confidence=Confidence.HIGH)
    assert m_metric.name == "conversion_rate"
    assert m_metric.metric == "conversion_rate"

    m_both_same = MetricClaim(name="rate", metric="rate", value=0.5, confidence=Confidence.MEDIUM)
    assert m_both_same.name == "rate"
    assert m_both_same.metric == "rate"

    with pytest.raises(ContractError, match="conflicting 'name' and 'metric'"):
        MetricClaim(name="rate1", metric="rate2", value=0.5, confidence=Confidence.LOW)

    with pytest.raises(ContractError, match="name must be a non-empty string"):
        MetricClaim(metric="", value=0.5, confidence=Confidence.HIGH)

    with pytest.raises(ContractError, match="name must be a non-empty string"):
        MetricClaim(metric="   ", value=0.5, confidence=Confidence.HIGH)


def test_metric_claim_rejects_nan_values():
    """Verify IEEE 754 NaN in value, numerator, or denominator raises ContractError."""
    import math

    with pytest.raises(ContractError, match="value cannot be NaN"):
        MetricClaim(metric="nan_val", value=math.nan, confidence=Confidence.LOW)

    with pytest.raises(ContractError, match="numerator cannot be NaN"):
        MetricClaim(name="nan_num", value=0.5, confidence=Confidence.HIGH, numerator=math.nan, denominator=10.0)

    with pytest.raises(ContractError, match="denominator cannot be NaN"):
        MetricClaim(metric="nan_denom", value=0.5, confidence=Confidence.HIGH, numerator=5.0, denominator=math.nan)


# =============================================================================
# 7. CandidateRecommendation Validation
# =============================================================================

def test_candidate_recommendation_requires_human_review_enforcement():
    """requires_human_review must be True; False raises ContractError."""
    # Default is True
    r1 = CandidateRecommendation(
        candidate_id="cand-1",
        action=RecommendationAction.REVIEW,
        rationale="Check qualifications",
        confidence=Confidence.HIGH,
    )
    assert r1.requires_human_review is True

    # Explicit True succeeds
    r2 = CandidateRecommendation(
        candidate_id="cand-2",
        action=RecommendationAction.ADVANCE,
        rationale="Passed technical screen",
        confidence=Confidence.HIGH,
        requires_human_review=True,
    )
    assert r2.requires_human_review is True

    # False MUST raise ContractError
    with pytest.raises(ContractError, match="candidate recommendations must require human review"):
        CandidateRecommendation(
            candidate_id="cand-3",
            action=RecommendationAction.REVIEW,
            rationale="Automated pass",
            confidence=Confidence.HIGH,
            requires_human_review=False,
        )


def test_candidate_recommendation_allowed_action_verbs():
    """Allowed actions are strictly review, advance, escalate, request_feedback, close."""
    allowed = ["review", "advance", "escalate", "request_feedback", "close"]
    for act in allowed:
        # String value coercion
        r = CandidateRecommendation(
            candidate_id="c-1",
            action=act,
            rationale=f"Testing {act}",
            confidence=Confidence.MEDIUM,
        )
        assert r.action == RecommendationAction(act)

    # Disallowed actions must raise ContractError / ValueError
    disallowed = ["reject", "auto_reject", "hire", "terminate", "pending", ""]
    for invalid_action in disallowed:
        with pytest.raises((ContractError, ValueError)):
            CandidateRecommendation(
                candidate_id="c-1",
                action=invalid_action,
                rationale="Invalid action test",
                confidence=Confidence.MEDIUM,
            )


def test_candidate_recommendation_fields():
    """Check candidate recommendation supports optional application_id and trims strings."""
    rec = CandidateRecommendation(
        candidate_id="  cand-99  ",
        action=RecommendationAction.ESCALATE,
        rationale="  Needs founder input  ",
        confidence=Confidence.HIGH,
        application_id="  app-99  ",
    )
    assert rec.candidate_id == "cand-99"
    assert rec.rationale == "Needs founder input"
    assert rec.application_id == "app-99"


# =============================================================================
# 8. Date Validation (ISO-8601)
# =============================================================================

def test_iso_date_validation_valid_formats():
    """Verify various valid ISO-8601 date and datetime formats pass."""
    valid_dates = [
        "2025-01-01",
        "2025-01-01T12:00:00",
        "2025-01-01T12:00:00Z",
        "2025-01-01T12:00:00+00:00",
        "2025-01-01T17:30:00+05:30",
        "2025-01-01T12:00:00.123456",
        "2025-01-01T12:00:00.123456Z",
        "2025-01-01T12:00:00.123456+00:00",
    ]
    for d in valid_dates:
        # JobOpening opened_at
        j = JobOpening("j1", "Dev", opened_at=d)
        assert j.opened_at == d

        # Application applied_at
        a = Application("a1", "c1", applied_at=d)
        assert a.applied_at == d

        # Interview scheduled_at and completed_at
        i = Interview("i1", "a1", scheduled_at=d, completed_at=d)
        assert i.scheduled_at == d
        assert i.completed_at == d

        # Offer offered_at and responded_at
        o = Offer("o1", "a1", offered_at=d, responded_at=d)
        assert o.offered_at == d
        assert o.responded_at == d

        # AirtableRecord created_time and modified_time
        r = AirtableRecord("r1", "T", created_time=d, modified_time=d)
        assert r.created_time == d
        assert r.modified_time == d

        # Briefing generated_at
        b = Briefing(generated_at=d, period="2025-W01")
        assert b.generated_at == d


def test_iso_date_validation_invalid_formats_raise_contract_error():
    """Non-ISO date strings or invalid date values must raise ContractError."""
    invalid_dates = [
        "not-a-date",
        "01/01/2025",
        "2025/01/01",
        "2025-13-45",
        "2025-02-30",
        "2025-01-01 25:00:00",
        "January 1, 2025",
        "",
        12345,
        True,
    ]
    for bad_date in invalid_dates:
        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            JobOpening("j1", "Dev", opened_at=bad_date)

        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Application("a1", "c1", applied_at=bad_date)

        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Interview("i1", "a1", scheduled_at=bad_date)

        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Offer("o1", "a1", offered_at=bad_date)

        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            AirtableRecord("r1", "T", created_time=bad_date)

        with pytest.raises(ContractError, match="must be an ISO-8601 string"):
            Briefing(generated_at=bad_date, period="2025-W01")


# =============================================================================
# 9. Non-Empty String Validation
# =============================================================================

def test_non_empty_string_validation():
    """Required entity IDs and names must reject empty string, whitespace, and non-strings."""
    # Department
    with pytest.raises(ContractError, match="department_id must be a non-empty string"):
        Department("", "Eng")
    with pytest.raises(ContractError, match="department_id must be a non-empty string"):
        Department("   ", "Eng")
    with pytest.raises(ContractError, match="name must be a non-empty string"):
        Department("d1", "")
    with pytest.raises(ContractError, match="name must be a non-empty string"):
        Department("d1", "   ")

    # Person
    with pytest.raises(ContractError, match="person_id must be a non-empty string"):
        Person("")
    with pytest.raises(ContractError, match="name must be a non-empty string"):
        Person("p1", name="")

    # JobOpening
    with pytest.raises(ContractError, match="job_id must be a non-empty string"):
        JobOpening("", "Title")
    with pytest.raises(ContractError, match="title must be a non-empty string"):
        JobOpening("j1", "")
    with pytest.raises(ContractError, match="department_id must be a non-empty string"):
        JobOpening("j1", "Title", department_id="")
    with pytest.raises(ContractError, match="status must be a non-empty string"):
        JobOpening("j1", "Title", status="")

    # Candidate
    with pytest.raises(ContractError, match="candidate_id must be a non-empty string"):
        Candidate("")
    with pytest.raises(ContractError, match="person_id must be a non-empty string"):
        Candidate("c1", person_id="")
    with pytest.raises(ContractError, match="name must be a non-empty string"):
        Candidate("c1", name="")

    # Application
    with pytest.raises(ContractError, match="application_id must be a non-empty string"):
        Application("", "c1")
    with pytest.raises(ContractError, match="candidate_id must be a non-empty string"):
        Application("a1", "")
    with pytest.raises(ContractError, match="job_id must be a non-empty string"):
        Application("a1", "c1", job_id="")
    with pytest.raises(ContractError, match="source must be a non-empty string"):
        Application("a1", "c1", source="")
    with pytest.raises(ContractError, match="status must be a non-empty string"):
        Application("a1", "c1", status="")

    # Interview
    with pytest.raises(ContractError, match="interview_id must be a non-empty string"):
        Interview("", "a1")
    with pytest.raises(ContractError, match="application_id must be a non-empty string"):
        Interview("i1", "")
    with pytest.raises(ContractError, match="status must be a non-empty string"):
        Interview("i1", "a1", status="")

    # Offer
    with pytest.raises(ContractError, match="offer_id must be a non-empty string"):
        Offer("", "a1")
    with pytest.raises(ContractError, match="application_id must be a non-empty string"):
        Offer("o1", "")
    with pytest.raises(ContractError, match="status must be a non-empty string"):
        Offer("o1", "a1", status="")

    # AirtableRecord
    with pytest.raises(ContractError, match="record_id must be a non-empty string"):
        AirtableRecord("", "Table")
    with pytest.raises(ContractError, match="table must be a non-empty string"):
        AirtableRecord("r1", "")

    # EvidenceReference
    with pytest.raises(ContractError, match="source must be a non-empty string"):
        EvidenceReference("")
    with pytest.raises(ContractError, match="table must be a non-empty string"):
        EvidenceReference("src", table="")
    with pytest.raises(ContractError, match="record_id must be a non-empty string"):
        EvidenceReference("src", record_ids=("",))

    # Finding
    with pytest.raises(ContractError, match="finding_id must be a non-empty string"):
        Finding("", "Title", "Fact", Confidence.HIGH)
    with pytest.raises(ContractError, match="title must be a non-empty string"):
        Finding("f1", "", "Fact", Confidence.HIGH)
    with pytest.raises(ContractError, match="observed_fact must be a non-empty string"):
        Finding("f1", "Title", "", Confidence.HIGH)

    # CandidateRecommendation
    with pytest.raises(ContractError, match="candidate_id must be a non-empty string"):
        CandidateRecommendation("", RecommendationAction.REVIEW, "Rationale", Confidence.HIGH)
    with pytest.raises(ContractError, match="rationale must be a non-empty string"):
        CandidateRecommendation("c1", RecommendationAction.REVIEW, "", Confidence.HIGH)

    # Briefing
    with pytest.raises(ContractError, match="period must be a non-empty string"):
        Briefing(generated_at="2025-01-01", period="")

    # AgentRequest
    with pytest.raises(ContractError, match="request_id must be a non-empty string"):
        AgentRequest("", "agent", payload={})
    with pytest.raises(ContractError, match="agent must be a non-empty string"):
        AgentRequest("req1", "", payload={})

    # AgentResult
    with pytest.raises(ContractError, match="request_id must be a non-empty string"):
        AgentResult("", "agent", status=AgentStatus.OK)
    with pytest.raises(ContractError, match="agent must be a non-empty string"):
        AgentResult("res1", "", status=AgentStatus.OK)


def test_string_trimming():
    """String values with leading/trailing whitespace must be automatically trimmed."""
    dept = Department("  dept-123  ", "  Finance  ")
    assert dept.department_id == "dept-123"
    assert dept.name == "Finance"

    person = Person("  p-123  ", name="  Bob  ")
    assert person.person_id == "p-123"
    assert person.name == "Bob"


# =============================================================================
# 10. Operational Contracts: EvidenceReference, Finding, Briefing, AgentRequest, AgentResult
# =============================================================================

def test_evidence_reference():
    """Test EvidenceReference creation, filters, record_ids and serialization."""
    ev = EvidenceReference(
        source="analytics.source_effectiveness",
        table="Applications",
        filters={"department": "Engineering"},
        record_ids=("rec1", "rec2"),
        method="group_by",
        query="department='Engineering'",
        caveats=("excludes rescinded",),
    )
    assert ev.source == "analytics.source_effectiveness"
    assert ev.table == "Applications"
    assert ev.filters == {"department": "Engineering"}
    assert ev.record_ids == ("rec1", "rec2")
    assert ev.method == "group_by"
    assert ev.query == "department='Engineering'"
    assert ev.caveats == ("excludes rescinded",)

    # Invalid filters (not a mapping)
    with pytest.raises(ContractError, match="filters must be a mapping"):
        EvidenceReference("source", filters="not-a-mapping")


def test_finding_creation_and_nesting():
    """Test Finding with nested MetricClaim and EvidenceReference."""
    ev = EvidenceReference("analytics.offers", table="Offers", record_ids=("o1", "o2"))
    claim = MetricClaim(
        name="offer_acceptance_rate",
        value=0.75,
        confidence=Confidence.HIGH,
        numerator=3,
        denominator=4,
        evidence=(ev,),
    )
    finding = Finding(
        finding_id="F-101",
        title="High Acceptance Rate",
        observed_fact="75% of extended offers were accepted",
        confidence=Confidence.HIGH,
        evidence=(ev,),
        interpretation="Competitive compensation packages",
        recommendation="Maintain current tier structure",
        caveats=("Sample size is 4",),
        severity=Severity.LOW,
        metric=claim,
        category="offers",
        description="Offer metrics analysis",
        affected_records=("o1", "o2"),
        recommendations=("Maintain tier",),
    )
    assert finding.finding_id == "F-101"
    assert finding.metric is not None
    assert finding.metric.value == 0.75
    assert finding.severity == Severity.LOW

    # Serialization roundtrip with nested structures
    f_dict = finding.to_dict()
    assert f_dict["metric"]["name"] == "offer_acceptance_rate"
    assert f_dict["metric"]["evidence"][0]["source"] == "analytics.offers"
    assert f_dict["severity"] == "low"
    assert f_dict["confidence"] == "high"


def test_briefing_creation_and_nesting():
    """Test Briefing with nested findings, actions, and sequence conversions."""
    rec = CandidateRecommendation(
        candidate_id="c-1",
        action=RecommendationAction.ADVANCE,
        rationale="Top candidate",
        confidence=Confidence.HIGH,
    )
    finding = Finding(
        finding_id="F-1",
        title="Speedy Pipeline",
        observed_fact="Mean time to hire is 14 days",
        confidence=Confidence.HIGH,
    )
    briefing = Briefing(
        generated_at="2025-01-15T09:00:00Z",
        period="2025-W02",
        what_changed=["3 new offers extended", "1 accepted"],
        urgent_items=["Candidate c-1 offer pending review"],
        findings=[finding],
        candidate_actions=[rec],
        quality_warnings=[],
        next_actions=["Review c-1 offer"],
        confidence=Confidence.HIGH,
        briefing_id="B-20250115",
        executive_summary="Strong hiring velocity this week.",
    )
    assert briefing.period == "2025-W02"
    assert isinstance(briefing.what_changed, tuple)
    assert isinstance(briefing.findings, tuple)
    assert isinstance(briefing.candidate_actions, tuple)
    assert len(briefing.findings) == 1
    assert len(briefing.candidate_actions) == 1

    b_dict = briefing.to_dict()
    assert b_dict["candidate_actions"][0]["action"] == "advance"
    assert b_dict["findings"][0]["finding_id"] == "F-1"

    b_json = briefing.to_json()
    decoded = json.loads(b_json)
    assert decoded["briefing_id"] == "B-20250115"
    assert decoded["candidate_actions"][0]["requires_human_review"] is True


def test_agent_request_and_result():
    """Test AgentRequest and AgentResult contracts."""
    ev = EvidenceReference("source.test")
    req = AgentRequest(
        request_id="req-123",
        agent="interpretation_agent",
        payload={"query": "summarize_funnel"},
        evidence=(ev,),
        prompt="Analyze the funnel",
        provider="mock",
    )
    assert req.request_id == "req-123"
    assert req.agent == "interpretation_agent"
    assert req.payload["query"] == "summarize_funnel"

    # Non-mapping payload raises ContractError
    with pytest.raises(ContractError, match="payload must be a mapping"):
        AgentRequest("req-bad", "agent", payload="not-a-dict")

    # AgentResult
    rec = CandidateRecommendation("c-1", RecommendationAction.REVIEW, "Verify", Confidence.LOW)
    claim = MetricClaim("m1", 10, Confidence.LOW)
    res = AgentResult(
        request_id="req-123",
        agent="interpretation_agent",
        status="ok",
        claims=[claim],
        recommendations=[rec],
        evidence=[ev],
        errors=[],
        message="Execution completed successfully",
    )
    assert res.status is AgentStatus.OK
    assert isinstance(res.claims, tuple)
    assert isinstance(res.recommendations, tuple)
    assert res.message == "Execution completed successfully"

    # Invalid status raises ContractError
    with pytest.raises(ContractError, match="invalid status"):
        AgentResult("r1", "agent", status="nonexistent_status")
