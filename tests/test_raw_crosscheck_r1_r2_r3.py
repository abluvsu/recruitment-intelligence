"""Milestone 6 Forensic Crosscheck and Strategic Insights Test Suite.

Verifies:
- R1: Deterministic crosscheck of Q1–Q5 core questions on the raw Airtable snapshot.
- R2: Deep strategic insights (recruiter bandwidth, interviewer load/burnout, time-to-hire velocity, departmental fill rates).
- R3: Output artifact verification across multi-format synthesis (Markdown, CSV, HTML, JSON) with strict advisory vocabulary and mandatory human review.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from recruitment_intelligence.airtable.ingest import profile_all_tables
from recruitment_intelligence.analytics import (
    funnel_stage_conversions,
    offer_acceptance_rate,
    run_analytics,
    source_effectiveness,
)
from recruitment_intelligence.analytics.metrics import (
    compensation_competitiveness,
    departmental_headcount_fill_rate,
    recruiter_interviewer_bandwidth,
    time_to_hire_by_source,
)
from recruitment_intelligence.domain import Confidence, RecommendationAction, Severity
from recruitment_intelligence.pipeline import load_snapshot, run_pipeline

RAW_PATH = Path(__file__).resolve().parent.parent / "data" / "raw" / "airtable_snapshot.json"
AS_OF = date(2026, 9, 2)


@pytest.fixture(scope="module")
def raw_data():
    """Load the raw Airtable snapshot once for the test module."""
    return load_snapshot(RAW_PATH)


# ==============================================================================
# R1: Deterministic Verification & Crosscheck of Core Questions (Q1–Q5)
# ==============================================================================

class TestR1ForensicCrosscheck:
    """Rigorous verification of Q1–Q5 against raw Airtable dataset."""

    def test_q1_exact_table_counts(self, raw_data):
        """Verify exact record counts across all 8 canonical tables totaling 892 records."""
        assert len(raw_data["Applications"]) == 350
        assert len(raw_data["Candidates"]) == 300
        assert len(raw_data["Interviews"]) == 160
        assert len(raw_data["Offers"]) == 36
        assert len(raw_data["Job Openings"]) == 24
        assert len(raw_data["People"]) == 14
        assert len(raw_data["Departments"]) == 8
        assert len(raw_data["Findings"]) == 0
        assert sum(len(v) for v in raw_data.values()) == 892

    def test_q1_schema_profiling(self, raw_data):
        """Profile schema structures, foreign key linkages, and field cardinality."""
        profiles = profile_all_tables(raw_data)
        assert len(profiles) == 8
        assert profiles["Applications"].record_count == 350
        assert profiles["Candidates"].record_count == 300
        assert profiles["Interviews"].record_count == 160
        assert profiles["Offers"].record_count == 36
        assert profiles["Job Openings"].record_count == 24
        assert profiles["People"].record_count == 14
        assert profiles["Departments"].record_count == 8
        assert profiles["Findings"].record_count == 0

    def test_q2_source_effectiveness_and_ranking(self, raw_data):
        """Prove Referral is #1 (41.2% conv) and Job Board/LinkedIn have low yields (4.2%, 2.6%)."""
        sources = source_effectiveness(raw_data)
        # Referral
        assert sources["Referral"]["hires"] == 7
        assert sources["Referral"]["applications"] == 17
        assert sources["Referral"]["hire_conversion_rate"] == pytest.approx(0.4118, abs=0.005)
        # Job Board
        assert sources["Job Board"]["hires"] == 10
        assert sources["Job Board"]["applications"] == 240
        assert sources["Job Board"]["hire_conversion_rate"] == pytest.approx(0.0417, abs=0.005)
        # LinkedIn
        assert sources["LinkedIn"]["hires"] == 1
        assert sources["LinkedIn"]["applications"] == 38
        assert sources["LinkedIn"]["hire_conversion_rate"] == pytest.approx(0.0263, abs=0.005)

    def test_q2_effort_ratios_and_bandwidth_sinks(self, raw_data):
        """Verify interview effort per hire and show Job Board + LinkedIn absorb 71.9% of interview bandwidth."""
        sources = source_effectiveness(raw_data)
        assert sources["Referral"]["effort_per_hire"] == pytest.approx(2.0, abs=0.1)
        assert sources["Job Board"]["effort_per_hire"] == pytest.approx(9.9, abs=0.2)
        assert sources["LinkedIn"]["effort_per_hire"] == pytest.approx(16.0, abs=0.2)

        total_ivs = len(raw_data["Interviews"])
        absorbed = sources["Job Board"]["interviews"] + sources["LinkedIn"]["interviews"]
        assert absorbed == 115
        assert (absorbed / total_ivs) == pytest.approx(0.7188, abs=0.005)

    def test_q3_headline_and_resolved_acceptance_rates(self, raw_data):
        """Crosscheck 72.2% headline acceptance vs 83.9% resolved acceptance (+11.7 pp delta)."""
        oar = offer_acceptance_rate(raw_data)
        assert oar["offers"] == 36
        assert oar["accepted"] == 26
        assert oar["rate"] == pytest.approx(0.7222, abs=0.005)

        declined = sum(1 for o in raw_data["Offers"] if o.get("fields", o).get("Status") == "Declined")
        assert declined == 5
        resolved_rate = 26 / (26 + declined)
        assert resolved_rate == pytest.approx(0.8387, abs=0.005)

    def test_q3_ghost_offers_triage(self, raw_data):
        """Identify 5 stale pending offers including Ravi Reddy (283d) and Mohit Patel duplicate offers."""
        pending = [o.get("fields", o) for o in raw_data["Offers"] if o.get("fields", o).get("Status") == "Pending"]
        assert len(pending) == 5

        # Ravi Reddy 283 days stale as of 2026-09-02
        ravi_offer = [o for o in pending if o.get("Offer ID") == "OFF-00001"][0]
        assert ravi_offer["Offered On"] == "2025-11-23"

        # Mohit Patel duplicate pending offers across different roles
        mohit_offers = [o for o in pending if o.get("Offer ID") in {"OFF-00005", "OFF-00035"}]
        assert len(mohit_offers) == 2

    def test_q3_decline_reasons(self, raw_data):
        """Break down offer decline reasons: Role Scope 60%, Comp 20%, Counter Offer 20%."""
        declined = [o.get("fields", o) for o in raw_data["Offers"] if o.get("fields", o).get("Status") == "Declined"]
        reasons = [o.get("Decline Reason") for o in declined]
        assert reasons.count("Role Scope") == 3
        assert reasons.count("Compensation") == 1
        assert reasons.count("Counter Offer") == 1

    def test_q4_interview_to_offer_bottleneck(self, raw_data):
        """Pinpoint primary conversion bottleneck at Interview -> Offer (25.2% pass-through, 74.8% drop-off)."""
        conv = funnel_stage_conversions(raw_data)
        trans = conv["transitions"]["interview_to_offer"]
        assert trans["numerator"] == 36
        assert trans["denominator"] == 143
        assert trans["conversion_rate"] == pytest.approx(0.2517, abs=0.005)
        assert trans["drop_off_rate"] == pytest.approx(0.7483, abs=0.005)
        assert conv["bottleneck"] == "interview_to_offer"

    def test_q4_interview_drop_off_breakdown(self, raw_data):
        """Detail the 107 non-offer candidates: 70 rejected R1, 14 Final, 23 stranded in interview stage."""
        apps = [a.get("fields", a) for a in raw_data["Applications"]]
        r1_rej = sum(1 for a in apps if a.get("Stage") == "Rejected" and a.get("First Interview On") and not a.get("Final Interview On"))
        final_rej = sum(1 for a in apps if a.get("Stage") == "Rejected" and a.get("Final Interview On"))
        stranded_iv = sum(1 for a in apps if a.get("Stage") == "Interview")
        no_shows = sum(1 for a in apps if a.get("Rejection Reason") == "No Show")

        assert r1_rej == 70
        assert final_rej == 14
        assert stranded_iv == 23
        assert r1_rej + final_rej + stranded_iv == 107
        assert no_shows == 23

    def test_q4_stagnant_active_applications_and_top_5(self, raw_data):
        """Identify 105 active applications and top 5 urgent applications with pending offers."""
        active = [a.get("fields", a) for a in raw_data["Applications"] if a.get("fields", a).get("Status") == "Active"]
        assert len(active) == 105
        # 5 active applications have pending offers awaiting founder/candidate action
        offers = {o.get("fields", o).get("Application", [None])[0]: o.get("fields", o) for o in raw_data["Offers"]}
        pending_apps = [a for a in raw_data["Applications"] if offers.get(a["id"], {}).get("Status") == "Pending"]
        assert len(pending_apps) == 5

    def test_q5_missing_source_inheritance(self, raw_data):
        """Verify Applications table lacks Source and all 350 apps inherit source from Candidates."""
        assert all("Source" not in a.get("fields", a) for a in raw_data["Applications"])
        sources = source_effectiveness(raw_data)
        total_apps = sum(s["applications"] for s in sources.values())
        assert total_apps == 350
        assert "Unknown" not in sources

    def test_q5_duplicate_candidate_pairs(self, raw_data):
        """Verify 6 duplicate candidate pairs (CAND-00001..12) with identical names and phone numbers."""
        cands = {c.get("fields", c).get("Candidate ID"): c.get("fields", c) for c in raw_data["Candidates"]}
        for i in range(1, 12, 2):
            c1 = cands[f"CAND-{i:05d}"]
            c2 = cands[f"CAND-{i+1:05d}"]
            assert c1["Full Name"] == c2["Full Name"]
            assert c1["Phone"] == c2["Phone"]
            assert c1["Source"] == "Job Board"

    def test_q5_index_shift_duplicate_applications(self, raw_data):
        """Verify 50 shifted applications (APP-00301..350) where 4 candidates applied twice to same opening."""
        apps = {a.get("fields", a).get("Application ID"): a.get("fields", a) for a in raw_data["Applications"]}
        shifted = [f"APP-{i:05d}" for i in range(301, 351) if f"APP-{i:05d}" in apps]
        assert len(shifted) == 50

        # Exactly 4 candidates applied twice to the exact same Job Opening
        same_opening_pairs = []
        for i in range(1, 51):
            a1 = apps[f"APP-{i:05d}"]
            a2 = apps[f"APP-{i+300:05d}"]
            if a1.get("Opening") == a2.get("Opening"):
                same_opening_pairs.append((f"APP-{i:05d}", f"APP-{i+300:05d}"))
        assert len(same_opening_pairs) == 4
        assert same_opening_pairs == [
            ("APP-00012", "APP-00312"),
            ("APP-00016", "APP-00316"),
            ("APP-00019", "APP-00319"),
            ("APP-00031", "APP-00331"),
        ]

    def test_q5_salary_band_violations(self, raw_data):
        """Verify 5 salary band violations: 2 over max (+51.2%, +92.5%) and 3 below min (-20.6%, -6.9%, -6.2%)."""
        comp = compensation_competitiveness(raw_data, as_of=AS_OF)
        violations = comp["salary_band_violations"]
        assert len(violations) == 5

        over_max = [v for v in violations if v["type"] == "over_max"]
        below_min = [v for v in violations if v["type"] == "below_min"]
        assert len(over_max) == 2
        assert len(below_min) == 3

        # Jr Content Marketer +92.5% over max
        neha = [v for v in over_max if v["candidate_name"] == "Neha Agarwal"][0]
        assert neha["deviation_pct"] == pytest.approx(92.5, abs=0.1)

        # Jr PM +51.25% over max
        elena = [v for v in over_max if v["candidate_name"] == "Elena Okonkwo"][0]
        assert elena["deviation_pct"] == pytest.approx(51.25, abs=0.1)

        # Enterprise AE -20.625% below min
        simran = [v for v in below_min if v["candidate_name"] == "Simran Menon"][0]
        assert simran["deviation_pct"] == pytest.approx(-20.625, abs=0.1)


