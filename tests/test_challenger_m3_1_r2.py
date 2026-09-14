"""Milestone 3 Round 2 Empirical Challenger Test Suite.

Authored by challenger_m3_1_r2 to rigorously challenge and verify:
1. Table row order invariance: permutation, reversal, and random shuffling across
   all fixtures and synthetic large datasets for bit-for-bit identical record_ids
   and identical JSON serialized output.
2. Empty and corrupted date inputs for application aging fallback claims (mean, median, max).
3. Zero touches and edge ratios in source effort yield (numerator/denominator guards).
4. Candidate hire attribution isolation and monotonic funnel stage progression.
5. Boolean string coercion hardening across analytics modules.
"""

from __future__ import annotations

import copy
from datetime import date, datetime
import json
from pathlib import Path
import random
from typing import Any, Mapping
import pytest

from recruitment_intelligence.airtable.ingest import load_snapshot
from recruitment_intelligence.analytics.engine import (
    AnalyticsEngine,
    AnalyticsResult,
    INSUFFICIENT_FALLBACK,
    run_analytics,
)
from recruitment_intelligence.analytics.metrics import (
    _as_bool,
    _is_hired,
    aging,
    funnel_stage_conversions,
    offer_acceptance_rate,
    source_effectiveness,
    stalled_applications,
)
from recruitment_intelligence.domain.models import Confidence, EvidenceReference, MetricClaim

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
# 1. Table Row Order Invariance & JSON Output Determinism
# ===========================================================================

class TestTableRowOrderInvariance:
    """Stress-test table row order invariance across permutations and random shuffling."""

    @pytest.mark.parametrize("fixture_name", ["clean_snapshot.json", "dirty_snapshot.json", "sparse_snapshot.json"])
    def test_fixture_row_reversal_identical_json_and_evidence_ids(self, fixture_name: str):
        """Reversing all table rows produces bit-for-bit identical JSON and record_ids."""
        with open(FIXTURES_DIR / fixture_name, encoding="utf-8") as f:
            data = json.load(f)

        engine_orig = AnalyticsEngine(data, as_of="2025-02-01")
        res_orig = engine_orig.analyze()
        json_orig = res_orig.to_json()

        rev_data = {table: list(reversed(rows)) for table, rows in data.items()}
        engine_rev = AnalyticsEngine(rev_data, as_of="2025-02-01")
        res_rev = engine_rev.analyze()
        json_rev = res_rev.to_json()

        assert json_orig == json_rev, f"JSON output differed on reversal for {fixture_name}"

        # Assert every claim evidence record_ids match bit-for-bit
        for c_orig, c_rev in zip(res_orig.claims, res_rev.claims):
            assert c_orig.metric == c_rev.metric
            assert len(c_orig.evidence) == len(c_rev.evidence)
            for e_orig, e_rev in zip(c_orig.evidence, c_rev.evidence):
                assert e_orig.record_ids == e_rev.record_ids, f"record_ids mismatch on {c_orig.metric}"

    @pytest.mark.parametrize("fixture_name", ["clean_snapshot.json", "dirty_snapshot.json", "sparse_snapshot.json"])
    def test_fixture_random_shuffles_invariance(self, fixture_name: str):
        """Randomly shuffling table records across 50 seeds produces bit-for-bit identical outputs."""
        with open(FIXTURES_DIR / fixture_name, encoding="utf-8") as f:
            data = json.load(f)

        res_orig = AnalyticsEngine(data, as_of="2025-02-01").analyze()
        json_orig = res_orig.to_json()

        for seed in range(50):
            rng = random.Random(seed)
            shuf_data = {table: list(rows) for table, rows in data.items()}
            for table in shuf_data:
                rng.shuffle(shuf_data[table])
            # Also permute the order of table keys
            keys = list(shuf_data.keys())
            rng.shuffle(keys)
            shuf_snapshot = {k: shuf_data[k] for k in keys}

            res_shuf = AnalyticsEngine(shuf_snapshot, as_of="2025-02-01").analyze()
            json_shuf = res_shuf.to_json()
            assert json_orig == json_shuf, f"Shuffle seed {seed} produced different JSON for {fixture_name}"

    def test_synthetic_large_dataset_slice_invariance(self):
        """Ensure sorting and truncation limits ([:100] and [:50]) remain invariant under permutation."""
        # Create 150 applications with unsorted string IDs
        apps = []
        for i in range(150):
            apps.append({
                "id": f"app_{random.randint(1000, 9999)}_{i:03d}",
                "candidate_id": f"cand_{i:03d}",
                "source": "Referral" if i % 2 == 0 else "Direct",
                "status": "applied" if i % 3 == 0 else "screening",
                "applied_at": "2025-01-01",
            })

        snap_a = {"Applications": list(apps)}
        snap_b = {"Applications": list(reversed(apps))}
        rng = random.Random(42)
        shuf_apps = list(apps)
        rng.shuffle(shuf_apps)
        snap_c = {"Applications": shuf_apps}

        res_a = AnalyticsEngine(snap_a, as_of="2025-02-01").analyze()
        res_b = AnalyticsEngine(snap_b, as_of="2025-02-01").analyze()
        res_c = AnalyticsEngine(snap_c, as_of="2025-02-01").analyze()

        assert res_a.to_json() == res_b.to_json()
        assert res_a.to_json() == res_c.to_json()

        # Check table_row_counts has exactly 100 sorted record_ids
        claim_a = res_a.get_claim("table_row_counts")
        claim_b = res_b.get_claim("table_row_counts")
        claim_c = res_c.get_claim("table_row_counts")
        assert len(claim_a.evidence[0].record_ids) == 100
        assert claim_a.evidence[0].record_ids == claim_b.evidence[0].record_ids
        assert claim_a.evidence[0].record_ids == claim_c.evidence[0].record_ids
        # Assert the tuple is lexicographically sorted
        assert list(claim_a.evidence[0].record_ids) == sorted(claim_a.evidence[0].record_ids)


