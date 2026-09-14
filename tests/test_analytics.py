"""Comprehensive test suite for Milestone 3: Deterministic Analytics Engine.

Tests cover:
1. Q1 Table row counts across canonical tables and synthetic fixtures.
2. Q2 Recruiting source effectiveness, role mix, effort touches, yield, ranking, and sinks.
3. Q3 Offer acceptance rate with explicit formal denominator justification and confidence scoring.
4. Q4 Funnel transitions, sequential pass-through conversion, aging, bottlenecks, and stalled apps.
5. Sensitivity analysis and counterfactual anomaly exclusions.
6. Envelope normalization (flat vs nested Airtable record envelopes).
7. AnalyticsEngine orchestration, claim aggregation, and question-specific filtering.
8. Contract compliance, MetricClaim invariants (0 <= numerator <= denominator), and serialization.
9. Deterministic offline pure-Python execution with zero network calls and zero LLM dependencies.
"""

from __future__ import annotations

from datetime import date
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
    _flatten_record,
    _flatten_tables,
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


@pytest.fixture
def snapshot() -> dict[str, list[dict[str, Any]]]:
    """Backward-compatible minimal test fixture."""
    return {
        "Applications": [
            {"id": "a1", "candidate_id": "c1", "source": "Referral", "department": "Eng", "status": "hired", "applied_at": "2025-01-01", "updated_at": "2025-01-20"},
            {"id": "a2", "candidate_id": "c2", "source": "Job board", "department": "Eng", "status": "interview", "applied_at": "2025-01-10", "updated_at": "2025-01-15"},
            {"id": "a3", "candidate_id": "c3", "source": "Referral", "department": "Sales", "status": "screening", "applied_at": "2025-01-12", "updated_at": "2025-01-13"},
        ],
        "Candidates": [{"id": "c1", "status": "hired"}, {"id": "c2", "status": "active"}, {"id": "c3", "status": "active"}],
        "Interviews": [{"id": "i1", "application_id": "a2"}],
        "Offers": [{"id": "o1", "application_id": "a1", "status": "accepted"}],
    }


# ===========================================================================
# 1. Q1 Table Counts Tests
# ===========================================================================

class TestTableCountsQ1:
    """Verify deterministic record counts across canonical tables and fixtures."""

    def test_table_counts_canonical_coverage(self, clean_snapshot):
        counts = table_counts(clean_snapshot)
        for table in CANONICAL_TABLES:
            assert table in counts, f"Missing canonical table {table} in counts"
        assert sum(counts.values()) == 39

    def test_table_counts_clean_snapshot_exact(self, clean_snapshot):
        counts = table_counts(clean_snapshot)
        expected = {
            "Departments": 3,
            "People": 4,
            "Job Openings": 3,
            "Candidates": 8,
            "Applications": 10,
            "Interviews": 6,
            "Offers": 3,
            "Findings": 2,
        }
        for table, expected_count in expected.items():
            assert counts[table] == expected_count

    def test_table_counts_sparse_snapshot(self, sparse_snapshot):
        counts = table_counts(sparse_snapshot)
        for table in CANONICAL_TABLES:
            assert counts.get(table, 0) == 0

    def test_table_counts_empty_dict(self):
        assert table_counts({}) == {}

    def test_table_counts_and_source_metrics_compat(self, snapshot):
        assert table_counts(snapshot)["Applications"] == 3
        metrics = source_effectiveness(snapshot)
        assert metrics["Referral"]["applications"] == 2
        assert metrics["Referral"]["hires"] == 1
        assert metrics["Referral"]["hire_conversion_rate"] == 0.5
        assert metrics["Referral"]["role_mix"] == {"Eng": 1, "Sales": 1}
        assert metrics["Job board"]["interviews"] == 1

    def test_engine_table_counts_metric_claim(self, clean_snapshot):
        engine = AnalyticsEngine(clean_snapshot)
        claim = engine.compute_table_counts()
        assert isinstance(claim, MetricClaim)
        assert claim.metric == "table_row_counts"
        assert claim.value == 39
        assert claim.confidence == Confidence.HIGH  # 39 >= 30
        assert claim.unit == "records"
        assert len(claim.evidence) == 1
        assert claim.evidence[0].source == "airtable_snapshot"
        assert len(claim.evidence[0].record_ids) > 0

    def test_engine_table_counts_sparse_fallback(self, sparse_snapshot):
        engine = AnalyticsEngine(sparse_snapshot)
        claim = engine.compute_table_counts()
        assert claim.value == INSUFFICIENT_FALLBACK
        assert claim.confidence == Confidence.INSUFFICIENT