# ==============================================================================
# R2: Deep Strategic & Operational Insights
# ==============================================================================

class TestR2StrategicInsights:
    """Strategic hiring, bandwidth allocation, velocity, and departmental fill insights."""

    def test_r2_recruiter_load_distribution(self, raw_data):
        """Quantify recruiter workloads: Ankit leads with 129 applications, Chetan has 36."""
        bw = recruiter_interviewer_bandwidth(raw_data)
        load = bw["recruiter_load"]
        assert load["Ankit Menon"] == 129
        assert load["Nadia Almeida"] == 96
        assert load["Pooja Khanna"] == 89
        assert load["Chetan Kulkarni"] == 36
        assert sum(load.values()) == 350

    def test_r2_interviewer_workload_concentration(self, raw_data):
        """Verify top 2 interviewers (Gaurav 37, Sanjay 33) absorb 43.8% of interview bandwidth."""
        bw = recruiter_interviewer_bandwidth(raw_data)
        iv_load = bw["interviewer_load"]
        assert iv_load["Gaurav Menon"] == 37
        assert iv_load["Sanjay Iyer"] == 33
        assert bw["top_two_interviewer_share"] == pytest.approx(0.4375, abs=0.005)
        assert bw["total_interviews"] == 160

    def test_r2_interviewer_scoring_and_strictest_evaluator(self, raw_data):
        """Identify Rakesh Dubey as strictest evaluator with 1.77 average score."""
        bw = recruiter_interviewer_bandwidth(raw_data)
        scores = bw["interviewer_avg_scores"]
        assert bw["strictest_interviewer"] == "Rakesh Dubey"
        assert scores["Rakesh Dubey"] == pytest.approx(1.77, abs=0.05)
        assert scores["Kavya Reddy"] == pytest.approx(3.69, abs=0.05)

    def test_r2_time_to_hire_funnel_velocity(self, raw_data):
        """Benchmark time-to-offer and time-to-hire velocity across recruiting sources."""
        tth = time_to_hire_by_source(raw_data)
        offer_v = tth["avg_days_to_offer"]
        hire_v = tth["avg_days_to_hire"]

        # Agency is fastest to offer (29.0d)
        assert offer_v["Agency"] == pytest.approx(29.0, abs=0.5)
        # Career Site has slowest time to offer (39.2d) and hire (52.5d)
        assert offer_v["Career Site"] == pytest.approx(39.2, abs=0.5)
        assert hire_v["Career Site"] == pytest.approx(52.5, abs=0.5)
        # Referral produces swift hires (33.3d to offer, 46.9d to hire)
        assert offer_v["Referral"] == pytest.approx(33.3, abs=0.5)
        assert hire_v["Referral"] == pytest.approx(46.9, abs=0.5)

    def test_r2_departmental_headcount_fill_rates(self, raw_data):
        """Compare actual hires against approved requisition headcount targets by department."""
        dept = departmental_headcount_fill_rate(raw_data)
        assert dept["CS"]["fill_rate"] == pytest.approx(0.80, abs=0.01)       # 4 / 5
        assert dept["DAT"]["fill_rate"] == 0.0                                 # 0 / 3
        assert dept["ENG"]["fill_rate"] == pytest.approx(0.20, abs=0.01)       # 1 / 5
        assert dept["FIN"]["fill_rate"] == pytest.approx(3.333, abs=0.01)      # 10 / 3
        assert dept["MKT"]["fill_rate"] == 0.0                                 # 0 / 4
        assert dept["POP"]["fill_rate"] == pytest.approx(0.333, abs=0.01)      # 1 / 3
        assert dept["PRD"]["fill_rate"] == pytest.approx(1.333, abs=0.01)      # 4 / 3
        assert dept["SLS"]["fill_rate"] == pytest.approx(2.00, abs=0.01)       # 6 / 3

    def test_r2_departmental_budget_vs_actual_hires(self, raw_data):
        """Verify department headcount budgets and identify over-hired vs zero-hire departments."""
        dept = departmental_headcount_fill_rate(raw_data)
        # Zero hire departments with open req targets
        zero_hire = [code for code, info in dept.items() if info["hires_made"] == 0]
        assert set(zero_hire) == {"DAT", "MKT"}
        # Over-hired departments (fill rate > 100%)
        over_hired = [code for code, info in dept.items() if info["fill_rate"] > 1.0]
        assert set(over_hired) == {"FIN", "PRD", "SLS"}


