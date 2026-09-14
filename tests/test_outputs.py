import csv
import io
import json

from recruitment_intelligence.domain import (
    Briefing,
    CandidateRecommendation,
    Confidence,
    EvidenceReference,
    Finding,
    RecommendationAction,
    Severity,
)
from recruitment_intelligence.outputs import (
    build_candidate_action_queue,
    build_cost_research_appendix,
    compare_previous_run,
    generate_executive_briefing,
    produce_daily_briefing,
    render_briefing_html,
    render_briefing_json,
    render_briefing_markdown,
    render_findings_csv,
    render_findings_json,
    render_findings_markdown,
    render_memo,
    write_artifacts,
)
from recruitment_intelligence.outputs.memo import render_memo as memo_render_memo


def sample():
    evidence = (EvidenceReference(source="analytics.test", table="Applications", record_ids=("a1",)),)
    finding = Finding("f1", "Referral result", "Referral produced one hire.", Confidence.MEDIUM, evidence=evidence, interpretation="Promising channel.", recommendation="Review role mix.", caveats=("No cost data.",))
    action = CandidateRecommendation("c1", "review", "Recent interview needs review", Confidence.LOW, evidence=evidence)
    briefing = Briefing("2025-01-01T00:00:00+00:00", "test", findings=(finding,), candidate_actions=(action,), next_actions=("Review candidate.",))
    return finding, action, briefing


# ---------------------------------------------------------------------------
# 1. Output Reproducibility, Safety Language & Isolation
# ---------------------------------------------------------------------------


def test_renderers_are_reproducible_and_evidence_preserving():
    finding, _, _ = sample()
    assert render_findings_json((finding,)) == render_findings_json((finding,))
    payload = json.loads(render_findings_json((finding,)))
    assert payload["findings"][0]["evidence"][0]["source"] == "analytics.test"
    assert "Observed fact" in render_findings_markdown((finding,))
    assert "analytics.test" in render_findings_csv((finding,))


def test_memo_and_briefing_keep_safety_language():
    finding, action, briefing = sample()
    memo = render_memo((finding,), [{"check": "missing_value", "severity": "high", "message": "missing source", "metric_impact": ["source_effectiveness"]}])
    assert "Observed fact" in memo and "Data trust" in memo
    assert "automatically" in memo
    markdown = render_findings_markdown((finding,), [{"check": "bad", "severity": "high", "message": "warning"}])
    assert "Data-quality warnings" in markdown
    assert "human review" in render_briefing_html(briefing).lower()
    assert build_candidate_action_queue((action,))[0]["requires_human_review"] is True


def test_compare_and_write_artifacts(tmp_path):
    finding, _, briefing = sample()
    changed = Finding("f1", "Referral result", "Referral produced two hires.", Confidence.HIGH)
    diff = compare_previous_run({"findings": (finding,)}, {"findings": (changed,)})
    assert len(diff["changed"]) == 1
    paths = write_artifacts(tmp_path, findings=(finding,), briefing=briefing)
    assert {"findings.json", "findings.csv", "findings.md", "memo.md", "briefing.json", "briefing.md", "briefing.html", "candidate_actions.json"} <= set(paths)
    assert (tmp_path / "findings.json").exists()


def test_cost_research_appendix_content_and_isolation():
    appendix = build_cost_research_appendix()
    assert "External Recruitment Cost Research" in appendix
    assert "NOT derived from Airtable data" in appendix
    assert "Software Engineering" in appendix


def test_briefing_with_cost_appendix_rendered():
    finding, action, briefing = sample()
    appendix = build_cost_research_appendix()
    briefing_with_cost = Briefing(
        briefing.generated_at,
        briefing.period,
        findings=briefing.findings,
        candidate_actions=briefing.candidate_actions,
        cost_appendix=appendix,
    )
    md = render_briefing_markdown(briefing_with_cost)
    assert "External cost research appendix (strictly isolated)" in md
    html_out = render_briefing_html(briefing_with_cost)
    assert "External cost research appendix (strictly isolated)" in html_out
    memo_out = render_memo(briefing.findings, cost_appendix=appendix)
    assert "External cost research appendix (strictly isolated)" in memo_out


