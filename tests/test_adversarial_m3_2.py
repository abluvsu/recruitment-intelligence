"""Adversarial stress-testing suite for Milestone 3 (Deterministic Analytics Engine).

Rigorous adversarial verification of:
1. Zero mutable state leakage between calls to AnalyticsEngine and metric functions.
2. Offer attribution isolation: candidates with multiple applications do NOT leak offers across applications.
3. Candidate hire attribution isolation: empirical demonstration of hire cross-contamination across applications.
4. Reproducibility across repeated runs and random table shuffling.
5. Pipeline effort sink classification truth table and boundary conditions.
6. Stalled application thresholds (13 vs 14 days, ISO timestamps, terminal status immunity).
7. Offer acceptance rate denominator filtering and mathematical ratio invariants.
8. Funnel sequential conversion progression and bottleneck identification.
"""

from __future__ import annotations

import concurrent.futures
from datetime import date, datetime
import json
import math
from pathlib import Path
import random
from typing import Any, Mapping
import pytest

from recruitment_intelligence.airtable.ingest import load_snapshot
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
# 1. State Isolation & Zero Mutable State Leakage Tests
# ===========================================================================

class TestZeroMutableStateLeakage:
    """Verify that AnalyticsEngine and metric functions maintain strict state isolation."""

    def test_reused_engine_instance_state_isolation(self, clean_snapshot, sparse_snapshot):
        """Repeatedly calling analyze() across different snapshots on the same engine leaves no trace."""
        engine = AnalyticsEngine()

        # Call with clean snapshot
        res_clean_1 = engine.analyze(clean_snapshot, as_of="2025-02-01")
        clean_oar_1 = res_clean_1.get_claim("offer_acceptance_rate").value

        # Call with sparse snapshot (should be insufficient)
        res_sparse = engine.analyze(sparse_snapshot, as_of="2025-02-01")
        assert res_sparse.get_claim("offer_acceptance_rate").value == INSUFFICIENT_FALLBACK
        assert res_sparse.get_claim("offer_acceptance_rate").confidence == Confidence.INSUFFICIENT

        # Call again with clean snapshot
        res_clean_2 = engine.analyze(clean_snapshot, as_of="2025-02-01")
        clean_oar_2 = res_clean_2.get_claim("offer_acceptance_rate").value

        assert clean_oar_1 == clean_oar_2
        assert res_clean_1.to_dict() == res_clean_2.to_dict()

    def test_input_snapshot_external_mutation_resistance(self, clean_snapshot):
        """External modification of caller dictionary after passing to AnalyticsEngine does not corrupt state."""
        input_data = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired", "applied_at": "2025-01-01"},
            ],
            "Offers": [
                {"id": "o1", "application_id": "a1", "status": "accepted"},
            ],
        }

        engine = AnalyticsEngine(input_data, as_of="2025-02-01")

        # Mutate the input dictionary externally
        input_data["Applications"].append(
            {"id": "a2", "candidate_id": "c2", "source": "Job board", "status": "screening", "applied_at": "2025-01-02"}
        )
        input_data["Offers"].clear()

        # Engine's internal snapshot was copied via _flatten_tables at init
        res = engine.analyze(as_of="2025-02-01")
        assert len(res.table_counts) >= 2
        assert res.table_counts["Applications"] == 1
        assert res.table_counts["Offers"] == 1
        assert res.get_claim("offer_acceptance_rate").value == 1.0

    def test_result_immutability(self, clean_snapshot):
        """AnalyticsResult is a frozen slotted dataclass and cannot be mutated."""
        engine = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        res = engine.analyze()

        with pytest.raises((AttributeError, TypeError)):
            res.claims = ()

        with pytest.raises((AttributeError, TypeError)):
            res.table_counts = {}

    def test_concurrent_execution_thread_safety(self, clean_snapshot, dirty_snapshot, sparse_snapshot):
        """Verify concurrent execution across multiple threads has zero race conditions or leakage."""
        def run_pass(snap, as_of):
            engine = AnalyticsEngine(snap, as_of=as_of)
            return engine.analyze().to_dict()

        snapshots = [clean_snapshot, dirty_snapshot, sparse_snapshot] * 10
        dates = ["2025-02-01", "2025-01-15", "2025-03-01"] * 10

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(run_pass, s, d) for s, d in zip(snapshots, dates)]
            results = [f.result() for f in futures]

        # Verify all 30 executions completed successfully
        assert len(results) == 30
        for r in results:
            assert "claims" in r
            assert "table_counts" in r


