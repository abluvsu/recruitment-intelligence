"""Empirical Challenger Test Suite for Milestone 4 (challenger_m4_2_gen5).

Rigorously verifies:
1. Counterfactual sensitivity mathematics on fixtures/dirty_snapshot.json:
   - Status contradictions: Job board inverts to 0%, Referral takes #1, new effort sink.
   - Duplicates: Referral conversion surges from 20% to 33.3%, bottleneck shifts to applied_to_screening.
   - Chronology errors: Offer acceptance rate drops from 40% to 25% (delta = -0.15).
   - Orphan links: Offer acceptance rate increases from 40% to 50% (delta = +0.10).
   - All anomalies: Offer acceptance rate surges to 100% (delta = +0.60), bottleneck migrates to accepted_to_hired.
2. Permutation invariance under row shuffling and reversed order across multiple seeds.
3. Zero-denominator robustness on empty and sparse data (no ZeroDivisionError, KeyError, or TypeError).
4. Domain contract fidelity and serialization for MetricSensitivityDelta, ScenarioEvaluation, and SensitivityReport.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
from typing import Any

import pytest

from recruitment_intelligence.domain import (
    Confidence,
    EvidenceReference,
    Finding,
    MetricClaim,
    Severity,
)
from recruitment_intelligence.quality.auditor import CANONICAL_TABLES, QualityAuditor, run_quality_audit
from recruitment_intelligence.quality.sensitivity import (
    MetricSensitivityDelta,
    ScenarioEvaluation,
    SensitivityReport,
    build_exclusion_scenarios,
    filter_tables_by_exclusions,
    quantify_scenario,
    quantify_sensitivity,
    sensitivity_analysis,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def clean_snapshot() -> dict[str, list[dict[str, Any]]]:
    with open(FIXTURES_DIR / "clean_snapshot.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def dirty_snapshot() -> dict[str, list[dict[str, Any]]]:
    with open(FIXTURES_DIR / "dirty_snapshot.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sparse_snapshot() -> dict[str, list[dict[str, Any]]]:
    with open(FIXTURES_DIR / "sparse_snapshot.json", encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# Objective 1: Counterfactual Sensitivity Calculations on Dirty Snapshot
# ==============================================================================

def test_dirty_snapshot_baseline_metrics(dirty_snapshot):
    """Verify exact baseline metric values on dirty_snapshot before any exclusions."""
    report = quantify_sensitivity(dirty_snapshot)
    assert report.baseline_top_source == "Job board"
    assert report.baseline_offer_acceptance_rate == pytest.approx(0.40, abs=1e-4)
    assert report.baseline_bottleneck == "screening_to_interview"


def test_scenario_status_contradictions_inversion_and_effort_sink(dirty_snapshot):
    """Empirical verification: exclude_status_contradictions inverts Job board to 0% and promotes Referral to #1."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_status_contradictions"]

    # Inversion verification
    assert sc.rank_inversion is True
    assert sc.top_source_baseline == "Job board"
    assert sc.top_source_counterfactual == "Referral"

    # Job board drops from 25.0% (1/4) to 0.0% (0/3) -> delta: -0.25
    assert sc.source_conversion_deltas["Job board"] == pytest.approx(-0.25, abs=1e-4)
    # Referral remains at 20.0% (1/5) -> delta: 0.0
    assert sc.source_conversion_deltas["Referral"] == pytest.approx(0.0, abs=1e-4)
    # Job board becomes a newly identified effort sink (volume with 0 hires)
    assert "Job board" in sc.new_effort_sinks

    # Finding verification
    rank_findings = [f for f in sc.findings if f.finding_id == "sens-rank-exclude_status_contradictions"]
    assert len(rank_findings) == 1
    rf = rank_findings[0]
    assert rf.severity == Severity.HIGH
    assert rf.confidence == Confidence.HIGH
    assert "app-dirty-contradiction" in rf.affected_records
    assert "Job board" in rf.observed_fact
    assert "Referral" in rf.observed_fact


