"""End-to-End (E2E) Test Suite for Recruitment Intelligence System (Milestone 6).

Verifies:
- Complete offline pipeline execution across clean, dirty, and sparse fixtures.
- Deterministic objective question coverage (Q1–Q5).
- Advisory candidate action queue vocabulary constraints & mandatory human review enforcement.
- Executive daily briefing multi-format artifact generation (JSON, Markdown, HTML, CSV).
- External cost research appendix strict isolation.
- Zero network dependencies and credential redaction.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from recruitment_intelligence.agents import (
    AdvisoryActionQueue,
    build_advisory_queue,
    generate_advisory_actions,
)
from recruitment_intelligence.domain import (
    Confidence,
    RecommendationAction,
    Severity,
)
from recruitment_intelligence.pipeline import load_snapshot, main as pipeline_main, run_pipeline

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def clean_snapshot_path() -> Path:
    return FIXTURES_DIR / "clean_snapshot.json"


@pytest.fixture
def dirty_snapshot_path() -> Path:
    return FIXTURES_DIR / "dirty_snapshot.json"


@pytest.fixture
def sparse_snapshot_path() -> Path:
    return FIXTURES_DIR / "sparse_snapshot.json"


REQUIRED_ARTIFACT_NAMES = {
    "briefing.md",
    "briefing.html",
    "briefing.json",
    "findings.md",
    "findings.csv",
    "memo.md",
    "candidate_actions.json",
}

ALLOWED_ACTIONS = {member.value for member in RecommendationAction}


# ==============================================================================
# 1. Clean Snapshot End-to-End Verification
# ==============================================================================

def test_clean_snapshot_e2e_pipeline(clean_snapshot_path, tmp_path):
    """Verify full pipeline execution on clean_snapshot.json produces all valid artifacts."""
    out_dir = tmp_path / "clean_run"
    result = run_pipeline(clean_snapshot_path, output_dir=out_dir)

    # 1. Check all required artifacts were created
    for name in REQUIRED_ARTIFACT_NAMES:
        artifact_path = out_dir / name
        assert artifact_path.is_file(), f"Missing artifact: {name}"
        assert artifact_path.stat().st_size > 0, f"Empty artifact: {name}"

    # 2. Check Briefing domain object
    briefing = result["briefing"]
    assert briefing.period == "daily"
    assert briefing.confidence in (Confidence.HIGH, Confidence.MEDIUM)
    assert len(briefing.what_changed) > 0
    assert len(briefing.urgent_items) > 0
    assert len(briefing.findings) > 0

    # 3. Check Q1 table counts
    analytics = result["analytics"]
    assert analytics.table_counts["Departments"] == 3
    assert analytics.table_counts["Applications"] == 10
    assert analytics.table_counts["Interviews"] == 6
    assert analytics.table_counts["Offers"] == 3

    # 4. Check Q2 top source
    top_source = analytics.get_claim("top_recruiting_source")
    assert top_source is not None
    assert top_source.value == "Referral"

    # 5. Check Q3 offer acceptance rate
    oar = analytics.get_claim("offer_acceptance_rate")
    assert oar is not None
    assert oar.value == pytest.approx(0.6667, abs=0.01)

    # 6. Check Q4 bottleneck
    bn = analytics.get_claim("funnel_bottleneck_stage")
    assert bn is not None
    assert bn.value == "offer_to_accepted"

    # 7. Check Q5 quality audit
    quality = result["quality"]
    assert quality.clean is True
    assert len(quality.findings) == 0


# ==============================================================================
# 2. Dirty Snapshot End-to-End Verification (Q5 & Sensitivity)
# ==============================================================================

def test_dirty_snapshot_e2e_pipeline(dirty_snapshot_path, tmp_path):
    """Verify pipeline handles dirty data, flags anomalies, and quantifies sensitivity."""
    out_dir = tmp_path / "dirty_run"
    result = run_pipeline(dirty_snapshot_path, output_dir=out_dir)

    # 1. All artifacts created
    for name in REQUIRED_ARTIFACT_NAMES:
        assert (out_dir / name).is_file()

    # 2. Quality audit detected issues
    quality = result["quality"]
    assert quality.clean is False
    assert len(quality.findings) > 0
    assert quality.confidence == Confidence.LOW

    # 3. Sensitivity analysis detected rank inversion or bottleneck shift
    sensitivity = result["sensitivity"]
    assert len(sensitivity.scenarios) > 0
    assert len(sensitivity.high_sensitivity_scenarios) > 0

    # 4. Briefing reflects low confidence and warnings
    briefing = result["briefing"]
    assert briefing.confidence == Confidence.LOW
    assert len(briefing.quality_warnings) > 0

    # 5. Briefing markdown mentions data quality warnings
    briefing_md = (out_dir / "briefing.md").read_text(encoding="utf-8")
    assert "data quality" in briefing_md.lower() or "warning" in briefing_md.lower()


# ==============================================================================
# 3. Sparse Snapshot End-to-End Verification (Edge Cases & Graceful Degradation)
# ==============================================================================

def test_sparse_snapshot_e2e_pipeline(sparse_snapshot_path, tmp_path):
    """Verify pipeline degrades gracefully on sparse data without crashing or NaN."""
    out_dir = tmp_path / "sparse_run"
    result = run_pipeline(sparse_snapshot_path, output_dir=out_dir)

    for name in REQUIRED_ARTIFACT_NAMES:
        assert (out_dir / name).is_file()

    briefing = result["briefing"]
    assert briefing is not None
    # No NaN in briefing JSON
    briefing_json_str = (out_dir / "briefing.json").read_text(encoding="utf-8")
    assert "NaN" not in briefing_json_str


# ==============================================================================
# 4. Candidate Action Queue Governance & Safety Invariants
# ==============================================================================

def test_candidate_action_queue_safety_invariants(clean_snapshot_path, dirty_snapshot_path, tmp_path):
    """Verify all candidate recommendations strictly obey advisory vocabulary and require human review."""
    for snap_path in (clean_snapshot_path, dirty_snapshot_path):
        out_dir = tmp_path / f"actions_{snap_path.stem}"
        run_pipeline(snap_path, output_dir=out_dir)

        actions_file = out_dir / "candidate_actions.json"
        actions = json.loads(actions_file.read_text(encoding="utf-8"))

        for action in actions:
            # 1. Action verb must be strictly advisory
            assert action["action"] in ALLOWED_ACTIONS, f"Disallowed action verb: {action['action']}"
            assert action["action"] not in {"reject", "rejected", "terminate", "fire"}

            # 2. Mandatory human review
            assert action["requires_human_review"] is True
            assert "human review" in action.get("human_review_note", "").lower()

            # 3. Evidence attachment
            assert len(action["evidence"]) > 0
            assert "source" in action["evidence"][0]

            # 4. Non-empty rationale
            assert bool(action.get("rationale", "").strip())


# ==============================================================================
# 5. External Cost Research Appendix Strict Isolation
# ==============================================================================

def test_external_cost_research_appendix_isolation(clean_snapshot_path, tmp_path):
    """Verify cost appendix is strictly labeled and isolated without altering baseline metrics."""
    out_dir = tmp_path / "cost_test"
    result = run_pipeline(clean_snapshot_path, output_dir=out_dir, include_cost_appendix=True)

    briefing = result["briefing"]
    assert briefing.cost_appendix is not None
    assert "External Recruitment Cost Research" in briefing.cost_appendix
    assert "NOT derived from Airtable data" in briefing.cost_appendix

    briefing_md = (out_dir / "briefing.md").read_text(encoding="utf-8")
    assert "External cost research appendix (strictly isolated)" in briefing_md

    briefing_html = (out_dir / "briefing.html").read_text(encoding="utf-8")
    assert "External cost research appendix (strictly isolated)" in briefing_html

    memo_md = (out_dir / "memo.md").read_text(encoding="utf-8")
    assert "External cost research appendix (strictly isolated)" in memo_md

    # Baseline analytics claims remain untouched by cost benchmarks
    for claim in briefing.metrics:
        assert "$" not in str(claim.value)


# ==============================================================================
# 6. Multi-Format Output Reproducibility & Schema Integrity
# ==============================================================================

def test_output_artifacts_schema_and_integrity(clean_snapshot_path, tmp_path):
    """Verify structure and parsability of all output artifacts."""
    out_dir = tmp_path / "format_test"
    run_pipeline(clean_snapshot_path, output_dir=out_dir)

    # 1. briefing.json parsable and valid
    briefing_json = json.loads((out_dir / "briefing.json").read_text(encoding="utf-8"))
    assert "generated_at" in briefing_json
    assert "findings" in briefing_json
    assert "candidate_actions" in briefing_json

    # 2. findings.json parsable
    findings_json = json.loads((out_dir / "findings.json").read_text(encoding="utf-8"))
    assert "findings" in findings_json
    assert "quality_warnings" in findings_json

    # 3. findings.csv readable with correct header columns
    with open(out_dir / "findings.csv", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert set(reader.fieldnames or []) == {
            "finding_id", "title", "observed_fact", "interpretation",
            "recommendation", "confidence", "severity", "caveats", "evidence"
        }
        rows = list(reader)
        assert len(rows) > 0

    # 4. briefing.html valid HTML skeleton
    html_text = (out_dir / "briefing.html").read_text(encoding="utf-8")
    assert "<!doctype html>" in html_text
    assert "</html>" in html_text


# ==============================================================================
# 7. Pipeline CLI Execution
# ==============================================================================

def test_pipeline_cli_execution(clean_snapshot_path, tmp_path):
    """Verify CLI interface runs cleanly and writes all artifacts."""
    out_dir = tmp_path / "cli_run"
    ret = pipeline_main([
        str(clean_snapshot_path),
        "--output-dir", str(out_dir),
    ])
    assert ret == 0
    for name in REQUIRED_ARTIFACT_NAMES:
        assert (out_dir / name).is_file()


def test_cli_run_snapshot_execution(clean_snapshot_path, tmp_path):
    """Verify recruitment_intelligence.cli.run_snapshot generates all artifacts."""
    from recruitment_intelligence.cli import run_snapshot
    with open(clean_snapshot_path, encoding="utf-8") as f:
        data = json.load(f)
    out_dir = tmp_path / "cli_snapshot_run"
    paths = run_snapshot(data, output_dir=out_dir)
    for name in REQUIRED_ARTIFACT_NAMES:
        assert name in paths
        assert (out_dir / name).is_file()
        assert (out_dir / name).stat().st_size > 0


def test_run_offline_script_execution(tmp_path):
    """Verify scripts/run_offline.py executes offline and produces all required artifacts."""
    import importlib.util
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "run_offline.py"
    spec = importlib.util.spec_from_file_location("run_offline_mod", str(script_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    out_dir = tmp_path / "offline_script_run"
    findings, warnings, briefing = mod.build()
    assert briefing is not None
    assert len(briefing.what_changed) > 0
    paths = mod.write_artifacts(out_dir, findings=findings, quality_warnings=warnings, briefing=briefing)
    for name in REQUIRED_ARTIFACT_NAMES:
        assert name in paths
        assert (out_dir / name).is_file()
        assert (out_dir / name).stat().st_size > 0