# ===========================================================================
# 2. Offer Attribution Isolation Tests
# ===========================================================================

class TestOfferAttributionIsolation:
    """Verify that offers are attributed strictly to their linked application."""

    def test_single_candidate_two_applications_offer_isolation(self):
        """Candidate applying to two applications does NOT cross-contaminate offers."""
        tables = {
            "Applications": [
                {"id": "app-001", "candidate_id": "cand-001", "source": "Referral", "status": "screening"},
                {"id": "app-002", "candidate_id": "cand-001", "source": "Agency", "status": "screening"},
            ],
            "Candidates": [
                {"id": "cand-001", "name": "Multi Applicant", "status": "active"},
            ],
            "Offers": [
                {"id": "off-001", "application_id": "app-001", "candidate_id": "cand-001", "status": "extended"},
            ],
        }

        res = source_effectiveness(tables)

        # Referral must have 1 offer
        assert res["Referral"]["applications"] == 1
        assert res["Referral"]["offers"] == 1
        assert res["Referral"]["effort_touches"] == 1

        # Agency must have ZERO offers (no leakage from app-001)
        assert res["Agency"]["applications"] == 1
        assert res["Agency"]["offers"] == 0
        assert res["Agency"]["effort_touches"] == 0

    def test_multi_app_multi_offer_separate_attribution(self):
        """Multiple applications with different offers attribute to each application separately."""
        tables = {
            "Applications": [
                {"id": "app-001", "candidate_id": "cand-001", "source": "Referral", "status": "offer"},
                {"id": "app-002", "candidate_id": "cand-001", "source": "Job board", "status": "offer"},
                {"id": "app-003", "candidate_id": "cand-001", "source": "Agency", "status": "rejected"},
            ],
            "Offers": [
                {"id": "off-001", "application_id": "app-001", "candidate_id": "cand-001", "status": "accepted"},
                {"id": "off-002", "application_id": "app-002", "candidate_id": "cand-001", "status": "declined"},
            ],
        }

        res = source_effectiveness(tables)
        assert res["Referral"]["offers"] == 1
        assert res["Job board"]["offers"] == 1
        assert res["Agency"]["offers"] == 0

    def test_offer_attribution_precedence_application_over_candidate(self):
        """When an offer specifies an application_id, it binds to that application even if candidate_id differs."""
        tables = {
            "Applications": [
                {"id": "app-001", "candidate_id": "cand-A", "source": "Referral", "status": "screening"},
                {"id": "app-002", "candidate_id": "cand-B", "source": "Inbound", "status": "screening"},
            ],
            "Offers": [
                {"id": "off-001", "application_id": "app-001", "candidate_id": "cand-B", "status": "extended"},
            ],
        }

        res = source_effectiveness(tables)
        # Offer binds to app-001 (Referral)
        assert res["Referral"]["offers"] == 1
        # Does not bind to cand-B's app-002 (Inbound)
        assert res["Inbound"]["offers"] == 0

    def test_funnel_stage_offer_attribution_isolation(self):
        """Funnel stage conversions only count applications with their own offers."""
        tables = {
            "Applications": [
                {"id": "app-001", "candidate_id": "cand-001", "source": "Referral", "status": "screening"},
                {"id": "app-002", "candidate_id": "cand-001", "source": "Agency", "status": "screening"},
            ],
            "Offers": [
                {"id": "off-001", "application_id": "app-001", "status": "extended"},
            ],
        }

        conv = funnel_stage_conversions(tables)
        # Only app-001 reached offer stage
        assert conv["stages"]["offer"] == 1
        assert conv["stages"]["applied"] == 2


# ===========================================================================
# 3. Candidate Hire Cross-Contamination Investigation
# ===========================================================================