# ===========================================================================
# 2. Q2 Recruiting Source Effectiveness & Effort Ranking Tests
# ===========================================================================

class TestSourceEffectivenessQ2:
    """Verify source funnel performance, conversion, effort touches, yield, and sinks."""

    def test_source_metrics_clean_snapshot(self, clean_snapshot):
        metrics = source_effectiveness(clean_snapshot)
        assert set(metrics.keys()) == {"Agency", "Careers page", "Job board", "Referral"}

        # Referral: 4 apps, 4 interviews, 3 offers, 2 hires -> 50.0% conversion
        ref = metrics["Referral"]
        assert ref["applications"] == 4
        assert ref["interviews"] == 4
        assert ref["offers"] == 3
        assert ref["hires"] == 2
        assert ref["hire_conversion_rate"] == 0.5
        assert ref["role_mix"] == {"Engineering": 2, "Product": 2}
        assert ref["effort_touches"] == 7
        assert ref["effort_yield"] == pytest.approx(2 / 7)
        assert ref["is_effort_sink"] is False

        # Careers page: 2 apps, 2 interviews, 1 offer, 1 hire -> 50.0% conversion
        car = metrics["Careers page"]
        assert car["applications"] == 2
        assert car["hires"] == 1
        assert car["hire_conversion_rate"] == 0.5
        assert car["effort_touches"] == 3
        assert car["is_effort_sink"] is False

        # Job board: 3 apps, 1 interview, 1 offer, 0 hires -> 0.0% conversion
        jb = metrics["Job board"]
        assert jb["applications"] == 3
        assert jb["interviews"] == 1
        assert jb["offers"] == 1
        assert jb["hires"] == 0
        assert jb["hire_conversion_rate"] == 0.0
        assert jb["effort_touches"] == 2
        assert jb["is_effort_sink"] is True

        # Agency: 1 app, 0 interviews, 0 hires -> 0.0% conversion
        ag = metrics["Agency"]
        assert ag["applications"] == 1
        assert ag["hires"] == 0
        assert ag["is_effort_sink"] is False

    def test_pipeline_effort_sinks_identification(self, clean_snapshot):
        sinks = pipeline_effort_sinks(clean_snapshot)
        assert "Job board" in sinks
        assert "Referral" not in sinks
        assert "Careers page" not in sinks

    def test_source_department_segmentation(self, clean_snapshot):
        segmented = source_department_segmentation(clean_snapshot)
        assert "Referral" in segmented
        assert "Engineering" in segmented["Referral"]
        assert segmented["Referral"]["Engineering"]["applications"] == 2

    def test_source_sparse_snapshot_zero_division(self, sparse_snapshot):
        assert source_effectiveness(sparse_snapshot) == {}
        assert pipeline_effort_sinks(sparse_snapshot) == []

    def test_engine_source_effectiveness_claims(self, clean_snapshot):
        engine = AnalyticsEngine(clean_snapshot)
        claims = engine.compute_source_effectiveness()
        assert len(claims) >= 4
        claim_map = {c.metric: c for c in claims}

        # Conversion claim
        ref_conv = claim_map["source_hire_conversion_rate:Referral"]
        assert ref_conv.value == 0.5
        assert ref_conv.numerator == 2
        assert ref_conv.denominator == 4
        assert ref_conv.unit == "ratio"

        # Top source claim
        top_claim = claim_map["top_recruiting_source"]
        assert top_claim.value in {"Referral", "Careers page"}
        assert top_claim.confidence in {Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH}

        # Sinks claim
        sinks_claim = claim_map["recruiting_effort_sinks"]
        assert "Job board" in str(sinks_claim.value)

    def test_engine_source_sparse_fallback(self, sparse_snapshot):
        engine = AnalyticsEngine(sparse_snapshot)
        claims = engine.compute_source_effectiveness()
        claim_map = {c.metric: c for c in claims}
        assert claim_map["top_recruiting_source"].value == INSUFFICIENT_FALLBACK
        assert claim_map["top_recruiting_source"].confidence == Confidence.INSUFFICIENT


