"""Milestone 3 Round 3 Empirical Challenger Test Suite.

Authored by challenger_m3_1_r3 to rigorously challenge and verify:
1. Table row order invariance: permutation, reversal, and 100 random shuffles per fixture
   for bit-for-bit identical EvidenceReference.record_ids and identical JSON serialized output.
2. Large synthetic dataset truncation slice invariance under permutation.
3. Empty and corrupted date inputs for application aging fallback claims (mean, median, max).
4. Zero touches, anomalous ratios, and zero denominator guards in source effort yield.
5. Multi-application candidate hire isolation, terminal non-hire statuses, and exact
   source-to-funnel hire invariant parity.
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

class TestTableRowOrderInvarianceM3R3:
    """Stress-test table row order invariance across permutations, reversals, and shuffles."""

    @pytest.mark.parametrize("fixture_name", ["clean_snapshot.json", "dirty_snapshot.json", "sparse_snapshot.json"])
    def test_fixture_row_reversal_bit_for_bit_identical(self, fixture_name: str):
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

        # Assert every single claim evidence record_ids match bit-for-bit
        assert len(res_orig.claims) == len(res_rev.claims)
        for c_orig, c_rev in zip(res_orig.claims, res_rev.claims):
            assert c_orig.metric == c_rev.metric
            assert len(c_orig.evidence) == len(c_rev.evidence)
            for e_orig, e_rev in zip(c_orig.evidence, c_rev.evidence):
                assert e_orig.record_ids == e_rev.record_ids, f"record_ids mismatch on {c_orig.metric}"
                assert e_orig.table == e_rev.table
                assert e_orig.caveats == e_rev.caveats

    @pytest.mark.parametrize("fixture_name", ["clean_snapshot.json", "dirty_snapshot.json", "sparse_snapshot.json"])
    def test_fixture_100_random_shuffles_invariance(self, fixture_name: str):
        """Randomly shuffling table records across 100 seeds produces bit-for-bit identical outputs."""
        with open(FIXTURES_DIR / fixture_name, encoding="utf-8") as f:
            data = json.load(f)

        res_orig = AnalyticsEngine(data, as_of="2025-02-01").analyze()
        json_orig = res_orig.to_json()

        for seed in range(100):
            rng = random.Random(seed * 37 + 7)
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

            # Check record_ids for evidence
            for c_orig, c_shuf in zip(res_orig.claims, res_shuf.claims):
                for e_orig, e_shuf in zip(c_orig.evidence, c_shuf.evidence):
                    assert e_orig.record_ids == e_shuf.record_ids

    def test_synthetic_large_dataset_truncation_invariance(self):
        """Verify that truncations in EvidenceReference are strictly sorted and invariant."""
        # Generate 300 applications, 200 offers, 150 interviews
        rng = random.Random(999)
        apps = [
            {
                "id": f"app_{rng.randint(10000, 99999)}_{i:04d}",
                "candidate_id": f"cand_{i % 80:03d}",
                "source": ["Referral", "LinkedIn", "Agency", "Direct", "Inbound"][i % 5],
                "status": ["applied", "screening", "interview", "offer", "hired", "rejected"][i % 6],
                "applied_at": f"2025-01-{(i % 25) + 1:02d}",
            }
            for i in range(300)
        ]
        interviews = [
            {
                "id": f"int_{rng.randint(10000, 99999)}_{i:04d}",
                "application_id": apps[i % len(apps)]["id"],
                "status": "completed",
            }
            for i in range(150)
        ]
        offers = [
            {
                "id": f"off_{rng.randint(10000, 99999)}_{i:04d}",
                "application_id": apps[i % len(apps)]["id"],
                "status": "accepted" if i % 2 == 0 else "extended",
            }
            for i in range(200)
        ]

        snap_orig = {"Applications": list(apps), "Interviews": list(interviews), "Offers": list(offers)}
        snap_rev = {"Applications": list(reversed(apps)), "Interviews": list(reversed(interviews)), "Offers": list(reversed(offers))}

        shuf_apps = list(apps)
        shuf_ints = list(interviews)
        shuf_offs = list(offers)
        rng.shuffle(shuf_apps)
        rng.shuffle(shuf_ints)
        rng.shuffle(shuf_offs)
        snap_shuf = {"Offers": shuf_offs, "Applications": shuf_apps, "Interviews": shuf_ints}

        res_orig = AnalyticsEngine(snap_orig, as_of="2025-02-01").analyze()
        res_rev = AnalyticsEngine(snap_rev, as_of="2025-02-01").analyze()
        res_shuf = AnalyticsEngine(snap_shuf, as_of="2025-02-01").analyze()

        assert res_orig.to_json() == res_rev.to_json()
        assert res_orig.to_json() == res_shuf.to_json()

        # Check table_row_counts has exactly 100 sorted record_ids
        row_count_claim = res_orig.get_claim("table_row_counts")
        assert len(row_count_claim.evidence[0].record_ids) == 100
        assert list(row_count_claim.evidence[0].record_ids) == sorted(row_count_claim.evidence[0].record_ids)


# ===========================================================================
# 2. Empty and Corrupted Date Inputs for Application Aging
# ===========================================================================

class TestEmptyAndCorruptedDateInputsAgingM3R3:
    """Verify mean, median, and max application age fallback claims on empty and corrupt inputs."""

    def test_completely_empty_and_missing_applications(self):
        """Missing or empty Applications table emits all 3 fallback claims with Confidence.INSUFFICIENT."""
        for snap in [{}, {"Applications": []}]:
            res = AnalyticsEngine(snap).analyze()
            for metric_name in ["mean_application_age_days", "median_application_age_days", "max_application_age_days"]:
                claim = res.get_claim(metric_name)
                assert claim is not None, f"Missing claim {metric_name}"
                assert claim.value == INSUFFICIENT_FALLBACK
                assert claim.confidence == Confidence.INSUFFICIENT
                assert claim.unit == "days" or claim.unit is None

    @pytest.mark.parametrize("corrupt_input", [
        None,
        "",
        "   ",
        "corrupted_string",
        "2025/02/01",
        "9999-99-99",
        "0000-00-00",
        "2025-13-45",
        "2025-02-30",
        1700000000,
        1700000000.5,
        True,
        False,
        [],
        {},
    ])
    def test_corrupted_dates_emit_all_three_fallbacks(self, corrupt_input: Any):
        """Any corrupt date variation emits mean, median, max fallbacks with explicit caveat."""
        snap = {
            "Applications": [
                {"id": "app_c1", "status": "applied", "applied_at": corrupt_input},
                {"id": "app_c2", "status": "screening", "application_date": corrupt_input},
                {"id": "app_c3", "status": "interview", "created_at": corrupt_input},
                {"id": "app_c4", "status": "offer", "date_applied": corrupt_input},
            ]
        }
        res = AnalyticsEngine(snap, as_of="2025-02-01").analyze()

        for metric in ["mean_application_age_days", "median_application_age_days", "max_application_age_days"]:
            claim = res.get_claim(metric)
            assert claim is not None
            assert claim.value == INSUFFICIENT_FALLBACK
            assert claim.confidence == Confidence.INSUFFICIENT
            assert claim.evidence[0].caveats == ("No parseable application dates found.",)
            assert claim.evidence[0].table == "Applications"

    def test_mixed_dates_statistical_precision(self):
        """Valid dates compute accurate mean, median, max while skipping corrupt dates."""
        snap = {
            "Applications": [
                {"id": "a1", "applied_at": "2025-01-20"},  # 11 days old (as of 2025-01-31)
                {"id": "a2", "applied_at": "invalid_timestamp"},
                {"id": "a3", "applied_at": "2025-01-26T14:30:00Z"},  # 5 days old
                {"id": "a4", "applied_at": None},
                {"id": "a5", "applied_at": "2025-01-11"},  # 20 days old
                {"id": "a6", "applied_at": ""},
                {"id": "a7", "applied_at": "2025-01-07"},  # 24 days old
            ]
        }
        res = AnalyticsEngine(snap, as_of="2025-01-31").analyze()

        mean_c = res.get_claim("mean_application_age_days")
        med_c = res.get_claim("median_application_age_days")
        max_c = res.get_claim("max_application_age_days")

        assert mean_c.value == 15.0
        assert med_c.value == 20
        assert max_c.value == 24


# ===========================================================================
# 3. Zero Touches and Edge Ratios in Source Effort Yield
# ===========================================================================

class TestSourceEffortYieldEdgeRatiosM3R3:
    """Stress-test zero touches, anomalous ratios, and zero denominator guards."""

    def test_zero_touches_and_zero_hires(self):
        """0 touches and 0 hires yields value 0.0 with numerator and denominator None."""
        snap = {
            "Applications": [
                {"id": "a1", "source": "Careers Page", "status": "applied"},
                {"id": "a2", "source": "Careers Page", "status": "screening"},
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        claim = res.get_claim("source_effort_yield:Careers Page")
        assert claim is not None
        assert claim.value == 0.0
        assert claim.numerator is None
        assert claim.denominator is None

    def test_positive_touches_and_zero_hires(self):
        """Positive touches and 0 hires sets numerator 0 and denominator touches."""
        snap = {
            "Applications": [
                {"id": "a1", "source": "Agency", "status": "interview"},
                {"id": "a2", "source": "Agency", "status": "interview"},
            ],
            "Interviews": [
                {"id": "i1", "application_id": "a1"},
                {"id": "i2", "application_id": "a2"},
            ]
        }
        res = AnalyticsEngine(snap).analyze()
        claim = res.get_claim("source_effort_yield:Agency")
        assert claim is not None
        assert claim.value == 0.0
        assert claim.numerator == 0
        assert claim.denominator == 2

    def test_anomalous_hires_greater_than_touches(self):
        """When hires > effort_touches, numerator and denominator must be None to prevent invalid ratio claims."""
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
        claim = res.get_claim("source_effort_yield:Direct")
        assert claim is not None
        assert claim.value == 2.0  # 2 hires / 1 touch
        assert claim.numerator is None
        assert claim.denominator is None

    def test_fixtures_all_source_effort_yield_claims_guarded(self, clean_snapshot, dirty_snapshot, sparse_snapshot):
        """Verify across all fixtures that any non-None denominator satisfies 0 <= numerator <= denominator."""
        for snap in (clean_snapshot, dirty_snapshot, sparse_snapshot):
            res = AnalyticsEngine(snap, as_of="2025-02-01").analyze()
            for claim in res.claims:
                if claim.metric.startswith("source_effort_yield:"):
                    if claim.denominator is not None:
                        assert claim.denominator > 0
                        assert claim.numerator is not None
                        assert 0 <= claim.numerator <= claim.denominator
                    else:
                        assert claim.numerator is None


# ===========================================================================
# 4. Multi-App Hire Isolation, Terminal Non-Hire Statuses & Invariant Parity
# ===========================================================================

class TestMultiAppHireIsolationAndInvariantParityM3R3:
    """Stress-test multi-application candidate hire isolation across complex topologies."""

    def test_ten_channel_candidate_topology_hire_isolation(self):
        """Candidate with 10 applications across 10 channels: only the hired channel gets a hire."""
        channels = [
            ("Referral", "hired"),
            ("LinkedIn", "offer"),
            ("Agency", "offer_made"),
            ("Direct", "offer_rejected"),
            ("Inbound", "offer_declined"),
            ("Careers", "declined_offer"),
            ("Campus", "screening"),
            ("Events", "interview"),
            ("JobBoard", "rejected"),
            ("TalentPool", "withdrawn"),
        ]
        apps = [
            {"id": f"app_{i}", "candidate_id": "cand_omega", "source": src, "status": st}
            for i, (src, st) in enumerate(channels)
        ]
        tables = {
            "Applications": apps,
            "Candidates": [{"id": "cand_omega", "status": "hired"}],
        }
        sources = source_effectiveness(tables)
        conv = funnel_stage_conversions(tables)

        assert sources["Referral"]["hires"] == 1
        for src, st in channels[1:]:
            assert sources[src]["hires"] == 0, f"Channel {src} with status {st} should have 0 hires"

        total_source_hires = sum(s["hires"] for s in sources.values())
        assert total_source_hires == 1
        assert conv["stages"]["hired"] == 1
        assert total_source_hires == conv["stages"]["hired"]

    def test_terminal_non_hire_statuses_explicit_isolation(self):
        """Explicitly test all terminal non-hire statuses in _is_hired."""
        terminal_statuses = [
            "rejected", "withdrawn", "closed", "declined", "archived",
            "offer_rejected", "offer_declined", "declined_offer",
        ]
        for st in terminal_statuses:
            app = {"id": "a1", "status": st, "hired": True}
            assert _is_hired(app) is False, f"Status {st} should be terminal non-hire"

    def test_multi_candidate_multi_app_invariant_parity_under_permutations(self):
        """Under 30 random row permutations, sum(source_hires) == funnel_hires holds identically."""
        tables = {
            "Applications": [
                {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired"},
                {"id": "a2", "candidate_id": "c1", "source": "LinkedIn", "status": "offer"},
                {"id": "a3", "candidate_id": "c2", "source": "Agency", "status": "hired"},
                {"id": "a4", "candidate_id": "c2", "source": "Referral", "status": "rejected"},
                {"id": "a5", "candidate_id": "c3", "source": "Careers", "status": "hired"},
                {"id": "a6", "candidate_id": "c3", "source": "Direct", "status": "declined_offer"},
                {"id": "a7", "candidate_id": "c4", "source": "Campus", "status": "screening"},
                {"id": "a8", "candidate_id": "c4", "source": "JobBoard", "status": "offer_rejected"},
            ],
            "Candidates": [
                {"id": "c1", "status": "hired"},
                {"id": "c2", "status": "hired"},
                {"id": "c3", "status": "hired"},
                {"id": "c4", "status": "active"},
            ],
        }

        rng = random.Random(12345)
        for trial in range(30):
            shuf_apps = list(tables["Applications"])
            shuf_cands = list(tables["Candidates"])
            rng.shuffle(shuf_apps)
            rng.shuffle(shuf_cands)
            perm_tables = {"Applications": shuf_apps, "Candidates": shuf_cands}

            srcs = source_effectiveness(perm_tables)
            fnl = funnel_stage_conversions(perm_tables)

            total_hires = sum(s["hires"] for s in srcs.values())
            assert total_hires == 3
            assert fnl["stages"]["hired"] == 3
            assert total_hires == fnl["stages"]["hired"]