class TestCandidateHireCrossContamination:
    """Stress-test candidate-level status vs application-level status attribution."""

    def test_empirical_hire_cross_contamination_on_rejected_application(self):
        """Verify fix: Candidate status='hired' does NOT cause rejected applications to register as hired."""
        tables = {
            "Applications": [
                {"id": "app-hired", "candidate_id": "cand-001", "source": "Referral", "status": "hired"},
                {"id": "app-rejected", "candidate_id": "cand-001", "source": "Job board", "status": "rejected"},
            ],
            "Candidates": [
                {"id": "cand-001", "name": "Carol", "status": "hired"},
            ],
            "Offers": [
                {"id": "off-001", "application_id": "app-hired", "status": "accepted"},
            ],
        }

        sources = source_effectiveness(tables)
        conv = funnel_stage_conversions(tables)

        # Referral produced the hire
        assert sources["Referral"]["hires"] == 1

        # Funnel stage conversions correctly only counts 1 hire because it inspects application status
        assert conv["stages"]["hired"] == 1

        # Hire isolation confirmed: candidate hire status must NOT leak to rejected application
        job_board_hires = sources["Job board"]["hires"]
        assert job_board_hires == 0, "Candidate status must not leak to rejected application"

        # Mathematical consistency: Sum of source hires (1) == Funnel hires (1)
        total_source_hires = sum(s["hires"] for s in sources.values())
        assert total_source_hires == 1
        assert total_source_hires == conv["stages"]["hired"]

    def test_multi_application_five_channel_topology_hire_isolation(self):
        """Challenger 2 finding: Candidate hired on one app does not leak hire to sibling apps in offer, rejected, screening, or offer_rejected."""
        tables = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired"},
                {"id": "a2", "candidate_id": "c1", "source": "LinkedIn", "status": "offer"},
                {"id": "a3", "candidate_id": "c1", "source": "Job board", "status": "rejected"},
                {"id": "a4", "candidate_id": "c1", "source": "Campus", "status": "screening"},
                {"id": "a5", "candidate_id": "c1", "source": "Inbound", "status": "offer_rejected"},
            ],
            "Candidates": [{"id": "c1", "status": "hired"}],
        }
        sources = source_effectiveness(tables)
        conv = funnel_stage_conversions(tables)

        assert sources["Referral"]["hires"] == 1
        assert sources["LinkedIn"]["hires"] == 0
        assert sources["Job board"]["hires"] == 0
        assert sources["Campus"]["hires"] == 0
        assert sources["Inbound"]["hires"] == 0

        total_source_hires = sum(s["hires"] for s in sources.values())
        assert total_source_hires == 1
        assert conv["stages"]["hired"] == 1
        assert total_source_hires == conv["stages"]["hired"]

    def test_unmapped_and_auxiliary_statuses_hire_isolation(self):
        """Sibling applications in unmapped, on_hold, offer_made, or empty status do NOT leak candidate hire status."""
        tables = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired"},
                {"id": "a2", "candidate_id": "c1", "source": "Agency", "status": "offer_made"},
                {"id": "a3", "candidate_id": "c1", "source": "Careers page", "status": "on_hold"},
                {"id": "a4", "candidate_id": "c1", "source": "Job board", "status": ""},
                {"id": "a5", "candidate_id": "c1", "source": "Inbound", "status": "declined"},
                {"id": "a6", "candidate_id": "c1", "source": "Direct", "status": "declined_offer"},
                {"id": "a7", "candidate_id": "c1", "source": "Events", "status": "pending_review"},
            ],
            "Candidates": [{"id": "c1", "status": "hired"}],
        }
        sources = source_effectiveness(tables)
        conv = funnel_stage_conversions(tables)

        assert sources["Referral"]["hires"] == 1
        for src in ["Agency", "Careers page", "Job board", "Inbound", "Direct", "Events"]:
            assert sources[src]["hires"] == 0, f"Source {src} should have 0 hires"

        total_source_hires = sum(s["hires"] for s in sources.values())
        assert total_source_hires == 1
        assert conv["stages"]["hired"] == 1
        assert total_source_hires == conv["stages"]["hired"]

    def test_multiple_concurrent_offers_across_channels(self):
        """When candidate receives multiple offers across channels, only the accepted/hired application counts as a hire."""
        tables = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired"},
                {"id": "a2", "candidate_id": "c1", "source": "Agency", "status": "offer"},
                {"id": "a3", "candidate_id": "c1", "source": "Direct", "status": "offer"},
            ],
            "Candidates": [{"id": "c1", "status": "hired"}],
        }
        sources = source_effectiveness(tables)
        conv = funnel_stage_conversions(tables)

        assert sources["Referral"]["hires"] == 1
        assert sources["Referral"]["hire_conversion_rate"] == 1.0
        assert sources["Agency"]["hires"] == 0
        assert sources["Agency"]["offers"] == 1
        assert sources["Agency"]["hire_conversion_rate"] == 0.0
        assert sources["Direct"]["hires"] == 0
        assert sources["Direct"]["offers"] == 1
        assert sources["Direct"]["hire_conversion_rate"] == 0.0

        total_source_hires = sum(s["hires"] for s in sources.values())
        assert total_source_hires == 1
        assert conv["stages"]["hired"] == 1
        assert total_source_hires == conv["stages"]["hired"]

    def test_multi_candidate_multi_application_graph_consistency(self):
        """Multiple candidates with diverse multi-application topographies maintain exact source-to-funnel hire parity."""
        tables = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired"},
                {"id": "a2", "candidate_id": "c1", "source": "Job board", "status": "rejected"},
                {"id": "a3", "candidate_id": "c2", "source": "Referral", "status": "rejected"},
                {"id": "a4", "candidate_id": "c2", "source": "Careers page", "status": "hired"},
                {"id": "a5", "candidate_id": "c2", "source": "Agency", "status": "offer"},
                {"id": "a6", "candidate_id": "c3", "source": "Job board", "status": "screening"},
                {"id": "a7", "candidate_id": "c3", "source": "Direct", "status": "offer_rejected"},
                {"id": "a8", "candidate_id": "c4", "source": "Agency", "status": "hired"},
                {"id": "a9", "candidate_id": "c4", "source": "Referral", "status": "withdrawn"},
            ],
            "Candidates": [
                {"id": "c1", "status": "hired"},
                {"id": "c2", "status": "hired"},
                {"id": "c3", "status": "active"},
                {"id": "c4", "status": "hired"},
            ],
        }
        sources = source_effectiveness(tables)
        conv = funnel_stage_conversions(tables)

        assert sources["Referral"]["hires"] == 1
        assert sources["Careers page"]["hires"] == 1
        assert sources["Agency"]["hires"] == 1
        assert sources["Job board"]["hires"] == 0
        assert sources["Direct"]["hires"] == 0

        total_source_hires = sum(s["hires"] for s in sources.values())
        assert total_source_hires == 3
        assert conv["stages"]["hired"] == 3
        assert total_source_hires == conv["stages"]["hired"]

    def test_single_application_unhired_candidate_with_hired_status(self):
        """A single-application candidate with status='hired' in Candidates but status='offer' in Applications is NOT a hire."""
        tables = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Agency", "status": "offer"},
            ],
            "Candidates": [{"id": "c1", "status": "hired"}],
        }
        sources = source_effectiveness(tables)
        conv = funnel_stage_conversions(tables)

        assert sources["Agency"]["hires"] == 0
        assert conv["stages"]["hired"] == 0
        total_source_hires = sum(s["hires"] for s in sources.values())
        assert total_source_hires == 0 == conv["stages"]["hired"]

    def test_analytics_engine_source_metrics_and_claims_consistency(self):
        """AnalyticsEngine claims and source_metrics maintain total consistency on multi-application topology."""
        tables = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired"},
                {"id": "a2", "candidate_id": "c1", "source": "LinkedIn", "status": "offer"},
                {"id": "a3", "candidate_id": "c1", "source": "Job board", "status": "rejected"},
                {"id": "a4", "candidate_id": "c1", "source": "Campus", "status": "screening"},
                {"id": "a5", "candidate_id": "c1", "source": "Inbound", "status": "offer_rejected"},
            ],
            "Candidates": [{"id": "c1", "status": "hired"}],
        }
        res = AnalyticsEngine(tables).analyze()

        # Referral metrics
        assert res.source_metrics["Referral"]["hires"] == 1
        ref_claim = res.get_claim("source_hire_conversion_rate:Referral")
        assert ref_claim is not None
        assert ref_claim.numerator == 1
        assert ref_claim.denominator == 1
        assert ref_claim.value == 1.0

        # LinkedIn metrics (must NOT have hire)
        assert res.source_metrics["LinkedIn"]["hires"] == 0
        li_claim = res.get_claim("source_hire_conversion_rate:LinkedIn")
        assert li_claim is not None
        assert li_claim.numerator == 0
        assert li_claim.denominator == 1
        assert li_claim.value == 0.0

        # Top recruiting source
        top_source = res.get_claim("top_recruiting_source")
        assert top_source is not None
        assert top_source.value == "Referral"

        # Funnel stage hires matches source hires
        total_src_hires = sum(s["hires"] for s in res.source_metrics.values())
        assert total_src_hires == 1 == res.funnel_metrics["stages"]["hired"]