def test_generate_and_produce_daily_briefing(tmp_path):
    tables = {
        "Applications": [
            {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired", "applied_at": "2025-01-01"},
            {"id": "a2", "candidate_id": "c2", "source": "Job board", "status": "interview", "applied_at": "2025-01-10"},
        ],
        "Candidates": [{"id": "c1"}, {"id": "c2"}],
        "Job Openings": [{"id": "j1", "title": "Eng"}],
        "Interviews": [{"id": "i1", "application_id": "a2"}],
        "Offers": [{"id": "o1", "application_id": "a1", "status": "accepted"}],
    }
    briefing = generate_executive_briefing(tables)
    assert briefing is not None
    assert briefing.cost_appendix is not None
    assert len(briefing.candidate_actions) > 0

    briefing2, paths = produce_daily_briefing(tables, output_dir=tmp_path / "briefing_prod")
    assert len(paths) == 8
    assert (tmp_path / "briefing_prod" / "briefing.html").exists()


# ---------------------------------------------------------------------------
# 2. Layout Conformance, Edge Cases & Action Queue Prioritization
# ---------------------------------------------------------------------------


def test_generate_executive_briefing_empty_tables_graceful_degradation():
    """Empty table snapshot produces calibrated briefing with INSUFFICIENT confidence."""
    briefing = generate_executive_briefing({})
    assert briefing.confidence is Confidence.INSUFFICIENT
    assert "0 records across 0 tables" in briefing.executive_summary
    assert "Unknown — insufficient evidence" in briefing.executive_summary
    assert briefing.candidate_actions == ()


def test_briefing_cost_appendix_toggle_and_custom_benchmarks():
    """Cost appendix can be disabled or replaced with custom benchmarks."""
    b_no_cost = generate_executive_briefing({}, include_cost_appendix=False)
    assert b_no_cost.cost_appendix is None
    assert "External cost research" not in render_briefing_markdown(b_no_cost)
    assert "External cost research" not in render_memo(b_no_cost.findings, cost_appendix=b_no_cost.cost_appendix)

    custom_text = "### Custom Benchmark Context\nEngineering cost-per-hire: $5,000"
    b_custom = generate_executive_briefing({}, custom_cost_appendix=custom_text)
    assert b_custom.cost_appendix == custom_text
    assert "Custom Benchmark Context" in render_briefing_markdown(b_custom)
    assert "Custom Benchmark Context" in render_briefing_html(b_custom)


def test_compare_previous_run_added_and_removed():
    """compare_previous_run tracks added and removed findings across pipeline runs."""
    f1 = Finding("f1", "Finding 1", "Fact 1", Confidence.MEDIUM)
    f2 = Finding("f2", "Finding 2", "Fact 2", Confidence.HIGH)

    diff_added = compare_previous_run({"findings": (f1, f2)}, {"findings": (f1,)})
    assert len(diff_added["added"]) == 1
    assert diff_added["added"][0]["finding_id"] == "f2"

    diff_removed = compare_previous_run({"findings": (f1,)}, {"findings": (f1, f2)})
    assert len(diff_removed["removed"]) == 1
    assert diff_removed["removed"][0]["finding_id"] == "f2"


def test_render_briefing_html_xss_escaping():
    """HTML renderer escapes script and dangerous HTML tags in findings and recommendations."""
    malicious_action = CandidateRecommendation(
        candidate_id="cand<script>alert('xss')</script>",
        action="review",
        rationale="Candidate test <img src=x onerror=alert(1)>",
        confidence=Confidence.HIGH,
    )
    malicious_finding = Finding(
        finding_id="f-xss",
        title="Title <svg/onload=alert('xss')>",
        observed_fact="Fact with <b>bold</b> and <script>attack()</script>",
        confidence=Confidence.MEDIUM,
    )
    briefing = Briefing(
        "2025-01-01T00:00:00+00:00",
        "daily",
        findings=(malicious_finding,),
        candidate_actions=(malicious_action,),
    )
    html_out = render_briefing_html(briefing)
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "<img" not in html_out
    assert "&lt;img" in html_out
    assert "<svg" not in html_out


def test_memo_module_direct_import_and_render():
    """Direct import from outputs.memo conforms to PROJECT.md code layout."""
    assert memo_render_memo is render_memo
    finding, _, _ = sample()
    memo = memo_render_memo((finding,))
    assert "# Recruitment intelligence memo" in memo
    assert "## Executive summary" in memo
    assert "## Findings" in memo
    assert "## Data trust" in memo
    assert "## Next action" in memo


def test_candidate_action_queue_urgency_priority_sorting():
    """Candidate action queue preserves urgency priority (escalate > request_feedback > advance > review > close)."""
    ev = EvidenceReference(source="test", table="Applications")
    rec_escalate = CandidateRecommendation("c-esc", RecommendationAction.ESCALATE, "Urgent stall", Confidence.HIGH, evidence=(ev,))
    rec_feedback = CandidateRecommendation("c-fb", RecommendationAction.REQUEST_FEEDBACK, "Pending scorecard", Confidence.HIGH, evidence=(ev,))
    rec_advance = CandidateRecommendation("c-adv", RecommendationAction.ADVANCE, "Offer follow-up", Confidence.HIGH, evidence=(ev,))
    rec_review = CandidateRecommendation("c-rev", RecommendationAction.REVIEW, "Review required", Confidence.MEDIUM, evidence=(ev,))
    rec_close = CandidateRecommendation("c-close", RecommendationAction.CLOSE, "Close terminal", Confidence.HIGH, evidence=(ev,))

    # Pass in scrambled order
    scrambled = [rec_close, rec_review, rec_advance, rec_feedback, rec_escalate]
    queue = build_candidate_action_queue(scrambled)

    actions = [item["action"] for item in queue]
    assert actions == [
        "escalate",
        "request_feedback",
        "advance",
        "review",
        "close",
    ]
    # Escalate must come before close (unlike alphabetical sort where close < escalate)
    assert actions.index("escalate") < actions.index("close")
    assert actions.index("advance") < actions.index("close")


def test_sparse_tables_briefing_and_memo_generation():
    """Sparse tables with missing linked records execute without errors."""
    sparse_tables = {
        "Applications": [{"id": "app-sparse", "candidate_id": None, "status": "active"}],
        "Candidates": [],
        "Interviews": [],
        "Offers": [],
    }
    briefing = generate_executive_briefing(sparse_tables)
    assert briefing is not None
    assert briefing.confidence in (Confidence.LOW, Confidence.INSUFFICIENT)
    memo = render_memo(briefing.findings, quality_warnings=briefing.quality_warnings)
    assert len(memo) > 0


def test_produce_daily_briefing_artifact_file_integrity(tmp_path):
    """produce_daily_briefing writes 8 atomic UTF-8 encoded artifacts with valid content."""
    tables = {
        "Applications": [
            {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired", "applied_at": "2025-01-01"},
        ],
        "Candidates": [{"id": "c1"}],
        "Job Openings": [],
        "Interviews": [],
        "Offers": [],
    }
    out_dir = tmp_path / "artifacts_verify"
    _, paths = produce_daily_briefing(tables, output_dir=out_dir)
    assert len(paths) == 8

    expected_files = {
        "briefing.md",
        "briefing.html",
        "briefing.json",
        "findings.md",
        "findings.csv",
        "findings.json",
        "memo.md",
        "candidate_actions.json",
    }
    assert set(paths) == expected_files

    for rel_path in paths:
        full_path = out_dir / rel_path
        assert full_path.exists()
        assert full_path.stat().st_size > 0
        # Ensure valid UTF-8
        content = full_path.read_text(encoding="utf-8")
        assert len(content) > 0



def test_candidate_actions_json_schema_and_advisory_invariants(tmp_path):
    """candidate_actions.json strictly adheres to advisory constraints and human review note."""
    tables = {
        "Applications": [
            {"id": "a1", "candidate_id": "c1", "status": "interview", "applied_at": "2025-01-01", "updated_at": "2025-01-02"},
            {"id": "a2", "candidate_id": "c2", "status": "rejected", "applied_at": "2025-01-01", "updated_at": "2025-01-03"},
        ],
        "Interviews": [
            {"id": "iv1", "application_id": "a1", "status": "completed", "completed_at": "2025-01-05", "score": 5},
        ],
    }
    out_dir = tmp_path / "actions_verify"
    produce_daily_briefing(tables, output_dir=out_dir, as_of="2025-01-10")

    actions_file = out_dir / "candidate_actions.json"
    actions = json.loads(actions_file.read_text(encoding="utf-8"))
    assert len(actions) > 0

    allowed = {"review", "advance", "escalate", "request_feedback", "close"}
    for action in actions:
        assert action["action"] in allowed
        assert action["requires_human_review"] is True
        assert "human review" in action.get("human_review_note", "").lower()
        assert len(action.get("evidence", [])) > 0


def test_render_findings_csv_format_and_escaping():
    """render_findings_csv produces standard RFC 4180 CSV with correct headers and quotes."""
    evidence = (EvidenceReference(source="analytics.test", table="Applications"),)
    finding = Finding(
        "f-csv",
        "Cost & Channel, Analysis",
        'Observed fact with "quotes" and commas, in text',
        Confidence.HIGH,
        evidence=evidence,
        interpretation="Channel yield: high",
        recommendation="Prioritize referrals",
    )
    csv_str = render_findings_csv((finding,))
    reader = csv.reader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == 2  # Header + 1 record
    headers = rows[0]
    assert headers == ["finding_id", "title", "observed_fact", "interpretation", "recommendation", "confidence", "severity", "caveats", "evidence"]
    data_row = rows[1]
    assert data_row[0] == "f-csv"
    assert data_row[1] == "Cost & Channel, Analysis"
    assert "quotes" in data_row[2]


def test_render_quality_warnings_from_finding_objects():
    """render_findings_markdown and render_memo correctly render Finding domain objects as quality warnings."""
    ev = (EvidenceReference(source="quality_checks", table="Applications", record_ids=("a1",)),)
    warning_finding = Finding(
        finding_id="qual-fk-apps-cand",
        category="foreign_key_integrity",
        title="Foreign Key Violation in Applications.candidate_id",
        observed_fact="2 record(s) link to missing Candidates record(s): c-missing",
        severity=Severity.HIGH,
        confidence=Confidence.HIGH,
        evidence=ev,
        caveats=("Metric impact: referential_integrity",),
    )

    md = render_findings_markdown((), quality_warnings=(warning_finding,))
    assert "## Data-quality warnings" in md
    assert "**high**" in md.lower()
    assert "foreign_key_integrity" in md
    assert "Applications" in md
    assert "c-missing" in md
    assert "referential_integrity" in md
    assert "unknown.*" not in md

    memo = render_memo((), quality_warnings=(warning_finding,))
    assert "## Data trust" in memo
    assert "HIGH:" in memo
    assert "c-missing" in memo
    assert "referential_integrity" in memo
    assert "- HIGH:  (impact: unspecified)" not in memo


def test_render_findings_recommendation_and_description_synchronization():
    """Findings with recommendations tuple populate recommendation in CSV, Markdown, and Memo."""
    ev = (EvidenceReference(source="analytics", table="Applications"),)
    f = Finding(
        finding_id="f-sens",
        title="Ranking Inversion",
        observed_fact="Top source flipped",
        confidence=Confidence.HIGH,
        evidence=ev,
        recommendations=("Verify source attribution before spending budget.",),
        description="Data anomalies inverted the top source.",
    )
    # Model contract level synchronization
    assert f.recommendation == "Verify source attribution before spending budget."
    assert f.interpretation == "Data anomalies inverted the top source."

    # CSV output
    csv_text = render_findings_csv((f,))
    assert "Verify source attribution before spending budget." in csv_text

    # Markdown output
    md_text = render_findings_markdown((f,))
    assert "**Recommendation:** Verify source attribution before spending budget." in md_text
    assert "**Interpretation:** Data anomalies inverted the top source." in md_text
    assert "No recommendation" not in md_text

    # Memo output
    memo_text = render_memo((f,))
    assert "**Recommendation:** Verify source attribution before spending budget." in memo_text
    assert "No recommendation" not in memo_text


def test_render_briefing_html_includes_findings_and_warnings():
    """render_briefing_html renders full sections including Findings and Data-quality warnings."""
    ev = (EvidenceReference(source="analytics", table="Applications"),)
    finding = Finding("f-main", "Top Source", "Referral produced 5 hires", Confidence.HIGH, evidence=ev, recommendation="Keep referral program")
    warning = Finding("w-main", "Missing Date", "3 applications lack dates", Confidence.MEDIUM, severity=Severity.HIGH, evidence=ev)

    briefing = Briefing(
        generated_at="2025-01-01T00:00:00+00:00",
        period="daily",
        findings=(finding,),
        quality_warnings=(warning,),
    )
    html_out = render_briefing_html(briefing)
    assert "<h2>Findings</h2>" in html_out
    assert "Top Source" in html_out
    assert "Referral produced 5 hires" in html_out
    assert "Keep referral program" in html_out
    assert "<h2>Data-quality warnings</h2>" in html_out
    assert "Missing Date" in html_out
    assert "3 applications lack dates" in html_out


def test_generate_executive_briefing_sparse_no_hallucinations():
    """Sparse snapshot briefing does not create hallucinated findings for 'Unknown' source or bottleneck."""
    sparse_tables = {
        "Departments": [],
        "People": [],
        "Job Openings": [],
        "Candidates": [],
        "Applications": [],
        "Interviews": [],
        "Offers": [],
        "Findings": [],
    }
    briefing = generate_executive_briefing(sparse_tables)
    finding_ids = [f.finding_id for f in briefing.findings]
    assert "find-top-source" not in finding_ids
    assert "find-funnel-bottleneck" not in finding_ids
    assert "Zero recruitment records found in snapshot" in briefing.urgent_items[0]