def test_scenario_duplicates_referral_surge_and_bottleneck_shift(dirty_snapshot):
    """Empirical verification: exclude_duplicates surges Referral conversion from 20% to 33.3% and shifts bottleneck."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_duplicates"]

    # Referral denominator drops from 5 to 3: 1/3 = 33.33% (delta: +13.33%)
    assert sc.source_conversion_deltas["Referral"] == pytest.approx(0.1333, abs=1e-3)
    # Rank inversion occurs because Referral (33.3%) overtakes Job board (25.0%)
    assert sc.rank_inversion is True
    assert sc.top_source_counterfactual == "Referral"

    # Funnel bottleneck migration: screening_to_interview -> applied_to_screening
    assert sc.bottleneck_shifted is True
    assert sc.bottleneck_baseline == "screening_to_interview"
    assert sc.bottleneck_counterfactual == "applied_to_screening"

    # Finding verification
    bn_findings = [f for f in sc.findings if f.finding_id == "sens-funnel-exclude_duplicates"]
    assert len(bn_findings) == 1
    assert bn_findings[0].severity == Severity.HIGH
    assert "applied_to_screening" in bn_findings[0].observed_fact


def test_scenario_chronology_errors_oar_drop(dirty_snapshot):
    """Empirical verification: exclude_chronology_errors drops OAR from 40% to 25% (delta: -0.15)."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_chronology_errors"]

    # Excluding off-dirty-chrono leaves 1 accepted offer out of 4 formal offers (25%)
    assert sc.offer_acceptance_baseline == pytest.approx(0.40, abs=1e-4)
    assert sc.offer_acceptance_counterfactual == pytest.approx(0.25, abs=1e-4)
    assert sc.offer_acceptance_delta == pytest.approx(-0.15, abs=1e-4)

    # High severity finding generated due to |delta| >= 0.15
    oar_findings = [f for f in sc.findings if f.finding_id == "sens-offer-exclude_chronology_errors"]
    assert len(oar_findings) == 1
    assert oar_findings[0].severity == Severity.HIGH
    assert oar_findings[0].confidence == Confidence.HIGH
    assert "off-dirty-chrono" in oar_findings[0].affected_records


def test_scenario_orphans_oar_increase(dirty_snapshot):
    """Empirical verification: exclude_orphans increases OAR from 40% to 50% (delta: +0.10)."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_orphans"]

    # Excluding off-dirty-orphan-app leaves 2 accepted offers out of 4 formal offers (50%)
    assert sc.offer_acceptance_baseline == pytest.approx(0.40, abs=1e-4)
    assert sc.offer_acceptance_counterfactual == pytest.approx(0.50, abs=1e-4)
    assert sc.offer_acceptance_delta == pytest.approx(0.10, abs=1e-4)

    # Medium severity finding generated due to 0.05 <= |delta| < 0.15
    oar_findings = [f for f in sc.findings if f.finding_id == "sens-offer-exclude_orphans"]
    assert len(oar_findings) == 1
    assert oar_findings[0].severity == Severity.MEDIUM
    assert "off-dirty-orphan-app" in oar_findings[0].affected_records


def test_scenario_exclude_all_anomalies_100_percent_oar(dirty_snapshot):
    """Empirical verification: exclude_all_anomalies produces 100% OAR and shifts bottleneck to accepted_to_hired."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_all_anomalies"]

    # Purging all corrupted offers leaves off-valid-1 (1 accepted / 1 formal = 100%)
    assert sc.offer_acceptance_counterfactual == pytest.approx(1.00, abs=1e-4)
    assert sc.offer_acceptance_delta == pytest.approx(0.60, abs=1e-4)

    # Bottleneck migration to accepted_to_hired
    assert sc.bottleneck_shifted is True
    assert sc.bottleneck_counterfactual == "accepted_to_hired"

    # Both offer and funnel findings generated with Severity.HIGH
    find_ids = {f.finding_id for f in sc.findings}
    assert "sens-offer-exclude_all_anomalies" in find_ids
    assert "sens-funnel-exclude_all_anomalies" in find_ids