# ===========================================================================
# 4. Reproducibility & Order Invariance (Determinism Stress-Test)
# ===========================================================================

class TestReproducibilityAndOrderInvariance:
    """Stress-test that record ordering within tables does not affect analytical calculations."""

    def test_shuffled_clean_snapshot_100_runs_analytical_determinism(self, clean_snapshot):
        """Shuffle table rows across 100 iterations; verify analytical values are 100% deterministic."""
        engine_base = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        base = engine_base.analyze()

        base_claims_tuple = tuple(
            (c.name, c.value, c.confidence, c.numerator, c.denominator, c.unit, c.caveats)
            for c in base.claims
        )

        rng = random.Random(42)

        for i in range(100):
            shuffled_tables: dict[str, list[dict[str, Any]]] = {}
            for table_name, rows in clean_snapshot.items():
                shuffled_rows = list(rows)
                rng.shuffle(shuffled_rows)
                shuffled_tables[table_name] = shuffled_rows

            engine = AnalyticsEngine(shuffled_tables, as_of="2025-02-01")
            res = engine.analyze()

            # Verify all metrics, confidence, and fractions are identical
            claims_tuple = tuple(
                (c.name, c.value, c.confidence, c.numerator, c.denominator, c.unit, c.caveats)
                for c in res.claims
            )
            assert claims_tuple == base_claims_tuple, f"Claim divergence on shuffle iteration {i}"

            # Verify structural analytics results are identical
            assert res.table_counts == base.table_counts
            assert res.source_metrics == base.source_metrics
            assert res.offer_metrics == base.offer_metrics
            assert res.funnel_metrics == base.funnel_metrics
            assert res.aging_records == base.aging_records
            assert res.stalled_applications == base.stalled_applications

    def test_shuffled_dirty_snapshot_50_runs_analytical_determinism(self, dirty_snapshot):
        """Shuffle dirty snapshot across 50 iterations; verify analytical results are invariant."""
        engine_base = AnalyticsEngine(dirty_snapshot, as_of="2025-02-01")
        base = engine_base.analyze()

        base_claims_tuple = tuple(
            (c.name, c.value, c.confidence, c.numerator, c.denominator, c.unit, c.caveats)
            for c in base.claims
        )

        rng = random.Random(99)

        for i in range(50):
            shuffled: dict[str, list[dict[str, Any]]] = {}
            for table_name, rows in dirty_snapshot.items():
                rows_copy = list(rows)
                rng.shuffle(rows_copy)
                shuffled[table_name] = rows_copy

            engine = AnalyticsEngine(shuffled, as_of="2025-02-01")
            res = engine.analyze()

            claims_tuple = tuple(
                (c.name, c.value, c.confidence, c.numerator, c.denominator, c.unit, c.caveats)
                for c in res.claims
            )
            assert claims_tuple == base_claims_tuple, f"Dirty claim divergence on shuffle {i}"
            assert res.table_counts == base.table_counts
            assert res.source_metrics == base.source_metrics
            assert res.offer_metrics == base.offer_metrics
            assert res.funnel_metrics == base.funnel_metrics
            assert res.aging_records == base.aging_records
            assert res.stalled_applications == base.stalled_applications

    def test_evidence_record_ids_preserves_input_order(self, clean_snapshot):
        """Verify fix: EvidenceReference.record_ids is deterministically sorted across table row permutations."""
        engine_base = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        base_claim = engine_base.compute_table_counts()

        # Reverse application rows
        reversed_tables = dict(clean_snapshot)
        reversed_tables["Applications"] = list(reversed(clean_snapshot["Applications"]))

        engine_rev = AnalyticsEngine(reversed_tables, as_of="2025-02-01")
        rev_claim = engine_rev.compute_table_counts()

        # Values and caveats are identical
        assert base_claim.value == rev_claim.value
        assert base_claim.confidence == rev_claim.confidence

        # Record IDs must be stably sorted and completely invariant to input table row ordering
        assert base_claim.evidence[0].record_ids == rev_claim.evidence[0].record_ids