# ===========================================================================
# 3. Q3 Offer Acceptance Rate Tests
# ===========================================================================

class TestOfferAcceptanceRateQ3:
    """Verify offer acceptance rate calculation, denominator justification, and confidence."""

    def test_offer_acceptance_clean_snapshot(self, clean_snapshot):
        oar = offer_acceptance_rate(clean_snapshot)
        assert oar["offers"] == 3
        assert oar["accepted"] == 2
        assert oar["rate"] == pytest.approx(2 / 3)
        assert oar["confidence"] == "low"  # sample size 3 < 10
        assert "denominator_justification" in oar
        assert "Offers table" in oar["denominator_justification"]

    def test_offer_acceptance_sparse_snapshot_zero_division(self, sparse_snapshot):
        oar = offer_acceptance_rate(sparse_snapshot)
        assert oar["offers"] == 0
        assert oar["accepted"] == 0
        assert oar["rate"] == 0.0

    def test_offer_acceptance_empty_dict(self):
        oar = offer_acceptance_rate({})
        assert oar["offers"] == 0
        assert oar["accepted"] == 0
        assert oar["rate"] == 0.0

    def test_offer_acceptance_dirty_snapshot_resilience(self, dirty_snapshot):
        oar = offer_acceptance_rate(dirty_snapshot)
        assert 0.0 <= oar["rate"] <= 1.0
        assert oar["accepted"] <= oar["offers"]

    def test_offer_acceptance_filters_draft_offers(self):
        tables = {
            "Offers": [
                {"id": "o1", "status": "accepted"},
                {"id": "o2", "status": "rejected"},
                {"id": "o3", "status": "draft"},
                {"id": "o4", "status": "rescinded"},
            ]
        }
        oar = offer_acceptance_rate(tables)
        assert oar["offers"] == 2  # draft and rescinded excluded
        assert oar["accepted"] == 1
        assert oar["rate"] == 0.5

    def test_engine_offer_acceptance_metric_claim(self, clean_snapshot):
        engine = AnalyticsEngine(clean_snapshot)
        claim = engine.compute_offer_acceptance_rate()
        assert claim.metric == "offer_acceptance_rate"
        assert claim.value == pytest.approx(2 / 3)
        assert claim.numerator == 2
        assert claim.denominator == 3
        assert claim.confidence == Confidence.LOW
        assert claim.unit == "ratio"
        assert len(claim.caveats) >= 1
        assert "denominator" in claim.caveats[0].lower()

    def test_engine_offer_acceptance_sparse_fallback(self, sparse_snapshot):
        engine = AnalyticsEngine(sparse_snapshot)
        claim = engine.compute_offer_acceptance_rate()
        assert claim.metric == "offer_acceptance_rate"
        assert claim.value == INSUFFICIENT_FALLBACK
        assert claim.confidence == Confidence.INSUFFICIENT
        assert claim.numerator is None
        assert claim.denominator is None


# ===========================================================================
# 4. Q4 Hiring Funnel Diagnosis, Aging, Bottlenecks, and Stalled Apps Tests
# ===========================================================================