# ==============================================================================
# R3: Output Artifact Verification Across Multi-Formats
# ==============================================================================

class TestR3MultiFormatOutputs:
    """End-to-end artifact generation, schema validation, and guardrail compliance."""

    def test_r3_all_seven_artifacts_produced(self, tmp_path):
        """Verify pipeline execution produces all 7 required output artifacts."""
        out_dir = tmp_path / "raw_pipeline_outputs"
        res = run_pipeline(RAW_PATH, output_dir=out_dir, as_of=AS_OF)
        required = {
            "briefing.md",
            "memo.md",
            "findings.md",
            "findings.csv",
            "briefing.html",
            "briefing.json",
            "candidate_actions.json",
        }
        for name in required:
            file_path = out_dir / name
            assert file_path.is_file(), f"Missing required artifact: {name}"
            assert file_path.stat().st_size > 0, f"Artifact is empty: {name}"

    def test_r3_advisory_vocabulary_and_human_review_invariant(self, tmp_path):
        """Enforce strict advisory vocabulary and mandatory human review invariant."""
        out_dir = tmp_path / "advisory_verify"
        run_pipeline(RAW_PATH, output_dir=out_dir, as_of=AS_OF)
        actions = json.loads((out_dir / "candidate_actions.json").read_text(encoding="utf-8"))
        assert len(actions) > 0

        allowed = {"review", "advance", "escalate", "request_feedback", "close", "request feedback", "close current process"}
        forbidden = {"reject", "rejected", "terminate", "auto_reject", "dismiss"}

        for a in actions:
            assert a["action"] in allowed, f"Forbidden action vocabulary found: {a['action']}"
            assert a["action"] not in forbidden
            assert a["requires_human_review"] is True, "Missing mandatory human review requirement"
            assert "human review" in a.get("human_review_note", "").lower()

    def test_r3_structured_evidence_blocks(self, tmp_path):
        """Confirm every finding in findings.json includes structured evidence blocks."""
        out_dir = tmp_path / "evidence_verify"
        run_pipeline(RAW_PATH, output_dir=out_dir, as_of=AS_OF)
        findings_payload = json.loads((out_dir / "findings.json").read_text(encoding="utf-8"))
        findings = findings_payload.get("findings", [])
        assert len(findings) > 0

        for f in findings:
            assert "finding_id" in f
            assert "title" in f
            assert "observed_fact" in f
            assert "confidence" in f
            assert "severity" in f
            evidence_list = f.get("evidence", [])
            assert len(evidence_list) > 0, f"Finding {f['finding_id']} missing evidence block"
            for ev in evidence_list:
                assert "source" in ev
                assert "method" in ev

    def test_r3_csv_schema_and_html_safety(self, tmp_path):
        """Verify findings.csv schema compliance and briefing.html markup integrity."""
        out_dir = tmp_path / "schema_verify"
        run_pipeline(RAW_PATH, output_dir=out_dir, as_of=AS_OF)

        # CSV schema
        with open(out_dir / "findings.csv", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required_cols = {"finding_id", "title", "observed_fact", "interpretation", "recommendation", "confidence", "severity"}
            assert required_cols.issubset(set(reader.fieldnames or []))
            rows = list(reader)
            assert len(rows) > 0

        # HTML markup
        html = (out_dir / "briefing.html").read_text(encoding="utf-8")
        assert "<!doctype html>" in html.lower()
        assert "human review" in html.lower()
        assert "<script>" not in html

    def test_r3_monday_operating_schedule_in_briefing(self, tmp_path):
        """Verify briefing contains the Monday morning operating schedule and top urgent alerts."""
        out_dir = tmp_path / "briefing_schedule_verify"
        res = run_pipeline(RAW_PATH, output_dir=out_dir, as_of=AS_OF)
        briefing = res["briefing"]

        # Urgent items contain top offer alerts
        urgent_text = " ".join(briefing.urgent_items)
        assert "stalled" in urgent_text.lower() or "offer" in urgent_text.lower()

        # Next actions contain Monday operating schedule
        actions_text = " ".join(briefing.next_actions)
        assert "monday" in actions_text.lower()