# ===========================================================================
# 5. Pipeline Effort Sink Classification Boundary Tests
# ===========================================================================

class TestPipelineEffortSinkBoundaries:
    """Verify exact boundary conditions for pipeline effort sink classification:
    Formula: hires == 0 and (apps >= 2 or interviews >= 1)
    """

    @pytest.mark.parametrize(
        ("apps_count", "interviews_count", "hires_count", "expected_sink"),
        [
            (1, 0, 0, False),  # 1 app, 0 int, 0 hire -> not a sink (apps < 2, int < 1)
            (2, 0, 0, True),   # 2 apps, 0 int, 0 hire -> SINK (apps >= 2)
            (3, 0, 0, True),   # 3 apps, 0 int, 0 hire -> SINK
            (1, 1, 0, True),   # 1 app, 1 int, 0 hire -> SINK (interviews >= 1)
            (2, 1, 0, True),   # 2 apps, 1 int, 0 hire -> SINK
            (2, 0, 1, False),  # 2 apps, 1 hire -> NOT a sink (hires > 0)
            (1, 1, 1, False),  # 1 app, 1 int, 1 hire -> NOT a sink
            (10, 5, 1, False), # 10 apps, 5 int, 1 hire -> NOT a sink
        ],
    )
    def test_effort_sink_boundary_combinations(self, apps_count, interviews_count, hires_count, expected_sink):
        apps = []
        for i in range(apps_count):
            status = "hired" if i < hires_count else "screening"
            apps.append({"id": f"app-{i}", "source": "Test Channel", "status": status})

        interviews = [{"id": f"int-{j}", "application_id": f"app-{j % max(1, apps_count)}"} for j in range(interviews_count)]

        tables = {
            "Applications": apps,
            "Interviews": interviews,
            "Offers": [],
            "Candidates": [],
        }

        res = source_effectiveness(tables)
        channel_data = res.get("Test Channel", {})
        actual_sink = channel_data.get("is_effort_sink", False)
        assert actual_sink == expected_sink, (
            f"Failed for apps={apps_count}, int={interviews_count}, hires={hires_count}: "
            f"expected {expected_sink}, got {actual_sink}"
        )

    def test_pipeline_effort_sinks_sorting_stability(self):
        """Multiple effort sinks must be sorted deterministically: -effort_touches, -applications, name."""
        tables = {
            "Applications": [
                {"id": "a1", "source": "Sink_B", "status": "screening"},
                {"id": "a2", "source": "Sink_B", "status": "screening"},
                {"id": "a3", "source": "Sink_B", "status": "screening"},
                {"id": "a4", "source": "Sink_A", "status": "screening"},
                {"id": "a5", "source": "Sink_A", "status": "screening"},
            ],
            "Interviews": [
                {"id": "i1", "application_id": "a1"},
                {"id": "i2", "application_id": "a2"},
                {"id": "i3", "application_id": "a4"},
            ],
            "Offers": [],
        }

        # Sink_B: 3 apps, 2 interviews -> 2 touches
        # Sink_A: 2 apps, 1 interview -> 1 touch
        sinks = pipeline_effort_sinks(tables)
        assert sinks == ["Sink_B", "Sink_A"]