class TestHiringFunnelDiagnosisQ4:
    """Verify stage transitions, pass-through rates, aging, bottleneck, and stalled applications."""

    def test_funnel_transitions_clean_snapshot(self, clean_snapshot):
        transitions = funnel_transitions(clean_snapshot)
        assert transitions["hired"] == 3
        assert transitions["interview"] == 2
        assert transitions["offer"] == 2
        assert transitions["rejected"] == 2
        assert transitions["screening"] == 1
        assert sum(transitions.values()) == 10

    def test_funnel_stage_conversions_clean_snapshot(self, clean_snapshot):
        conv = funnel_stage_conversions(clean_snapshot)
        assert "stages" in conv
        assert "transitions" in conv
        assert conv["stages"]["applied"] == 10
        assert conv["stages"]["hired"] == 3
        assert "applied_to_screening" in conv["transitions"]
        trans = conv["transitions"]["applied_to_screening"]
        assert trans["denominator"] == 10
        assert trans["numerator"] >= 1
        assert 0.0 <= trans["conversion_rate"] <= 1.0

    def test_funnel_bottleneck_identification(self, clean_snapshot):
        bn = funnel_bottleneck(clean_snapshot)
        assert bn != "Unknown — insufficient evidence"
        assert "_to_" in bn

    def test_stalled_applications_clean_snapshot_isolates_app003(self, clean_snapshot):
        """As of 2025-02-01 with 14-day threshold, app-003 is the sole stalled application."""
        stalled = stalled_applications(clean_snapshot, threshold_days=14, as_of="2025-02-01")
        assert len(stalled) == 1
        item = stalled[0]
        assert item["application_id"] == "app-003"
        assert item["status"] == "screening"
        assert item["days_stalled"] == 22

    def test_stalled_applications_excludes_terminal_statuses(self, clean_snapshot):
        """Hired and rejected applications are terminal and must never be flagged as stalled."""
        stalled = stalled_applications(clean_snapshot, threshold_days=1, as_of="2025-02-01")
        stalled_ids = {s["application_id"] for s in stalled}
        terminal_ids = {"app-001", "app-004", "app-007", "app-009", "app-010"}
        assert stalled_ids.isdisjoint(terminal_ids)

    def test_application_aging_calculation(self, clean_snapshot):
        ages = aging(clean_snapshot, as_of=date(2025, 2, 1))
        assert len(ages) == 10
        for i in range(len(ages) - 1):
            assert ages[i]["age_days"] >= ages[i + 1]["age_days"]
        assert ages[0]["age_days"] == 30

    def test_application_aging_skips_invalid_dates(self, dirty_snapshot):
        ages = aging(dirty_snapshot, as_of="2025-02-01")
        assert isinstance(ages, list)
        for item in ages:
            assert item["age_days"] >= 0
            assert item["application_id"] != "app-dirty-bad-date"

    def test_funnel_sparse_snapshot(self, sparse_snapshot):
        assert funnel_transitions(sparse_snapshot) == {}
        assert stalled_applications(sparse_snapshot, as_of="2025-02-01") == []
        assert aging(sparse_snapshot, as_of="2025-02-01") == []
        assert funnel_bottleneck(sparse_snapshot) == INSUFFICIENT_FALLBACK

    def test_engine_funnel_diagnosis_claims(self, clean_snapshot):
        engine = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        claims = engine.compute_funnel_diagnosis()
        claim_map = {c.metric: c for c in claims}

        assert "funnel_bottleneck_stage" in claim_map
        assert claim_map["funnel_bottleneck_stage"].value != INSUFFICIENT_FALLBACK
        assert "mean_application_age_days" in claim_map
        assert isinstance(claim_map["mean_application_age_days"].value, (int, float))
        assert "stalled_applications_count" in claim_map
        assert claim_map["stalled_applications_count"].value == 1

    def test_engine_funnel_sparse_fallback(self, sparse_snapshot):
        engine = AnalyticsEngine(sparse_snapshot)
        claims = engine.compute_funnel_diagnosis()
        claim_map = {c.metric: c for c in claims}
        assert claim_map["funnel_bottleneck_stage"].value == INSUFFICIENT_FALLBACK
        assert claim_map["funnel_bottleneck_stage"].confidence == Confidence.INSUFFICIENT
        assert claim_map["mean_application_age_days"].value == INSUFFICIENT_FALLBACK
        assert claim_map["stalled_applications_count"].value == INSUFFICIENT_FALLBACK


# ===========================================================================
# 5. Sensitivity Analysis Tests
# ===========================================================================