# ==============================================================================
# Objective 2: Permutation Invariance Under Table Row Permutations
# ==============================================================================

def test_permutation_invariance_shuffled_tables_dirty_snapshot(dirty_snapshot):
    """Empirical verification: Shuffling rows in dirty_snapshot produces identical deltas and rankings."""
    baseline_report = quantify_sensitivity(dirty_snapshot)

    seeds = [42, 1337, 2026, 88888, 99999]
    for seed in seeds:
        shuffled_tables: dict[str, list[dict[str, Any]]] = {}
        rng = random.Random(seed)
        for tbl_name, rows in dirty_snapshot.items():
            shuffled_rows = copy.deepcopy(rows)
            rng.shuffle(shuffled_rows)
            shuffled_tables[tbl_name] = shuffled_rows

        permuted_report = quantify_sensitivity(shuffled_tables)

        # Baseline invariance
        assert permuted_report.baseline_top_source == baseline_report.baseline_top_source
        assert permuted_report.baseline_offer_acceptance_rate == baseline_report.baseline_offer_acceptance_rate
        assert permuted_report.baseline_bottleneck == baseline_report.baseline_bottleneck
        assert permuted_report.high_sensitivity_scenarios == baseline_report.high_sensitivity_scenarios

        # Scenario invariance
        assert set(permuted_report.scenarios.keys()) == set(baseline_report.scenarios.keys())
        for sc_name, base_sc in baseline_report.scenarios.items():
            perm_sc = permuted_report.scenarios[sc_name]

            assert perm_sc.rank_inversion == base_sc.rank_inversion
            assert perm_sc.top_source_counterfactual == base_sc.top_source_counterfactual
            assert perm_sc.offer_acceptance_counterfactual == base_sc.offer_acceptance_counterfactual
            assert perm_sc.offer_acceptance_delta == base_sc.offer_acceptance_delta
            assert perm_sc.bottleneck_shifted == base_sc.bottleneck_shifted
            assert perm_sc.bottleneck_counterfactual == base_sc.bottleneck_counterfactual
            assert perm_sc.source_conversion_deltas == base_sc.source_conversion_deltas
            assert perm_sc.new_effort_sinks == base_sc.new_effort_sinks
            assert perm_sc.resolved_effort_sinks == base_sc.resolved_effort_sinks
            assert perm_sc.excluded_record_ids == base_sc.excluded_record_ids


def test_permutation_invariance_reversed_rows(dirty_snapshot):
    """Empirical verification: Reversing row order produces identical sensitivity report."""
    baseline_report = quantify_sensitivity(dirty_snapshot)
    reversed_tables = {t: list(reversed(copy.deepcopy(rows))) for t, rows in dirty_snapshot.items()}

    rev_report = quantify_sensitivity(reversed_tables)
    assert rev_report.baseline_top_source == baseline_report.baseline_top_source
    assert rev_report.baseline_offer_acceptance_rate == baseline_report.baseline_offer_acceptance_rate
    assert rev_report.baseline_bottleneck == baseline_report.baseline_bottleneck

    for sc_name, base_sc in baseline_report.scenarios.items():
        rev_sc = rev_report.scenarios[sc_name]
        assert rev_sc.rank_inversion == base_sc.rank_inversion
        assert rev_sc.offer_acceptance_delta == base_sc.offer_acceptance_delta
        assert rev_sc.bottleneck_shifted == base_sc.bottleneck_shifted
        assert rev_sc.excluded_record_ids == base_sc.excluded_record_ids


# ==============================================================================
# Objective 3: Zero-Denominator and Sparse / Empty Snapshot Robustness
# ==============================================================================