# ===========================================================================
# 2. Empty and Corrupted Date Inputs for Application Aging
# ===========================================================================

class TestEmptyAndCorruptedDateInputsForAging:
    """Verify fallback claims for mean, median, and max application age on empty/corrupted dates."""

    def test_completely_empty_applications_table(self):
        """When Applications table is empty, all age metrics return INSUFFICIENT_FALLBACK."""
        snap: dict[str, list[dict[str, Any]]] = {"Applications": []}
        res = AnalyticsEngine(snap).analyze()

        mean_c = res.get_claim("mean_application_age_days")
        med_c = res.get_claim("median_application_age_days")
        max_c = res.get_claim("max_application_age_days")

        for c in (mean_c, med_c, max_c):
            assert c is not None
            assert c.value == INSUFFICIENT_FALLBACK
            assert c.confidence == Confidence.INSUFFICIENT

    def test_missing_applications_table_in_snapshot(self):
        """When Applications table key is absent altogether, all age metrics return INSUFFICIENT_FALLBACK."""
        snap: dict[str, list[dict[str, Any]]] = {}
        res = AnalyticsEngine(snap).analyze()

        mean_c = res.get_claim("mean_application_age_days")
        med_c = res.get_claim("median_application_age_days")
        max_c = res.get_claim("max_application_age_days")

        for c in (mean_c, med_c, max_c):
            assert c is not None
            assert c.value == INSUFFICIENT_FALLBACK
            assert c.confidence == Confidence.INSUFFICIENT

    @pytest.mark.parametrize("corrupt_val", [
        None,
        "",
        "   ",
        "corrupted_date_string",
        "2025/02/01",
        "9999-99-99",
        "0000-00-00",
        "not-a-timestamp",
        123456789,
        True,
        False,
        [],
        {},
    ])
    def test_corrupted_date_inputs_emit_all_three_fallbacks(self, corrupt_val: Any):
        """Applications with unparseable dates must emit mean, median, AND max fallback claims."""
        snap = {
            "Applications": [
                {"id": "a1", "status": "screening", "applied_at": corrupt_val},
                {"id": "a2", "status": "applied", "application_date": corrupt_val},
            ]
        }
        res = AnalyticsEngine(snap, as_of="2025-02-01").analyze()

        mean_c = res.get_claim("mean_application_age_days")
        med_c = res.get_claim("median_application_age_days")
        max_c = res.get_claim("max_application_age_days")

        assert mean_c is not None and mean_c.value == INSUFFICIENT_FALLBACK
        assert med_c is not None and med_c.value == INSUFFICIENT_FALLBACK
        assert max_c is not None and max_c.value == INSUFFICIENT_FALLBACK

        assert mean_c.confidence == Confidence.INSUFFICIENT
        assert med_c.confidence == Confidence.INSUFFICIENT
        assert max_c.confidence == Confidence.INSUFFICIENT

        for c in (mean_c, med_c, max_c):
            assert c.evidence[0].caveats == ("No parseable application dates found.",)
            assert c.evidence[0].table == "Applications"

    def test_mixed_valid_and_corrupt_dates(self):
        """Mixed valid and corrupted dates calculates valid statistics while gracefully ignoring bad dates."""
        snap = {
            "Applications": [
                {"id": "a1", "applied_at": "2025-01-20"},  # 11 days old as of 2025-01-31
                {"id": "a2", "applied_at": "invalid_date"},
                {"id": "a3", "applied_at": "2025-01-26"},  # 5 days old as of 2025-01-31
                {"id": "a4", "applied_at": None},
                {"id": "a5", "applied_at": "2025-01-11"},  # 20 days old as of 2025-01-31
            ]
        }
        res = AnalyticsEngine(snap, as_of="2025-01-31").analyze()

        mean_c = res.get_claim("mean_application_age_days")
        med_c = res.get_claim("median_application_age_days")
        max_c = res.get_claim("max_application_age_days")

        # Ages: [5, 11, 20] -> sum = 36, mean = 12.0, median = 11, max = 20
        assert mean_c.value == 12.0
        assert med_c.value == 11
        assert max_c.value == 20
        assert mean_c.confidence == Confidence.LOW  # n=3 < 10

    def test_future_application_date_clamping(self):
        """Application date in the future relative to as_of clamps age_days to 0."""
        snap = {
            "Applications": [
                {"id": "a1", "applied_at": "2025-03-01"},  # In future relative to 2025-02-01
            ]
        }
        res = AnalyticsEngine(snap, as_of="2025-02-01").analyze()
        assert res.get_claim("mean_application_age_days").value == 0.0
        assert res.get_claim("median_application_age_days").value == 0
        assert res.get_claim("max_application_age_days").value == 0