class TestSensitivityAnalysis:
    """Verify counterfactual metric recalculations on anomaly exclusions."""

    def test_sensitivity_analysis_counterfactual_rank_inversion(self, dirty_snapshot):
        sens = sensitivity_analysis(dirty_snapshot, {
            "drop_orphan_candidate": ["app-dirty-orphan-cand"],
        })
        assert "baseline" in sens
        assert "drop_orphan_candidate" in sens["scenarios"]

        baseline_ref = sens["baseline"]["Referral"]
        assert baseline_ref["hires"] == 1
        assert baseline_ref["hire_conversion_rate"] == 0.20

        scenario_ref = sens["scenarios"]["drop_orphan_candidate"]["Referral"]
        assert scenario_ref["hires"] == 0
        assert scenario_ref["hire_conversion_rate"] == 0.0

    def test_segmentation_and_sensitivity_compat(self, snapshot):
        segmented = source_department_segmentation(snapshot)
        assert segmented["Referral"]["Eng"]["applications"] == 1
        result = sensitivity_analysis(snapshot, {"drop_a1": ["a1"]})
        assert result["baseline"]["Referral"]["hires"] == 1
        assert result["scenarios"]["drop_a1"]["Referral"]["hires"] == 0


# ===========================================================================
# 6. Envelope Normalization (Flat vs Nested Fields) Tests
# ===========================================================================

class TestEnvelopeNormalization:
    """Verify seamless handling of both flat dictionaries and nested record['fields']."""

    def test_flatten_record_flat_dict(self):
        flat = {"id": "rec01", "source": "Referral", "status": "hired"}
        res = _flatten_record(flat)
        assert res["id"] == "rec01"
        assert res["source"] == "Referral"
        assert res["status"] == "hired"

    def test_flatten_record_nested_fields(self):
        nested = {
            "id": "rec02",
            "fields": {
                "source": "Careers page",
                "status": "interview",
                "department": "Engineering",
            },
        }
        res = _flatten_record(nested)
        assert res["id"] == "rec02"
        assert res["source"] == "Careers page"
        assert res["status"] == "interview"
        assert res["department"] == "Engineering"

    def test_nested_envelope_equivalence(self, clean_snapshot):
        # Create pure nested snapshot where all table records have only {"id": ..., "fields": {...}}
        nested_snapshot: dict[str, list[dict[str, Any]]] = {}
        for table, rows in clean_snapshot.items():
            nested_snapshot[table] = [
                {"id": r.get("id", f"id-{i}"), "fields": {k: v for k, v in r.items() if k != "id"}}
                for i, r in enumerate(rows)
            ]

        # Run analytics on both
        flat_sources = source_effectiveness(clean_snapshot)
        nested_sources = source_effectiveness(nested_snapshot)
        assert flat_sources == nested_sources

        flat_oar = offer_acceptance_rate(clean_snapshot)
        nested_oar = offer_acceptance_rate(nested_snapshot)
        assert flat_oar == nested_oar

        flat_stalled = stalled_applications(clean_snapshot, as_of="2025-02-01")
        nested_stalled = stalled_applications(nested_snapshot, as_of="2025-02-01")
        assert flat_stalled == nested_stalled


# ===========================================================================
# 7. AnalyticsEngine Integration & Result Querying Tests
# ===========================================================================

class TestAnalyticsEngineIntegration:
    """Verify end-to-end AnalyticsEngine orchestration, results, and question filtering."""

    def test_engine_analyze_clean_snapshot(self, clean_snapshot):
        engine = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        result = engine.analyze()
        assert isinstance(result, AnalyticsResult)
        assert len(result.claims) > 10
        assert sum(result.table_counts.values()) == 39
        assert len(result.stalled_applications) == 1

        # Query helper
        oar_claim = result.get_claim("offer_acceptance_rate")
        assert oar_claim is not None
        assert oar_claim.value == pytest.approx(2 / 3)

        # Question filtering
        q1_claims = result.claims_for_question("Q1")
        assert any(c.metric == "table_row_counts" for c in q1_claims)

        q2_claims = result.claims_for_question("Q2")
        assert any(c.metric == "top_recruiting_source" for c in q2_claims)

        q3_claims = result.claims_for_question("Q3")
        assert len(q3_claims) == 1
        assert q3_claims[0].metric == "offer_acceptance_rate"

        q4_claims = result.claims_for_question("Q4")
        assert any(c.metric == "funnel_bottleneck_stage" for c in q4_claims)
        assert any(c.metric == "stalled_applications_count" for c in q4_claims)

    def test_run_analytics_convenience_function(self, clean_snapshot):
        result = run_analytics(clean_snapshot, as_of="2025-02-01")
        assert isinstance(result, AnalyticsResult)
        assert len(result.claims) > 10

    def test_compute_all_claims(self, clean_snapshot):
        engine = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        claims = engine.compute_all_claims()
        assert isinstance(claims, tuple)
        assert all(isinstance(c, MetricClaim) for c in claims)