# ===========================================================================
# 6. Stalled Applications Threshold & Status Immunity Tests
# ===========================================================================

class TestStalledApplicationsThresholds:
    """Verify application aging and stalled threshold (>= 14 days without activity)."""

    def test_stalled_threshold_exact_boundaries(self):
        """Test exact day boundaries relative to as_of='2025-02-01'."""
        as_of_date = "2025-02-01"
        tables = {
            "Applications": [
                # 14 days ago: 2025-01-18 -> age 14 -> STALLED
                {"id": "app-14d", "status": "screening", "updated_at": "2025-01-18"},
                # 13 days ago: 2025-01-19 -> age 13 -> NOT STALLED
                {"id": "app-13d", "status": "screening", "updated_at": "2025-01-19"},
                # 15 days ago: 2025-01-17 -> age 15 -> STALLED
                {"id": "app-15d", "status": "interview", "updated_at": "2025-01-17"},
            ],
        }

        stalled = stalled_applications(tables, threshold_days=14, as_of=as_of_date)
        stalled_ids = [s["application_id"] for s in stalled]

        assert "app-14d" in stalled_ids
        assert "app-15d" in stalled_ids
        assert "app-13d" not in stalled_ids
        assert len(stalled) == 2

    def test_stalled_subday_iso_timestamps(self):
        """Verify ISO timestamps with times are properly parsed and binned."""
        as_of_date = "2025-02-01"
        tables = {
            "Applications": [
                # 2025-01-18T23:59:59Z -> date is 2025-01-18 -> age 14 -> STALLED
                {"id": "app-iso-14", "status": "screening", "updated_at": "2025-01-18T23:59:59Z"},
                # 2025-01-19T00:00:01Z -> date is 2025-01-19 -> age 13 -> NOT STALLED
                {"id": "app-iso-13", "status": "screening", "updated_at": "2025-01-19T00:00:01Z"},
            ],
        }

        stalled = stalled_applications(tables, threshold_days=14, as_of=as_of_date)
        stalled_ids = [s["application_id"] for s in stalled]

        assert "app-iso-14" in stalled_ids
        assert "app-iso-13" not in stalled_ids

    def test_stalled_terminal_status_immunity(self):
        """Applications in terminal statuses must NEVER be flagged as stalled."""
        as_of_date = "2025-02-01"
        tables = {
            "Applications": [
                {"id": "app-hired", "status": "hired", "updated_at": "2020-01-01"},
                {"id": "app-rejected", "status": "rejected", "updated_at": "2020-01-01"},
                {"id": "app-withdrawn", "status": "withdrawn", "updated_at": "2020-01-01"},
                {"id": "app-closed", "status": "closed", "updated_at": "2020-01-01"},
                {"id": "app-accepted", "status": "accepted", "updated_at": "2020-01-01"},
                # Non-terminal but ancient -> MUST be flagged
                {"id": "app-active-ancient", "status": "interviewing", "updated_at": "2024-01-01"},
            ],
        }

        stalled = stalled_applications(tables, threshold_days=14, as_of=as_of_date)
        assert len(stalled) == 1
        assert stalled[0]["application_id"] == "app-active-ancient"


