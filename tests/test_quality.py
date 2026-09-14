"""Comprehensive test suite for Milestone 4: Data Quality & Metric Sensitivity (Q5).

Covers:
- Feature 20: Foreign Key & Link Integrity across all 8 tables & multi-link arrays
- Feature 21: Orphaned Record Detection (direct, transitive, unreferenced)
- Feature 22: Timestamp Contradiction & Paradoxes (intra-record, cross-table, naive vs aware)
- Feature 23: Unmapped Enum Value Detection & Status Contradictions
- Feature 24: Metric Sensitivity Quantification across clean, dirty, and sparse fixtures
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from recruitment_intelligence.domain import (
    Confidence,
    EvidenceReference,
    Finding,
    MetricClaim,
    Severity,
)
from recruitment_intelligence.quality import (
    MetricSensitivityDelta,
    QualityAuditor,
    QualityAuditResult,
    ScenarioEvaluation,
    SensitivityReport,
    affected_metrics,
    assess_data_quality,
    build_exclusion_scenarios,
    check_quality,
    chronology_errors,
    data_quality_confidence,
    data_quality_report,
    duplicate_records,
    filter_tables_by_exclusions,
    find_quality_issues,
    invalid_dates,
    missing_values,
    orphan_links,
    quality_confidence,
    quantify_scenario,
    quantify_sensitivity,
    run_quality_audit,
    run_quality_checks,
    sensitivity_analysis,
    source_taxonomy_issues,
    status_inconsistencies,
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
# Baseline Pre-M4 Regression Tests (Must remain 100% passing)
# ==============================================================================

def test_required_values_and_duplicates_are_explicit():
    tables = {
        "Applications": [
            {"id": "a1", "candidate_id": "c-missing", "source": "Referral"},
            {"id": "a1", "candidate_id": "c2", "source": "Referral"},
        ]
    }
    missing = missing_values(tables)
    assert any(item["check"] == "missing_value" and item["field"] == "id" for item in missing) is False
    duplicates = duplicate_records(tables)
    assert duplicates[0]["affected_records"] == ["a1"]
    assert set(duplicates[0]) == {"check", "table", "field", "severity", "affected_records", "metric_impact", "confidence", "message"}


def test_orphan_invalid_date_and_chronology_checks():
    tables = {
        "Candidates": [{"id": "c1"}],
        "Applications": [{"id": "a1", "candidate_id": "c404", "applied_at": "not-a-date"}],
        "Offers": [{"id": "o1", "application_id": "a1", "offered_at": "2025-03-01", "responded_at": "2025-02-01"}],
    }
    assert orphan_links(tables)[0]["affected_records"] == ["a1"]
    assert invalid_dates(tables)[0]["field"] == "applied_at"
    assert chronology_errors(tables)[0]["check"] == "chronology_error"


def test_unknown_status_and_source_are_reported_without_coercion():
    tables = {
        "Applications": [{"id": "a1", "candidate_id": "c1", "status": "phone screen", "source": "Mystery Channel"}],
        "Candidates": [{"id": "c1"}],
    }
    statuses = status_inconsistencies(tables)
    assert "not mapped" in statuses[0]["message"]
    assert source_taxonomy_issues(tables)[0]["message"].startswith("Source 'Mystery Channel'")


def test_full_report_is_reproducible_and_empty_snapshot_is_insufficient():
    assert run_quality_checks({})["confidence"] == "insufficient"
    tables = {"Applications": [{"id": "a1", "candidate_id": "c1", "status": "applied"}], "Candidates": [{"id": "c1"}]}
    first, second = run_quality_checks(tables), run_quality_checks(tables)
    assert first == second
    assert first["summary"]["total_records"] == 2


# ==============================================================================
# Feature 20: Foreign Key & Link Integrity Audit Across All 8 Tables (Q5)
# ==============================================================================

def test_f20_fk_integrity_across_all_tables():
    """Verify that foreign keys across all 8 tables are validated against target table IDs."""
    tables = {
        "Departments": [{"id": "dep-1", "name": "Engineering"}],
        "People": [{"id": "per-1", "name": "Alice", "department_id": "dep-missing"}],
        "Job Openings": [{"id": "job-1", "department_id": "dep-1", "hiring_manager_id": "per-missing", "title": "Dev"}],
        "Candidates": [{"id": "cand-1", "person_id": "per-1"}],
        "Applications": [{"id": "app-1", "candidate_id": "cand-1", "job_id": "job-1"}],
        "Interviews": [{"id": "int-1", "application_id": "app-1", "interviewer_id": "per-missing-interviewer"}],
        "Offers": [{"id": "off-1", "application_id": "app-1", "candidate_id": "cand-missing"}],
    }
    auditor = QualityAuditor(tables)
    result = auditor.audit()

    # Verify that secondary foreign keys (People.department_id, Job.hiring_manager_id, Interview.interviewer_id, Offer.candidate_id) are caught
    observed_facts = " ".join(f.observed_fact for f in result.findings)
    assert "dep-missing" in observed_facts
    assert "per-missing" in observed_facts
    assert "per-missing-interviewer" in observed_facts
    assert "cand-missing" in observed_facts


def test_f20_fk_multi_link_arrays():
    """Verify that multi-link arrays containing multiple IDs validate each entry."""
    tables = {
        "People": [{"id": "p1"}, {"id": "p2"}],
        "Candidates": [
            {"id": "c1", "person_id": ["p1", "p-missing-404"]},
            {"id": "c2", "person_id": [{"id": "p2"}, {"id": "p-missing-500"}]},
        ],
        "Job Openings": [{"id": "j1", "title": "Lead"}],
        "Applications": [{"id": "a1", "candidate_id": "c1", "job_id": "j1"}],
    }
    result = run_quality_audit(tables)
    findings = result.findings_by_category("foreign_key_integrity")
    affected_ids = result.affected_record_ids
    assert "c1" in affected_ids
    assert "c2" in affected_ids
    combined_msg = " ".join(f.observed_fact for f in findings)
    assert "p-missing-404" in combined_msg
    assert "p-missing-500" in combined_msg


def test_f20_fk_clean_fixture_has_zero_link_violations(clean_snapshot):
    """Verify that clean_snapshot.json has 0 foreign key integrity violations."""
    result = run_quality_audit(clean_snapshot)
    fk_findings = result.findings_by_category("foreign_key_integrity")
    orphan_findings = result.findings_by_category("orphan_link")
    assert len(fk_findings) == 0
    assert len(orphan_findings) == 0


def test_f20_fk_finding_evidence_reference_attributes():
    """Verify that generated Finding objects have valid EvidenceReference with table and record IDs."""
    tables = {
        "Departments": [],
        "Job Openings": [{"id": "job-orphan", "title": "Eng", "department_id": "dep-404"}],
    }
    result = run_quality_audit(tables)
    assert len(result.findings) >= 1
    f = result.findings[0]
    assert isinstance(f, Finding)
    assert len(f.evidence) >= 1
    ev = f.evidence[0]
    assert isinstance(ev, EvidenceReference)
    assert ev.table == "Job Openings"
    assert "job-orphan" in ev.record_ids
    assert f.severity == Severity.HIGH
    assert f.confidence == Confidence.HIGH


# ==============================================================================
# Feature 21: Orphaned Record Detection (Direct & Transitive) (Q5)
# ==============================================================================

def test_f21_direct_orphan_links():
    """Verify that orphan_links reports non-empty foreign keys whose parent record is missing."""
    tables = {
        "Candidates": [{"id": "c1"}],
        "Applications": [{"id": "a1", "candidate_id": "c-ghost", "job_id": "j-ghost"}],
        "Job Openings": [],
    }
    issues = orphan_links(tables)
    assert len(issues) == 2
    assert any(iss["field"] == "candidate_id" and "c-ghost" in iss["message"] for iss in issues)
    assert any(iss["field"] == "job_id" and "j-ghost" in iss["message"] for iss in issues)


def test_f21_transitive_orphan_detection():
    """Verify that interviews and offers referencing orphaned applications are flagged as transitive orphans."""
    tables = {
        "Candidates": [{"id": "c1"}],
        "Job Openings": [{"id": "j1", "title": "Dev"}],
        # app-orphan links to nonexistent candidate
        "Applications": [
            {"id": "app-valid", "candidate_id": "c1", "job_id": "j1"},
            {"id": "app-orphan", "candidate_id": "cand-missing-404", "job_id": "j1"},
        ],
        # int-transitive links to app-orphan
        "Interviews": [
            {"id": "int-valid", "application_id": "app-valid"},
            {"id": "int-transitive", "application_id": "app-orphan"},
        ],
        # off-transitive links to app-orphan
        "Offers": [
            {"id": "off-valid", "application_id": "app-valid"},
            {"id": "off-transitive", "application_id": "app-orphan"},
        ],
    }
    result = run_quality_audit(tables)
    trans_findings = result.findings_by_category("transitive_orphan")
    assert len(trans_findings) == 2

    int_trans = [f for f in trans_findings if any(ev.table == "Interviews" for ev in f.evidence)][0]
    assert "int-transitive" in int_trans.affected_records
    assert "int-valid" not in int_trans.affected_records

    off_trans = [f for f in trans_findings if any(ev.table == "Offers" for ev in f.evidence)][0]
    assert "off-transitive" in off_trans.affected_records
    assert "off-valid" not in off_trans.affected_records


def test_f21_clean_and_sparse_have_zero_orphans(clean_snapshot, sparse_snapshot):
    """Verify that clean and sparse fixtures have 0 direct or transitive orphans."""
    r_clean = run_quality_audit(clean_snapshot)
    assert len(r_clean.findings_by_category("orphan_link")) == 0
    assert len(r_clean.findings_by_category("transitive_orphan")) == 0

    r_sparse = run_quality_audit(sparse_snapshot)
    assert len(r_sparse.findings_by_category("orphan_link")) == 0
    assert len(r_sparse.findings_by_category("transitive_orphan")) == 0


# ==============================================================================
# Feature 22: Timestamp Contradiction & Paradox Audit (Q5)
# ==============================================================================

def test_f22_intra_record_chronology_errors():
    """Verify intra-record chronology checks for Job Openings, Interviews, and Offers."""
    tables = {
        "Job Openings": [{"id": "j1", "opened_at": "2025-05-01", "closed_at": "2025-04-01"}],
        "Interviews": [{"id": "i1", "scheduled_at": "2025-05-10", "completed_at": "2025-05-01"}],
        "Offers": [{"id": "o1", "offered_at": "2025-05-20", "responded_at": "2025-05-15"}],
    }
    issues = chronology_errors(tables)
    assert len(issues) == 3
    assert all(iss["check"] == "chronology_error" for iss in issues)
    assert {iss["table"] for iss in issues} == {"Job Openings", "Interviews", "Offers"}


def test_f22_naive_aware_datetime_comparison_no_type_error():
    """Verify that comparing naive date with aware ISO datetime does not crash with TypeError."""
    # Test 1: Start is naive date, End is aware ISO datetime later (valid chronology)
    valid_tables = {
        "Job Openings": [{"id": "j1", "opened_at": "2025-01-01", "closed_at": "2025-01-02T12:00:00Z"}],
    }
    assert len(chronology_errors(valid_tables)) == 0

    # Test 2: Start is aware ISO datetime, End is naive date earlier (error)
    invalid_tables = {
        "Job Openings": [{"id": "j2", "opened_at": "2025-01-02T12:00:00Z", "closed_at": "2025-01-01"}],
    }
    issues = chronology_errors(invalid_tables)
    assert len(issues) == 1
    assert issues[0]["affected_records"] == ["j2"]


def test_f22_same_date_timestamps_are_not_chronology_errors():
    """Verify that an action occurring on the same day as its start is not flagged as an error."""
    tables = {
        "Interviews": [
            {"id": "i1", "scheduled_at": "2025-03-10T10:00:00Z", "completed_at": "2025-03-10"},
            {"id": "i2", "scheduled_at": "2025-03-10", "completed_at": "2025-03-10T17:00:00Z"},
            {"id": "i3", "scheduled_at": "2025-03-10", "completed_at": "2025-03-10"},
        ]
    }
    assert len(chronology_errors(tables)) == 0


def test_f22_cross_table_timestamp_applied_after_job_closed():
    """Verify cross-table paradox: Application submitted after linked Job requisition was closed."""
    tables = {
        "Job Openings": [{"id": "j1", "title": "Eng", "closed_at": "2025-02-01"}],
        "Candidates": [{"id": "c1"}],
        "Applications": [
            {"id": "app-late", "job_id": "j1", "candidate_id": "c1", "applied_at": "2025-02-15"},
            {"id": "app-ontime", "job_id": "j1", "candidate_id": "c1", "applied_at": "2025-01-15"},
        ],
    }
    result = run_quality_audit(tables)
    late_findings = [f for f in result.findings if f.finding_id == "qual-cross-chrono-applied-after-job-closed"]
    assert len(late_findings) == 1
    assert late_findings[0].affected_records == ("app-late",)


def test_f22_cross_table_timestamp_interview_before_application():
    """Verify cross-table paradox: Interview scheduled before application submission date."""
    tables = {
        "Candidates": [{"id": "c1"}],
        "Job Openings": [{"id": "j1", "title": "Eng"}],
        "Applications": [{"id": "app-1", "candidate_id": "c1", "job_id": "j1", "applied_at": "2025-03-15"}],
        "Interviews": [
            {"id": "int-early", "application_id": "app-1", "scheduled_at": "2025-03-10"},
            {"id": "int-normal", "application_id": "app-1", "scheduled_at": "2025-03-18"},
        ],
    }
    result = run_quality_audit(tables)
    early_findings = [f for f in result.findings if f.finding_id == "qual-cross-chrono-interview-before-application"]
    assert len(early_findings) == 1
    assert early_findings[0].affected_records == ("int-early",)


def test_f22_cross_table_timestamp_offer_before_application():
    """Verify cross-table paradox: Formal offer extended before candidate application date."""
    tables = {
        "Candidates": [{"id": "c1"}],
        "Job Openings": [{"id": "j1", "title": "Eng"}],
        "Applications": [{"id": "app-1", "candidate_id": "c1", "job_id": "j1", "applied_at": "2025-04-10"}],
        "Offers": [
            {"id": "off-early", "application_id": "app-1", "offered_at": "2025-04-01"},
            {"id": "off-normal", "application_id": "app-1", "offered_at": "2025-04-20"},
        ],
    }
    result = run_quality_audit(tables)
    early_findings = [f for f in result.findings if f.finding_id == "qual-cross-chrono-offer-before-application"]
    assert len(early_findings) == 1
    assert early_findings[0].affected_records == ("off-early",)


def test_f22_app_updated_before_applied():
    """Verify intra-record contradiction: application updated_at precedes applied_at."""
    tables = {
        "Applications": [{"id": "app-retro", "candidate_id": "c1", "applied_at": "2025-05-10", "updated_at": "2025-05-01"}],
    }
    result = run_quality_audit(tables)
    updated_findings = [f for f in result.findings if f.finding_id == "qual-chrono-app-updated-before-applied"]
    assert len(updated_findings) == 1
    assert updated_findings[0].affected_records == ("app-retro",)


# ==============================================================================
# Feature 23: Unmapped Enum Value Detection & Status Contradictions (Q5)
# ==============================================================================

def test_f23_unmapped_status_values_across_entities():
    """Verify status validation audits Applications, Candidates, Interviews, Offers, and Job Openings."""
    tables = {
        "Applications": [{"id": "a1", "status": "exploring_options"}],
        "Candidates": [{"id": "c1", "status": "drinking_coffee"}],
        "Interviews": [{"id": "i1", "status": "maybe_passed"}],
        "Offers": [{"id": "o1", "status": "half_signed"}],
        "Job Openings": [{"id": "j1", "status": "on_the_backburner"}],
    }
    issues = status_inconsistencies(tables)
    assert len(issues) == 5
    assert {iss["table"] for iss in issues} == {"Applications", "Candidates", "Interviews", "Offers", "Job Openings"}
    for iss in issues:
        assert "not mapped" in iss["message"]


def test_f23_contradictory_terminal_application_flag():
    """Verify that terminal application status paired with rejection boolean is flagged as high-severity corruption."""
    tables = {
        "Applications": [
            {"id": "app-hired-but-rejected", "candidate_id": "c1", "status": "hired", "rejected": True},
            {"id": "app-accepted-but-rejected", "candidate_id": "c2", "status": "accepted", "is_rejected": True},
            {"id": "app-valid-hired", "candidate_id": "c3", "status": "hired", "rejected": False},
        ],
        "Candidates": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}],
    }
    issues = status_inconsistencies(tables)
    contradictions = [iss for iss in issues if "contradictory" in iss["message"].lower()]
    assert len(contradictions) == 1
    assert set(contradictions[0]["affected_records"]) == {"app-accepted-but-rejected", "app-hired-but-rejected"}
    assert contradictions[0]["severity"] == "high"


def test_f23_contradictory_offer_acceptance_and_rejection_flags():
    """Verify that an offer marked as accepted and declined/rejected is caught by QualityAuditor."""
    tables = {
        "Offers": [
            {"id": "off-contradiction-1", "application_id": "a1", "is_accepted": True, "status": "rejected"},
            {"id": "off-contradiction-2", "application_id": "a2", "is_accepted": True, "declined": True},
            {"id": "off-valid-accepted", "application_id": "a3", "is_accepted": True, "declined": False, "status": "accepted"},
        ]
    }
    result = run_quality_audit(tables)
    offer_contra = [f for f in result.findings if f.finding_id == "qual-offer-contradiction-accepted-vs-declined"]
    assert len(offer_contra) == 1
    assert set(offer_contra[0].affected_records) == {"off-contradiction-1", "off-contradiction-2"}
    assert offer_contra[0].severity == Severity.HIGH


def test_f23_unmapped_findings_table_enums():
    """Verify that Findings table severity and confidence must map to canonical domain enums."""
    tables = {
        "Findings": [
            {"id": "f1", "severity": "super_urgent", "confidence": "high"},
            {"id": "f2", "severity": "low", "confidence": "guesswork"},
            {"id": "f3", "severity": "high", "confidence": "medium"},
        ]
    }
    result = run_quality_audit(tables)
    sev_findings = [f for f in result.findings if f.finding_id == "qual-enum-findings-severity"]
    conf_findings = [f for f in result.findings if f.finding_id == "qual-enum-findings-confidence"]
    assert len(sev_findings) == 1
    assert sev_findings[0].affected_records == ("f1",)
    assert len(conf_findings) == 1
    assert conf_findings[0].affected_records == ("f2",)


def test_f23_source_taxonomy_issues():
    """Verify that non-canonical recruitment source channels are reported without silent coercion."""
    tables = {
        "Applications": [
            {"id": "a1", "candidate_id": "c1", "source": "Highway Billboard"},
            {"id": "a2", "candidate_id": "c2", "source": "LinkedIn"},
            {"id": "a3", "candidate_id": "c3", "source": "referral"},
        ]
    }
    issues = source_taxonomy_issues(tables)
    assert len(issues) == 1
    assert issues[0]["affected_records"] == ["a1"]
    assert "Highway Billboard" in issues[0]["message"]


# ==============================================================================
# Feature 24: Metric Sensitivity Quantification (Q5) Across Fixtures
# ==============================================================================

def test_f24_dirty_snapshot_preserves_22_issue_invariant(dirty_snapshot):
    """STRICT INVARIANT: run_quality_checks on dirty_snapshot.json MUST yield exactly 22 issues."""
    report = run_quality_checks(dirty_snapshot)
    assert len(report["issues"]) == 22, f"Expected 22 issues on dirty_snapshot, got {len(report['issues'])}"
    assert report["confidence"] == "low"
    assert report["summary"]["issue_count"] == 22

    # QualityAuditor on dirty snapshot also yields exactly 22 findings
    audit_res = run_quality_audit(dirty_snapshot)
    assert len(audit_res.findings) == 22
    assert audit_res.confidence == Confidence.LOW


def test_f24_clean_snapshot_zero_anomalies(clean_snapshot):
    """Verify that clean_snapshot.json produces 0 issues, 0 findings, and high confidence."""
    checks_report = run_quality_checks(clean_snapshot)
    assert len(checks_report["issues"]) == 0
    assert checks_report["confidence"] == "high"

    audit_res = run_quality_audit(clean_snapshot)
    assert len(audit_res.findings) == 0
    assert audit_res.confidence == Confidence.HIGH
    assert audit_res.clean is True

    # Sensitivity on clean snapshot should yield 0 high sensitivity scenarios
    sens_report = quantify_sensitivity(clean_snapshot)
    assert len(sens_report.high_sensitivity_scenarios) == 0
    assert len(sens_report.findings) == 0


def test_f24_sparse_snapshot_zero_anomalies_insufficient_confidence(sparse_snapshot):
    """Verify that sparse_snapshot.json handles empty data cleanly without ZeroDivisionError."""
    checks_report = run_quality_checks(sparse_snapshot)
    assert len(checks_report["issues"]) == 0
    assert checks_report["confidence"] == "insufficient"

    audit_res = run_quality_audit(sparse_snapshot)
    assert len(audit_res.findings) == 0
    assert audit_res.confidence == Confidence.INSUFFICIENT

    sens_report = quantify_sensitivity(sparse_snapshot)
    assert len(sens_report.high_sensitivity_scenarios) == 0


def test_f24_dirty_snapshot_baseline_metrics(dirty_snapshot):
    """Verify baseline metric states on dirty_snapshot.json before counterfactual exclusions."""
    report = quantify_sensitivity(dirty_snapshot)
    assert report.baseline_top_source == "Job board"
    assert report.baseline_offer_acceptance_rate == pytest.approx(0.40, abs=0.01)
    assert report.baseline_bottleneck == "screening_to_interview"


def test_f24_source_ranking_inversion_under_status_contradictions(dirty_snapshot):
    """Verify that excluding status contradictions inverts top recruiting source from Job board to Referral."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_status_contradictions"]

    assert sc.rank_inversion is True
    assert sc.top_source_baseline == "Job board"
    assert sc.top_source_counterfactual == "Referral"
    # Job board drops from 25% (1/4) to 0% (0/3), becoming a new effort sink
    assert sc.source_conversion_deltas["Job board"] == pytest.approx(-0.25, abs=0.01)
    assert "Job board" in sc.new_effort_sinks

    # Finding should be generated
    rank_findings = [f for f in sc.findings if f.finding_id == "sens-rank-exclude_status_contradictions"]
    assert len(rank_findings) == 1
    assert rank_findings[0].severity == Severity.HIGH
    assert rank_findings[0].confidence == Confidence.HIGH
    assert "app-dirty-contradiction" in rank_findings[0].affected_records