# ===========================================================================
# 8. Contract Compliance & Invariants Tests
# ===========================================================================

class TestContractComplianceAndInvariants:
    """Enforce domain contracts, MetricClaim invariants (numerator <= denominator), and serialization."""

    def test_metric_claim_invariants_valid(self):
        claim = MetricClaim(
            metric="offer_acceptance_rate",
            value=0.667,
            confidence=Confidence.LOW,
            numerator=2,
            denominator=3,
            unit="ratio",
            evidence=(EvidenceReference(source="airtable_snapshot", table="Offers", record_ids=("off-001", "off-003")),),
            caveats=("Formal offers only",),
        )
        assert claim.metric == "offer_acceptance_rate"
        assert claim.name == "offer_acceptance_rate"
        assert claim.confidence == Confidence.LOW
        assert claim.numerator == 2
        assert claim.denominator == 3

        # Serialization roundtrip
        d = claim.to_dict()
        assert d["name"] == "offer_acceptance_rate"
        assert d["confidence"] == "low"
        json_str = claim.to_json()
        assert "offer_acceptance_rate" in json_str

    def test_metric_claim_invariant_numerator_cannot_exceed_denominator(self):
        with pytest.raises(ValueError):
            MetricClaim(metric="invalid_ratio", value=2.0, numerator=5, denominator=2)

    def test_all_engine_claims_satisfy_invariants(self, clean_snapshot, dirty_snapshot, sparse_snapshot):
        """Verify that every single claim produced across all snapshots satisfies domain invariants."""
        for snap in (clean_snapshot, dirty_snapshot, sparse_snapshot):
            engine = AnalyticsEngine(snap, as_of="2025-02-01")
            claims = engine.compute_all_claims()
            for claim in claims:
                assert isinstance(claim, MetricClaim)
                assert isinstance(claim.metric, str) and len(claim.metric) > 0
                assert isinstance(claim.confidence, Confidence)
                if claim.numerator is not None and claim.denominator is not None:
                    assert claim.numerator <= claim.denominator
                    assert claim.numerator >= 0
                    assert claim.denominator >= 0
                if isinstance(claim.value, float):
                    assert not math.isnan(claim.value)
                    assert not math.isinf(claim.value)
                # Verify evidence references
                assert len(claim.evidence) >= 1
                for ev in claim.evidence:
                    assert isinstance(ev, EvidenceReference)
                    assert isinstance(ev.source, str) and len(ev.source) > 0
                    for rid in ev.record_ids:
                        assert isinstance(rid, str) and len(rid) > 0


# ===========================================================================
# 9. Pure-Python Determinism & Zero Network Tests
# ===========================================================================

class TestDeterminismAndOfflineSafety:
    """Enforce offline execution, zero network sockets, and 100% bit-for-bit reproducibility."""

    def test_deterministic_reproducibility(self, clean_snapshot):
        engine1 = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        res1 = engine1.analyze()
        engine2 = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        res2 = engine2.analyze()

        # Check that dictionary serialization is bit-for-bit identical
        assert res1.to_dict() == res2.to_dict()
        assert res1.to_json() == res2.to_json()

    def test_offline_execution_zero_network(self, clean_snapshot, monkeypatch):
        def guarded_connect(*args, **kwargs):
            raise AssertionError("Network connection attempted during offline analytics execution!")

        monkeypatch.setattr(socket.socket, "connect", guarded_connect)

        # Run entire analytics suite — zero network allowed
        engine = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        result = engine.analyze()
        assert result is not None