# ===========================================================================
# 3. Zero Touches and Edge Ratios in Source Effort Yield
# ===========================================================================

class TestSourceEffortYieldEdgeRatios:
    """Stress-test zero touches, zero denominator guards, and edge ratios in source_effort_yield."""

    def test_zero_touches_and_zero_hires(self):
        """When effort_touches == 0 and hires == 0, numerator and denominator MUST be None."""
        snap = {
            "Applications": [
                {"id": "a1", "source": "Campus", "status": "applied"},
                {"id": "a2", "source": "Campus", "status": "screening"},
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        c = res.get_claim("source_effort_yield:Campus")
        assert c is not None
        assert c.value == 0.0
        assert c.numerator is None
        assert c.denominator is None

    def test_zero_touches_and_phantom_hire_guard(self):
        """When an application has hired=True but 0 interviews and 0 offers (0 touches), guard sets None."""
        snap = {
            "Applications": [
                {"id": "a1", "source": "Direct", "status": "applied", "hired": True},
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        c = res.get_claim("source_effort_yield:Direct")
        assert c is not None
        assert c.value == 0.0
        assert c.numerator is None
        assert c.denominator is None

    def test_positive_touches_and_zero_hires(self):
        """When effort_touches > 0 and hires == 0, numerator is 0 and denominator is effort_touches."""
        snap = {
            "Applications": [
                {"id": "a1", "source": "Cold Outreach", "status": "interview"},
                {"id": "a2", "source": "Cold Outreach", "status": "interview"},
            ],
            "Interviews": [
                {"id": "i1", "application_id": "a1"},
                {"id": "i2", "application_id": "a2"},
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        c = res.get_claim("source_effort_yield:Cold Outreach")
        assert c is not None
        assert c.value == 0.0
        assert c.numerator == 0
        assert c.denominator == 2

    def test_normal_valid_ratio(self):
        """When hires <= effort_touches and touches > 0, ratio is exact."""
        snap = {
            "Applications": [
                {"id": "a1", "source": "Referral", "status": "hired"},
            ],
            "Interviews": [
                {"id": "i1", "application_id": "a1"},
            ],
            "Offers": [
                {"id": "o1", "application_id": "a1", "status": "accepted"},
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        c = res.get_claim("source_effort_yield:Referral")
        assert c is not None
        assert c.value == 0.5  # 1 hire / 2 touches (1 interview + 1 offer)
        assert c.numerator == 1
        assert c.denominator == 2

    def test_anomalous_hires_exceeding_touches(self):
        """When hires > effort_touches, numerator and denominator MUST be None to avoid invalid ratio claims."""
        snap = {
            "Applications": [
                {"id": "a1", "source": "Direct", "status": "applied", "hired": True},
                {"id": "a2", "source": "Direct", "status": "applied", "hired": True},
            ],
            "Interviews": [
                {"id": "i1", "application_id": "a1"},
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        c = res.get_claim("source_effort_yield:Direct")
        assert c is not None
        assert c.value == 2.0  # 2 hires / 1 touch
        assert c.numerator is None
        assert c.denominator is None

    def test_dirty_snapshot_all_source_effort_yield_claims_guarded(self, dirty_snapshot):
        """Verify across all sources in dirty_snapshot that zero-touch sources have None numerator/denominator."""
        res = AnalyticsEngine(dirty_snapshot, as_of="2025-02-01").analyze()
        for claim in res.claims:
            if claim.metric.startswith("source_effort_yield:"):
                if claim.denominator is not None:
                    assert claim.denominator > 0
                    assert claim.numerator is not None
                    assert 0 <= claim.numerator <= claim.denominator
                else:
                    assert claim.numerator is None


# ===========================================================================
# 4. Candidate Hire Attribution Isolation & Funnel Monotonicity
# ===========================================================================

class TestCandidateHireAttributionIsolation:
    """Verify that candidate status does NOT cross-contaminate rejected/withdrawn/active applications."""

    def test_candidate_hired_on_one_app_does_not_credit_rejected_app(self):
        """A candidate with 2 applications credits only the hired application, not the rejected application."""
        snap = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired"},
                {"id": "a2", "candidate_id": "c1", "source": "Job board", "status": "rejected"},
            ],
            "Candidates": [
                {"id": "c1", "status": "hired"}
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        assert res.source_metrics["Referral"]["hires"] == 1
        assert res.source_metrics["Job board"]["hires"] == 0
        total_hires = sum(s["hires"] for s in res.source_metrics.values())
        assert total_hires == 1
        assert res.funnel_metrics["stages"]["hired"] == 1

    def test_candidate_hired_does_not_credit_active_screening_app(self):
        """Candidate status 'hired' is NOT inspected for active applications (applied, screening, interview)."""
        snap = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Agency", "status": "screening"},
            ],
            "Candidates": [
                {"id": "c1", "status": "hired"}
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        assert res.source_metrics["Agency"]["hires"] == 0
        assert res.funnel_metrics["stages"]["hired"] == 0

    def test_funnel_monotonic_progression_across_complex_stages(self):
        """Funnel reached counts must be strictly monotonic: applied >= screening >= interview >= offer >= accepted >= hired."""
        snap = {
            "Applications": [
                {"id": "a1", "status": "applied"},
                {"id": "a2", "status": "screening"},
                {"id": "a3", "status": "interview"},
                {"id": "a4", "status": "offer"},
                {"id": "a5", "status": "accepted"},
                {"id": "a6", "status": "hired"},
                {"id": "a7", "status": "rejected"},
                {"id": "a8", "status": "withdrawn"},
            ],
            "Interviews": [
                {"id": "i1", "application_id": "a7"},
            ],
            "Offers": [
                {"id": "o1", "application_id": "a8", "status": "rescinded"},
            ]
        }
        conv = funnel_stage_conversions(snap)
        stages = conv["stages"]
        assert stages["applied"] >= stages["screening"]
        assert stages["screening"] >= stages["interview"]
        assert stages["interview"] >= stages["offer"]
        assert stages["offer"] >= stages["accepted"]
        assert stages["accepted"] >= stages["hired"]


# ===========================================================================
# 5. Boolean String Coercion Hardening
# ===========================================================================

class TestBooleanCoercionHardening:
    """Stress-test _as_bool helper and metrics against truthiness traps."""

    @pytest.mark.parametrize("falsy_str", ["false", "False", "no", "NO", "0", "rejected", "declined", "withdrawn", ""])
    def test_as_bool_falsy_strings(self, falsy_str: str):
        assert _as_bool(falsy_str) is False
        assert _is_hired({"hired": falsy_str}) is False

    @pytest.mark.parametrize("truthy_str", ["true", "True", "yes", "YES", "1", "accepted", "hired"])
    def test_as_bool_truthy_strings(self, truthy_str: str):
        assert _as_bool(truthy_str) is True
        assert _is_hired({"hired": truthy_str}) is True

    def test_offer_acceptance_rate_string_boolean_accepted(self):
        snap_false = {"Offers": [{"id": "o1", "status": "extended", "accepted": "false"}]}
        res_false = offer_acceptance_rate(snap_false)
        assert res_false["accepted"] == 0
        assert res_false["rate"] == 0.0

        snap_true = {"Offers": [{"id": "o1", "status": "extended", "accepted": "true"}]}
        res_true = offer_acceptance_rate(snap_true)
        assert res_true["accepted"] == 1
        assert res_true["rate"] == 1.0