def test_f24_source_ranking_inversion_under_duplicates(dirty_snapshot):
    """Verify that excluding duplicates inverts top source to Referral due to denominator deduplication."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_duplicates"]

    assert sc.rank_inversion is True
    assert sc.top_source_counterfactual == "Referral"
    # Referral conversion surges from 20% (1/5) to 33.3% (1/3)
    assert sc.source_conversion_deltas["Referral"] == pytest.approx(0.1333, abs=0.01)
    # Bottleneck shifts from screening_to_interview to applied_to_screening
    assert sc.bottleneck_shifted is True
    assert sc.bottleneck_counterfactual == "applied_to_screening"


def test_f24_offer_acceptance_drop_under_chronology_errors(dirty_snapshot):
    """Verify that excluding chronology errors drops offer acceptance rate from 40% to 25%."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_chronology_errors"]

    assert sc.offer_acceptance_baseline == pytest.approx(0.40, abs=0.01)
    assert sc.offer_acceptance_counterfactual == pytest.approx(0.25, abs=0.01)
    assert sc.offer_acceptance_delta == pytest.approx(-0.15, abs=0.01)

    oar_findings = [f for f in sc.findings if f.finding_id == "sens-offer-exclude_chronology_errors"]
    assert len(oar_findings) == 1
    assert oar_findings[0].severity == Severity.HIGH