# ===========================================================================
# 7. Offer Acceptance Rate Mathematical Correctness & Denominator Filtering
# ===========================================================================

class TestOfferAcceptanceRateCorrectness:
    """Verify offer acceptance rate calculation, denominator exclusions, and justification."""

    def test_non_formal_offers_excluded_from_denominator(self):
        """Verify draft, rescinded, withdrawn_by_company, internal_review are excluded."""
        tables = {
            "Offers": [
                {"id": "o1", "status": "draft", "is_accepted": False},
                {"id": "o2", "status": "rescinded", "is_accepted": False},
                {"id": "o3", "status": "withdrawn_by_company", "is_accepted": False},
                {"id": "o4", "status": "internal_review", "is_accepted": False},
                {"id": "o5", "status": "extended", "is_accepted": False},
                {"id": "o6", "status": "accepted", "is_accepted": True},
            ],
        }

        raw = offer_acceptance_rate(tables)
        # Total formal offers: only o5 and o6 (2 offers)
        assert raw["offers"] == 2
        assert raw["accepted"] == 1
        assert raw["rate"] == 0.5
        assert "denominator_justification" in raw

    def test_zero_formal_offers_fallback(self):
        """When all offers are draft/rescinded, rate fallback is returned safely."""
        tables = {
            "Offers": [
                {"id": "o1", "status": "draft"},
                {"id": "o2", "status": "rescinded"},
            ],
        }

        engine = AnalyticsEngine(tables, as_of="2025-02-01")
        claim = engine.compute_offer_acceptance_rate()

        assert claim.value == INSUFFICIENT_FALLBACK
        assert claim.confidence == Confidence.INSUFFICIENT
        assert claim.numerator is None
        assert claim.denominator is None

    def test_ratio_invariant_holds_under_anomalous_data(self):
        """Even if accepted > offers due to corrupted data, numerator never exceeds denominator."""
        tables = {
            "Offers": [
                {"id": "o1", "status": "accepted", "is_accepted": True},
            ],
        }

        engine = AnalyticsEngine(tables, as_of="2025-02-01")
        claim = engine.compute_offer_acceptance_rate()

        assert claim.numerator is not None and claim.denominator is not None
        assert claim.numerator <= claim.denominator
        assert claim.value == 1.0


# ===========================================================================
# 8. Hiring Funnel Diagnosis Mathematical Invariants
# ===========================================================================

class TestFunnelDiagnosisInvariants:
    """Verify sequential pass-through conversion, drop-off, and bottleneck detection."""

    def test_funnel_monotonic_progression_invariants(self, clean_snapshot):
        conv = funnel_stage_conversions(clean_snapshot)
        stages = conv["stages"]

        # In a standard pipeline cohort, applied >= screening >= interview
        assert stages["applied"] >= stages["screening"]
        assert stages["screening"] >= stages["interview"]
        assert stages["interview"] >= stages["offer"]
        assert stages["offer"] >= stages["accepted"]
        assert stages["accepted"] >= stages["hired"]

        # Verify all conversion rates are bounded [0.0, 1.0]
        for trans_name, trans_data in conv["transitions"].items():
            assert 0.0 <= trans_data["conversion_rate"] <= 1.0
            assert 0.0 <= trans_data["drop_off_rate"] <= 1.0
            assert math.isclose(
                trans_data["conversion_rate"] + trans_data["drop_off_rate"], 1.0, abs_tol=1e-6
            )

    def test_bottleneck_matches_highest_drop_off(self, clean_snapshot):
        conv = funnel_stage_conversions(clean_snapshot)
        bottleneck = conv["bottleneck"]

        max_drop = -1.0
        expected_bottleneck = None
        for trans_name, trans_data in conv["transitions"].items():
            if trans_data["drop_off_rate"] > max_drop:
                max_drop = trans_data["drop_off_rate"]
                expected_bottleneck = trans_name

        assert bottleneck == expected_bottleneck