def test_sparse_snapshot_zero_division_robustness(sparse_snapshot):
    """Empirical verification: sparse_snapshot does not trigger ZeroDivisionError, KeyError, or TypeError."""
    report = quantify_sensitivity(sparse_snapshot)

    assert report.baseline_top_source == "Unknown — insufficient evidence"
    assert report.baseline_offer_acceptance_rate is None
    assert report.baseline_bottleneck == "Unknown — insufficient evidence"
    assert len(report.high_sensitivity_scenarios) == 0
    assert len(report.findings) == 0


def test_empty_snapshot_zero_division_robustness():
    """Empirical verification: Completely empty dictionary {} executes cleanly without crash."""
    report = quantify_sensitivity({})

    assert report.baseline_top_source == "Unknown — insufficient evidence"
    assert report.baseline_offer_acceptance_rate is None
    assert report.baseline_bottleneck == "Unknown — insufficient evidence"
    assert len(report.scenarios) == 0
    assert len(report.claims) == 0
    assert len(report.findings) == 0


def test_canonical_empty_tables_robustness():
    """Empirical verification: Canonical tables dictionary with 0 rows executes cleanly."""
    empty_tables = {t: [] for t in CANONICAL_TABLES}
    report = quantify_sensitivity(empty_tables)

    assert report.baseline_top_source == "Unknown — insufficient evidence"
    assert report.baseline_offer_acceptance_rate is None
    assert report.baseline_bottleneck == "Unknown — insufficient evidence"
    assert len(report.scenarios) == 0


def test_zero_offers_extended_scenario():
    """Empirical verification: Applications exist with zero Offers extended."""
    tables = {
        "Applications": [
            {"id": "app-1", "source": "Referral", "status": "applied"},
            {"id": "app-2", "source": "Job board", "status": "interviewing"},
        ],
        "Offers": [],
    }
    report = quantify_sensitivity(tables, exclusions={"test_excl": ["app-1"]})
    sc = report.scenarios["test_excl"]

    assert sc.offer_acceptance_baseline is None
    assert sc.offer_acceptance_counterfactual is None
    assert sc.offer_acceptance_delta is None
    assert sc.rank_inversion is False


def test_zero_applications_extended_scenario():
    """Empirical verification: Offers exist with zero Applications."""
    tables = {
        "Applications": [],
        "Offers": [
            {"id": "off-1", "status": "accepted", "is_accepted": True},
        ],
    }
    report = quantify_sensitivity(tables, exclusions={"test_excl": ["off-1"]})
    sc = report.scenarios["test_excl"]

    assert sc.top_source_baseline == "Unknown — insufficient evidence"
    assert sc.top_source_counterfactual == "Unknown — insufficient evidence"
    assert sc.offer_acceptance_baseline == pytest.approx(1.0, abs=1e-4)
    assert sc.offer_acceptance_counterfactual is None
    assert sc.offer_acceptance_delta is None


def test_total_exclusion_leaves_empty_tables(dirty_snapshot):
    """Empirical verification: Excluding every record ID in the snapshot degrades gracefully."""
    all_ids = [
        str(r.get("id") or r.get("record_id"))
        for rows in dirty_snapshot.values()
        for r in rows
        if r.get("id") or r.get("record_id")
    ]
    report = quantify_sensitivity(dirty_snapshot, exclusions={"total_purge": all_ids})
    sc = report.scenarios["total_purge"]

    assert sc.top_source_counterfactual == "Unknown — insufficient evidence"
    assert sc.offer_acceptance_counterfactual is None
    assert sc.bottleneck_counterfactual == "Unknown — insufficient evidence"


# ==============================================================================
# Objective 4: Edge Cases, Custom Exclusions, and Contract Serialization
# ==============================================================================