def test_f24_offer_acceptance_increase_under_orphans(dirty_snapshot):
    """Verify that excluding orphan links increases offer acceptance rate from 40% to 50%."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_orphans"]

    assert sc.offer_acceptance_baseline == pytest.approx(0.40, abs=0.01)
    assert sc.offer_acceptance_counterfactual == pytest.approx(0.50, abs=0.01)
    assert sc.offer_acceptance_delta == pytest.approx(0.10, abs=0.01)


def test_f24_full_clean_pass_sensitivity(dirty_snapshot):
    """Verify full clean pass (excluding all 22 anomalies) on dirty_snapshot.json."""
    report = quantify_sensitivity(dirty_snapshot)
    sc = report.scenarios["exclude_all_anomalies"]

    assert sc.excluded_record_count >= 18
    # Offer acceptance surges to 100% (1/1)
    assert sc.offer_acceptance_counterfactual == pytest.approx(1.00, abs=0.01)
    assert sc.offer_acceptance_delta == pytest.approx(0.60, abs=0.01)
    # Funnel bottleneck migrates to accepted_to_hired
    assert sc.bottleneck_shifted is True
    assert sc.bottleneck_counterfactual == "accepted_to_hired"


def test_f24_typed_metric_claims_and_finding_contracts(dirty_snapshot):
    """Verify typed MetricClaim and Finding structures returned in SensitivityReport."""
    report = quantify_sensitivity(dirty_snapshot)

    assert len(report.claims) > 0
    for claim in report.claims:
        assert isinstance(claim, MetricClaim)
        assert claim.name.startswith("sensitivity_")
        assert claim.confidence in (Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW, Confidence.INSUFFICIENT)
        assert len(claim.evidence) >= 1
        assert isinstance(claim.evidence[0], EvidenceReference)

    assert len(report.findings) > 0
    for finding in report.findings:
        assert isinstance(finding, Finding)
        assert finding.category == "metric_sensitivity"
        assert finding.severity in (Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
        assert finding.confidence in (Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW, Confidence.INSUFFICIENT)
        assert len(finding.affected_records) > 0
        assert len(finding.recommendations) > 0


def test_f24_backward_compatible_sensitivity_analysis_dict(dirty_snapshot):
    """Verify backward-compatible sensitivity_analysis returning standard nested dict."""
    res = sensitivity_analysis(dirty_snapshot, exclusions={"custom_test": ["app-dirty-contradiction"]})
    assert "baseline" in res
    assert "scenarios" in res
    assert "custom_test" in res["scenarios"]
    assert "Job board" in res["scenarios"]["custom_test"]


def test_f24_quality_audit_result_helpers(dirty_snapshot):
    """Verify helper query methods on QualityAuditResult."""
    result = run_quality_audit(dirty_snapshot)

    # get_finding
    first_f = result.findings[0]
    found = result.get_finding(first_f.finding_id)
    assert found is not None
    assert found.finding_id == first_f.finding_id
    assert result.get_finding("nonexistent-id") is None

    # findings_by_category
    dups = result.findings_by_category("duplicate_record")
    assert len(dups) == 1
    assert dups[0].category == "duplicate_record"

    # findings_by_severity
    high_sev = result.findings_by_severity(Severity.HIGH)
    assert len(high_sev) > 0

    # findings_by_table
    app_findings = result.findings_by_table("Applications")
    assert len(app_findings) > 0

    # serialization
    data_dict = result.to_dict()
    assert "findings" in data_dict
    assert "confidence" in data_dict
    assert "summary" in data_dict


def test_f24_affected_metrics_aggregation(dirty_snapshot):
    """Verify affected_metrics properly aggregates impacted metrics by check type."""
    report = run_quality_checks(dirty_snapshot)
    aggregated = affected_metrics(report["issues"])
    assert "orphan_link" in aggregated
    assert "hire_conversion_rate" in aggregated["orphan_link"]
    assert "chronology_error" in aggregated
    assert "aging" in aggregated["chronology_error"]
