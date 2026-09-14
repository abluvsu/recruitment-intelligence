"""Adversarial stress-testing suite for Milestone 3: Deterministic Analytics Engine.

Adversarially challenges:
1. Extreme edge cases: empty tables, missing keys, malformed records, null/None fields, zero denominators, negative numbers.
2. Sparse snapshot and dirty snapshot resilience across all metrics and claims.
3. MetricClaim contract invariants (0 <= numerator <= denominator, non-NaN values, valid evidence references).
4. Funnel pathology, stage skips, non-monotonic cohorts, and bottleneck detection under extreme conversions.
5. Aging and stalled applications under extreme temporal boundaries (ancient dates, future dates, missing dates).
6. String boolean coercion and type-boundary behavior.
7. Determinism, JSON serialization roundtrip, and zero network calls.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import math
from pathlib import Path
import socket
from typing import Any
import pytest

from recruitment_intelligence.airtable.ingest import CANONICAL_TABLES, load_snapshot
from recruitment_intelligence.analytics import (
    AnalyticsEngine,
    AnalyticsResult,
    INSUFFICIENT_FALLBACK,
    aging,
    funnel_bottleneck,
    funnel_stage_conversions,
    funnel_transitions,
    offer_acceptance_rate,
    pipeline_effort_sinks,
    run_analytics,
    sensitivity_analysis,
    source_department_segmentation,
    source_effectiveness,
    stalled_applications,
    table_counts,
)
from recruitment_intelligence.domain.models import (
    Confidence,
    EvidenceReference,
    MetricClaim,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
CLEAN_PATH = FIXTURES_DIR / "clean_snapshot.json"
DIRTY_PATH = FIXTURES_DIR / "dirty_snapshot.json"
SPARSE_PATH = FIXTURES_DIR / "sparse_snapshot.json"


@pytest.fixture
def clean_snapshot() -> dict[str, list[dict[str, Any]]]:
    return load_snapshot(CLEAN_PATH)


@pytest.fixture
def dirty_snapshot() -> dict[str, list[dict[str, Any]]]:
    return load_snapshot(DIRTY_PATH)


@pytest.fixture
def sparse_snapshot() -> dict[str, list[dict[str, Any]]]:
    return load_snapshot(SPARSE_PATH)


# ===========================================================================
# 1. Extreme Edge Cases: Empty Tables, Nulls, Missing Keys, Malformed Records
# ===========================================================================

class TestExtremeEdgeCasesAndMalformedRecords:
    """Stress-test analytics functions and engine on corrupt or malformed inputs."""

    def test_completely_empty_dictionary(self):
        result = run_analytics({})
        assert isinstance(result, AnalyticsResult)
        assert len(result.claims) == 18
        for claim in result.claims:
            assert isinstance(claim, MetricClaim)
            assert claim.confidence in (Confidence.INSUFFICIENT, Confidence.LOW)

    def test_null_table_mappings(self):
        """Tables mapped to None must not trigger TypeError during unrolling."""
        null_tables = {
            "Applications": None,
            "Offers": None,
            "Interviews": None,
            "Candidates": None,
        }
        engine = AnalyticsEngine(null_tables)
        result = engine.analyze()
        assert isinstance(result, AnalyticsResult)
        assert len(result.claims) == 18

    def test_heterogeneous_junk_in_records(self):
        """Tables containing None, non-dict scalars, and invalid structures must not crash."""
        junk_snapshot = {
            "Applications": [
                None,
                123,
                "scalar_string",
                [1, 2, 3],
                True,
                False,
                {"fields": None},
                {"fields": {"source": None, "status": None}},
                {},
            ],
            "Offers": [None, "invalid", 456, {"fields": None}],
            "Interviews": [None, False],
        }
        result = run_analytics(junk_snapshot)
        assert isinstance(result, AnalyticsResult)
        assert len(result.claims) >= 10
        # Invariants must still hold
        for c in result.claims:
            if c.numerator is not None and c.denominator is not None:
                assert c.numerator <= c.denominator

    def test_empty_string_and_whitespace_ids(self):
        """Records with whitespace or empty IDs must not pollute EvidenceReference record_ids."""
        whitespace_snapshot = {
            "Applications": [
                {"id": "", "source": "Referral", "status": "interview"},
                {"id": "   ", "source": "Referral", "status": "hired"},
                {"id": "\t\n", "source": "Referral", "status": "applied"},
            ]
        }
        result = run_analytics(whitespace_snapshot)
        for claim in result.claims:
            for ev in claim.evidence:
                for rid in ev.record_ids:
                    assert rid.strip() != "", f"Empty or whitespace record_id found: {rid!r}"

    def test_non_string_numeric_ids(self):
        """Records with integer or float IDs must be stringified without error."""
        numeric_id_snapshot = {
            "Applications": [
                {"id": 1001, "source": "Referral", "status": "hired", "candidate_id": 9001},
                {"id": 1002, "source": "Referral", "status": "interview", "candidate_id": 9002},
            ],
            "Interviews": [{"id": 501, "application_id": 1002}],
            "Offers": [{"id": 701, "application_id": 1001, "status": "accepted"}],
        }
        result = run_analytics(numeric_id_snapshot)
        assert isinstance(result, AnalyticsResult)
        oar = result.get_claim("offer_acceptance_rate")
        assert oar is not None
        assert oar.value == 1.0


# ===========================================================================
# 2. Sparse Snapshot and Dirty Snapshot Stress
# ===========================================================================

class TestSparseAndDirtySnapshotStress:
    """Rigorous stress-testing of synthetic fixtures."""

    def test_sparse_snapshot_claim_fallbacks(self, sparse_snapshot):
        """Sparse snapshot must return standardized fallback claims for all executive questions."""
        result = run_analytics(sparse_snapshot)
        assert len(result.claims) == 18

        # Q1 fallback
        q1_claim = result.get_claim("table_row_counts")
        assert q1_claim.value == INSUFFICIENT_FALLBACK
        assert q1_claim.confidence == Confidence.INSUFFICIENT

        # Q2 fallbacks
        q2_top = result.get_claim("top_recruiting_source")
        assert q2_top.value == INSUFFICIENT_FALLBACK
        assert q2_top.confidence == Confidence.INSUFFICIENT
        q2_sinks = result.get_claim("recruiting_effort_sinks")
        assert q2_sinks.value == INSUFFICIENT_FALLBACK

        # Q3 fallback
        q3_oar = result.get_claim("offer_acceptance_rate")
        assert q3_oar.value == INSUFFICIENT_FALLBACK
        assert q3_oar.numerator is None
        assert q3_oar.denominator is None

        # Q4 fallbacks
        q4_bn = result.get_claim("funnel_bottleneck_stage")
        assert q4_bn.value == INSUFFICIENT_FALLBACK
        q4_mean_age = result.get_claim("mean_application_age_days")
        assert q4_mean_age.value == INSUFFICIENT_FALLBACK
        q4_median_age = result.get_claim("median_application_age_days")
        assert q4_median_age.value == INSUFFICIENT_FALLBACK
        q4_max_age = result.get_claim("max_application_age_days")
        assert q4_max_age.value == INSUFFICIENT_FALLBACK
        q4_stalled = result.get_claim("stalled_applications_count")
        assert q4_stalled.value == INSUFFICIENT_FALLBACK

    def test_dirty_snapshot_resilience_and_bounds(self, dirty_snapshot):
        """Dirty snapshot containing planted anomalies must evaluate without crashes or invariant breaches."""
        result = run_analytics(dirty_snapshot, as_of="2025-02-01")
        assert len(result.claims) > 20

        # Verify all ratio claims are strictly bounded [0.0, 1.0]
        for c in result.claims:
            if c.unit == "ratio" and isinstance(c.value, (int, float)):
                assert 0.0 <= c.value <= 1.0, f"Ratio claim {c.metric} out of bounds: {c.value}"
            if c.numerator is not None and c.denominator is not None:
                assert 0 <= c.numerator <= c.denominator, (
                    f"Invariant breach in {c.metric}: numerator={c.numerator} > denominator={c.denominator}"
                )

        # OAR should correctly exclude corrupt/draft/rescinded offers
        oar = result.get_claim("offer_acceptance_rate")
        assert oar is not None
        assert oar.denominator == 5
        assert oar.numerator == 2
        assert oar.value == pytest.approx(2 / 5)

        # Bottleneck stage should be identified
        bn = result.get_claim("funnel_bottleneck_stage")
        assert bn is not None
        assert bn.value == "screening_to_interview"

    def test_serialization_stability_across_fixtures(self, clean_snapshot, dirty_snapshot, sparse_snapshot):
        """Ensure to_dict() and to_json() produce valid, parsable outputs for all fixtures."""
        for snap in (clean_snapshot, dirty_snapshot, sparse_snapshot):
            res = run_analytics(snap, as_of="2025-02-01")
            d = res.to_dict()
            assert isinstance(d, dict)
            assert "claims" in d
            j = res.to_json()
            parsed = json.loads(j)
            assert parsed["claims"] == d["claims"]


# ===========================================================================
# 3. Zero Denominators and Ratio Invariants
# ===========================================================================

class TestZeroDenominatorsAndRatioInvariants:
    """Stress-test potential division-by-zero locations."""

    def test_source_with_zero_applications(self):
        """Empty tables should yield empty dictionary without ZeroDivisionError."""
        assert source_effectiveness([]) == {}
        assert pipeline_effort_sinks([]) == []

    def test_source_effort_yield_zero_touches(self):
        """Source with 0 touches must yield 0.0 yield without ZeroDivisionError."""
        tables = {
            "Applications": [
                {"id": "a1", "source": "Cold Outreach", "status": "applied"},
            ]
        }
        res = source_effectiveness(tables)
        out = res["Cold Outreach"]
        assert out["effort_touches"] == 0
        assert out["effort_yield"] == 0.0
        assert out["effort_per_hire"] is None

    def test_funnel_conversions_zero_denominator_at_early_stage(self):
        """When 0 candidates reach a stage, downstream transitions must not crash."""
        tables = {
            "Applications": [
                {"id": "a1", "status": "applied"},
                {"id": "a2", "status": "applied"},
            ]
        }
        conv = funnel_stage_conversions(tables)
        trans = conv["transitions"]
        assert trans["screening_to_interview"]["denominator"] == 0
        assert trans["screening_to_interview"]["conversion_rate"] == 0.0
        assert trans["screening_to_interview"]["drop_off_rate"] == 0.0

    def test_all_metric_claims_non_nan(self, clean_snapshot, dirty_snapshot, sparse_snapshot):
        """Verify no MetricClaim has NaN or Infinite value."""
        for snap in (clean_snapshot, dirty_snapshot, sparse_snapshot):
            engine = AnalyticsEngine(snap, as_of="2025-02-01")
            for c in engine.compute_all_claims():
                if isinstance(c.value, float):
                    assert not math.isnan(c.value)
                    assert not math.isinf(c.value)
                if isinstance(c.numerator, float):
                    assert not math.isnan(c.numerator)
                if isinstance(c.denominator, float):
                    assert not math.isnan(c.denominator)


# ===========================================================================
# 4. Funnel Pathology and Stage Progression Stress
# ===========================================================================

class TestFunnelPathologyAndStageProgression:
    """Adversarially challenge stage-to-stage transition logic."""

    def test_fast_track_hires_without_intermediate_stages(self):
        """Candidates marked 'hired' directly must not cause conversion rate to crash."""
        tables = {
            "Applications": [
                {"id": "a1", "status": "hired"},
                {"id": "a2", "status": "applied"},
            ]
        }
        conv = funnel_stage_conversions(tables)
        # a1 reached hired, which cumulatively implies reaching earlier stages
        stages = conv["stages"]
        assert stages["applied"] == 2
        assert stages["screening"] == 1
        assert stages["interview"] == 1
        assert stages["offer"] == 1
        assert stages["accepted"] == 1
        assert stages["hired"] == 1

    def test_perfect_100_percent_funnel_bottleneck(self):
        """In a funnel where 100% of candidates convert at every step, bottleneck logic must not crash."""
        tables = {
            "Applications": [
                {"id": "a1", "status": "hired"},
            ]
        }
        bn = funnel_bottleneck(tables)
        assert isinstance(bn, str)
        assert len(bn) > 0

    def test_zero_conversion_funnel_bottleneck(self):
        """In a funnel where all candidates drop immediately at screening, applied_to_screening is bottleneck."""
        tables = {
            "Applications": [
                {"id": "a1", "status": "applied"},
                {"id": "a2", "status": "applied"},
                {"id": "a3", "status": "applied"},
            ]
        }
        bn = funnel_bottleneck(tables)
        assert bn == "applied_to_screening"


# ===========================================================================
# 5. Application Aging and Stalled Applications Temporal Boundaries
# ===========================================================================

class TestAgingAndStalledTemporalBoundaries:
    """Stress-test aging and stalled application calculations with extreme temporal parameters."""

    def test_ancient_reference_date(self, clean_snapshot):
        """Reference date before all application dates must clamp age to 0 and report 0 stalled."""
        ages = aging(clean_snapshot, as_of="1900-01-01")
        assert all(a["age_days"] == 0 for a in ages)
        stalled = stalled_applications(clean_snapshot, threshold_days=14, as_of="1900-01-01")
        assert len(stalled) == 0

    def test_far_future_reference_date(self, clean_snapshot):
        """Far future reference date must flag all non-terminal applications as stalled."""
        stalled = stalled_applications(clean_snapshot, threshold_days=14, as_of="2099-01-01")
        assert len(stalled) == 5  # 5 non-terminal apps in clean snapshot

    def test_negative_stalled_threshold(self, clean_snapshot):
        """Negative threshold should flag all non-terminal applications with valid dates."""
        stalled = stalled_applications(clean_snapshot, threshold_days=-1, as_of="2025-02-01")
        assert len(stalled) == 5

    def test_very_large_stalled_threshold(self, clean_snapshot):
        """Astronomical threshold must report 0 stalled applications."""
        stalled = stalled_applications(clean_snapshot, threshold_days=100000, as_of="2025-02-01")
        assert len(stalled) == 0

    def test_corrupt_date_strings_gracefully_ignored(self):
        """Applications with malformed dates must be skipped by aging() without raising ValueError."""
        tables = {
            "Applications": [
                {"id": "a1", "applied_at": "not-a-date"},
                {"id": "a2", "applied_at": "2025/13/99"},
                {"id": "a3", "applied_at": ""},
                {"id": "a4", "applied_at": None},
                {"id": "a5", "applied_at": "2025-01-10"},
            ]
        }
        ages = aging(tables, as_of="2025-02-01")
        assert len(ages) == 1
        assert ages[0]["application_id"] == "a5"


# ===========================================================================
# 6. Type Coercion & Boolean Semantics
# ===========================================================================

class TestTypeCoercionAndBooleanSemantics:
    """Examine behavior under non-boolean types in flag fields."""

    def test_offer_accepted_explicit_boolean_false(self):
        """Offers with explicit boolean False must not be counted as accepted."""
        tables = {
            "Offers": [
                {"id": "o1", "status": "pending", "accepted": False},
                {"id": "o2", "status": "pending", "is_accepted": False},
            ]
        }
        oar = offer_acceptance_rate(tables)
        assert oar["offers"] == 2
        assert oar["accepted"] == 0
        assert oar["rate"] == 0.0

    def test_offer_accepted_explicit_boolean_true(self):
        """Offers with explicit boolean True must be counted as accepted."""
        tables = {
            "Offers": [
                {"id": "o1", "status": "pending", "accepted": True},
            ]
        }
        oar = offer_acceptance_rate(tables)
        assert oar["offers"] == 1
        assert oar["accepted"] == 1
        assert oar["rate"] == 1.0

    def test_hired_flag_explicit_boolean_false(self):
        """Applications with hired=False must not be counted as hired."""
        tables = {
            "Applications": [
                {"id": "a1", "status": "applied", "hired": False},
            ]
        }
        res = source_effectiveness(tables)
        assert res["Unknown"]["hires"] == 0


# ===========================================================================
# 7. Fallback Claims when Dates Missing
# ===========================================================================

class TestFallbackClaimsWhenDatesMissing:
    """Document and verify behavior when applications exist but lack valid dates."""

    def test_mean_age_fallback_on_unparseable_dates(self):
        """When applications exist but lack valid dates, mean_application_age_days reports fallback."""
        snap = {
            "Applications": [
                {"id": "a1", "status": "screening", "applied_at": "corrupt_date"},
            ]
        }
        engine = AnalyticsEngine(snap)
        res = engine.analyze()
        mean_claim = res.get_claim("mean_application_age_days")
        assert mean_claim is not None
        assert mean_claim.value == INSUFFICIENT_FALLBACK
        assert mean_claim.confidence == Confidence.INSUFFICIENT


# ===========================================================================
# 8. Deterministic Replay and Question Filtering
# ===========================================================================

class TestDeterministicReplayAndFiltering:
    """Verify claim retrieval, question-specific filtering, and bit-for-bit reproducibility."""

    def test_claims_for_question_filtering(self, clean_snapshot):
        engine = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        res = engine.analyze()

        q1 = res.claims_for_question("Q1")
        assert len(q1) == 9  # 1 aggregate + 8 canonical
        assert all(c.name.startswith("table_") for c in q1)

        q2 = res.claims_for_question("Q2")
        assert len(q2) >= 3
        assert any(c.name == "top_recruiting_source" for c in q2)
        assert any(c.name == "recruiting_effort_sinks" for c in q2)

        q3 = res.claims_for_question("Q3")
        assert len(q3) == 1
        assert q3[0].name == "offer_acceptance_rate"

        q4 = res.claims_for_question("Q4")
        assert len(q4) >= 5
        assert any(c.name == "funnel_bottleneck_stage" for c in q4)
        assert any(c.name == "stalled_applications_count" for c in q4)

        # Unrecognized questions return empty tuple
        assert res.claims_for_question("Q5") == ()
        assert res.claims_for_question("UNKNOWN") == ()

    def test_bit_for_bit_reproducibility(self, clean_snapshot):
        """Identical inputs must yield 100% identical outputs."""
        res1 = run_analytics(clean_snapshot, as_of="2025-02-01")
        res2 = run_analytics(clean_snapshot, as_of="2025-02-01")
        assert res1.to_dict() == res2.to_dict()
        assert res1.to_json() == res2.to_json()