def test_ghost_and_whitespace_exclusions_tolerance(dirty_snapshot):
    """Empirical verification: Exclusions containing nonexistent IDs, whitespace, and empty strings do not crash."""
    ghost_ids = ["nonexistent-uuid-9999", "   ", "", "another-ghost-id", "  \t\n  "]
    report = quantify_sensitivity(dirty_snapshot, exclusions={"ghost_scenario": ghost_ids})
    sc = report.scenarios["ghost_scenario"]

    # Whitespace and empty strings filtered out; only valid non-empty strings kept
    assert set(sc.excluded_record_ids) == {"nonexistent-uuid-9999", "another-ghost-id"}
    assert sc.rank_inversion is False
    assert sc.offer_acceptance_delta == pytest.approx(0.0, abs=1e-4)


def test_empty_exclusion_list_produces_zero_delta(dirty_snapshot):
    """Empirical verification: An empty exclusion list evaluates to zero delta without error."""
    report = quantify_sensitivity(dirty_snapshot, exclusions={"noop": []})
    sc = report.scenarios["noop"]

    assert sc.excluded_record_count == 0
    assert sc.excluded_record_ids == ()
    assert sc.rank_inversion is False
    assert sc.offer_acceptance_delta == pytest.approx(0.0, abs=1e-4)
    assert sc.bottleneck_shifted is False


def test_corrupted_row_structures_tolerance():
    """Empirical verification: Rows missing id, record_id, or containing None values are handled gracefully."""
    corrupt_tables = {
        "Applications": [
            {},
            {"id": None, "source": None, "status": None},
            {"record_id": "", "source": "Referral", "status": "hired"},
        ],
        "Offers": [
            {},
            {"status": "accepted", "offered_at": "not-a-valid-date"},
        ],
    }
    report = quantify_sensitivity(corrupt_tables, exclusions={"test_corrupt": ["unknown-id"]})
    assert "test_corrupt" in report.scenarios


def test_sensitivity_report_serialization_and_domain_fidelity(dirty_snapshot):
    """Empirical verification: SensitivityReport serializes cleanly to dict and JSON round-trip."""
    report = quantify_sensitivity(dirty_snapshot)

    # Verify dict conversion
    data_dict = report.to_dict()
    assert isinstance(data_dict, dict)
    assert "baseline_top_source" in data_dict
    assert "baseline_offer_acceptance_rate" in data_dict
    assert "scenarios" in data_dict
    assert "claims" in data_dict
    assert "findings" in data_dict

    # Verify JSON conversion and round-trip
    json_str = report.to_json()
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed["baseline_top_source"] == report.baseline_top_source
    assert len(parsed["scenarios"]) == len(report.scenarios)

    # Verify all claims conform to MetricClaim specification
    for claim in report.claims:
        assert isinstance(claim, MetricClaim)
        assert claim.confidence == Confidence.HIGH
        assert len(claim.evidence) >= 1
        assert isinstance(claim.evidence[0], EvidenceReference)

    # Verify all findings conform to Finding specification
    for finding in report.findings:
        assert isinstance(finding, Finding)
        assert finding.category == "metric_sensitivity"
        assert finding.severity in (Severity.MEDIUM, Severity.HIGH)
        assert finding.confidence == Confidence.HIGH
        assert len(finding.affected_records) > 0
        assert len(finding.recommendations) > 0
        assert len(finding.evidence) >= 1


def test_backward_compatible_sensitivity_analysis_functional(dirty_snapshot):
    """Empirical verification: Backward-compatible functional sensitivity_analysis adapter works seamlessly."""
    res = sensitivity_analysis(dirty_snapshot, exclusions={"test_excl": ["app-dirty-contradiction"]})
    assert "baseline" in res
    assert "scenarios" in res
    assert "test_excl" in res["scenarios"]
    assert "Job board" in res["scenarios"]["test_excl"]
    assert res["scenarios"]["test_excl"]["Job board"]["hire_conversion_rate"] == 0.0