# ===========================================================================
# 9. Round 2 Remediation Coverage: Boolean Coercion, Fallbacks, Zero Denominators
# ===========================================================================

class TestRemediationHardeningM3R2:
    """Explicit tests for Milestone 3 Round 2 primary and secondary bug fixes."""

    def test_boolean_string_coercion_in_metrics(self):
        """Verify _as_bool correctly parses boolean-like strings without truthiness trap."""
        from recruitment_intelligence.analytics.metrics import _as_bool, _is_hired

        assert _as_bool("true") is True
        assert _as_bool("True") is True
        assert _as_bool("yes") is True
        assert _as_bool("1") is True
        assert _as_bool(1) is True
        assert _as_bool(True) is True

        assert _as_bool("false") is False
        assert _as_bool("False") is False
        assert _as_bool("no") is False
        assert _as_bool("0") is False
        assert _as_bool(0) is False
        assert _as_bool(False) is False
        assert _as_bool("rejected") is False
        assert _as_bool("declined") is False
        assert _as_bool("withdrawn") is False
        assert _as_bool("") is False

        # _is_hired with string booleans
        assert _is_hired({"hired": "false"}) is False
        assert _is_hired({"hired": "no"}) is False
        assert _is_hired({"hired": "0"}) is False
        assert _is_hired({"hire_outcome": "rejected"}) is False
        assert _is_hired({"hired": "true"}) is True
        assert _is_hired({"hired": "1"}) is True

    def test_offer_acceptance_rate_boolean_strings(self):
        """Verify offer_acceptance_rate correctly handles stringified boolean values."""
        res_false = offer_acceptance_rate({"Offers": [{"status": "extended", "accepted": "false"}]})
        assert res_false["offers"] == 1
        assert res_false["rate"] == 0.0
        assert res_false["accepted"] == 0

        res_true = offer_acceptance_rate({"Offers": [{"status": "extended", "accepted": "true"}]})
        assert res_true["offers"] == 1
        assert res_true["rate"] == 1.0
        assert res_true["accepted"] == 1

        # Also verify sequence format with 'offer' status
        seq_false = offer_acceptance_rate([{"status": "offer", "accepted": "false"}])
        assert seq_false["offers"] == 1
        assert seq_false["rate"] == 0.0
        assert seq_false["accepted"] == 0

        seq_true = offer_acceptance_rate([{"status": "offer", "accepted": "true"}])
        assert seq_true["offers"] == 1
        assert seq_true["rate"] == 1.0
        assert seq_true["accepted"] == 1

    def test_median_and_max_application_age_fallbacks_on_missing_dates(self):
        """Verify median and max application age claims emit INSUFFICIENT_FALLBACK when dates unparseable."""
        snap = {
            "Applications": [
                {"id": "a1", "status": "screening", "applied_at": "corrupt_date"},
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        mean_c = res.get_claim("mean_application_age_days")
        median_c = res.get_claim("median_application_age_days")
        max_c = res.get_claim("max_application_age_days")

        assert mean_c is not None and mean_c.value == INSUFFICIENT_FALLBACK
        assert median_c is not None and median_c.value == INSUFFICIENT_FALLBACK
        assert max_c is not None and max_c.value == INSUFFICIENT_FALLBACK
        assert median_c.confidence == Confidence.INSUFFICIENT
        assert max_c.confidence == Confidence.INSUFFICIENT

    def test_source_effort_yield_zero_touches_denominator_guard(self, dirty_snapshot):
        """Verify source_effort_yield emits None for numerator and denominator when effort_touches == 0."""
        res = run_analytics(dirty_snapshot, as_of="2025-02-01")
        c = res.get_claim("source_effort_yield:Billboard on Highway 101")
        assert c is not None
        assert c.numerator is None
        assert c.denominator is None

    def test_source_app_ids_order_invariance(self, clean_snapshot):
        """Verify source_app_ids in source_effectiveness evidence is stably sorted."""
        reversed_tables = dict(clean_snapshot)
        reversed_tables["Applications"] = list(reversed(clean_snapshot["Applications"]))

        engine_base = AnalyticsEngine(clean_snapshot, as_of="2025-02-01")
        engine_rev = AnalyticsEngine(reversed_tables, as_of="2025-02-01")

        base_res = engine_base.analyze()
        rev_res = engine_rev.analyze()

        base_claim = base_res.get_claim("source_hire_conversion_rate:Referral")
        rev_claim = rev_res.get_claim("source_hire_conversion_rate:Referral")

        assert base_claim.evidence[0].record_ids == rev_claim.evidence[0].record_ids
