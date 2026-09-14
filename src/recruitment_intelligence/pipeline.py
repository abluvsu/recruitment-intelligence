"""Offline end-to-end orchestration pipeline.

Converts read-only Airtable recruitment data into deterministic, evidence-backed
founder decisions answering Q1–Q5, generating advisory candidate actions, diagnosing
data quality anomalies, and producing daily recruitment briefings offline.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .agents.advisory_queue import generate_advisory_actions
from .analytics.engine import AnalyticsEngine, AnalyticsResult
from .domain import Briefing, MetricClaim
from .outputs.briefing import generate_executive_briefing
from .outputs.renderers import write_artifacts
from .quality.auditor import QualityAuditResult, run_quality_audit
from .quality.sensitivity import SensitivityReport, quantify_sensitivity


DEFAULT_SNAPSHOT_LOCATIONS = (
    Path("data/raw/airtable_snapshot.json"),
    Path("fixtures/clean_snapshot.json"),
    Path("fixtures/recruitment_snapshot.json"),
)


def load_snapshot(snapshot_path: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Load a snapshot from path or find first available default snapshot."""
    candidates = [Path(snapshot_path)] if snapshot_path else list(DEFAULT_SNAPSHOT_LOCATIONS)
    for path in candidates:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): list(v) for k, v in data.items() if isinstance(v, list)}
    raise FileNotFoundError(
        f"No snapshot found at supplied path: {snapshot_path}. "
        f"Checked default candidates: {[str(p) for p in DEFAULT_SNAPSHOT_LOCATIONS]}"
    )


def run_pipeline(
    snapshot: Mapping[str, Any] | str | Path | None = None,
    output_dir: str | Path = "outputs",
    *,
    as_of: date | datetime | str | None = None,
    include_cost_appendix: bool = True,
    period: str = "daily",
) -> dict[str, Any]:
    """Execute complete offline intelligence pipeline and write output artifacts.

    Answers Q1–Q5 deterministically:
    - Q1: Table counts & schema profiling
    - Q2: Source effectiveness & ranking vs pipeline effort
    - Q3: Offer acceptance rate with denominator justification
    - Q4: Funnel stage transitions, aging, and bottleneck diagnosis
    - Q5: Data quality audit & counterfactual sensitivity analysis

    Returns dict with:
    - briefing: Briefing domain contract
    - analytics: AnalyticsResult
    - quality: QualityAuditResult
    - sensitivity: SensitivityReport
    - artifacts: Mapping[str, Path]
    """
    if isinstance(snapshot, (str, Path)) or snapshot is None:
        tables = load_snapshot(snapshot)
    elif isinstance(snapshot, Mapping):
        tables = {str(k): list(v) for k, v in snapshot.items() if isinstance(v, list)}
    else:
        raise TypeError(f"Invalid snapshot type: {type(snapshot).__name__}")

    # 1. Quality Audit (Q5)
    quality_result: QualityAuditResult = run_quality_audit(tables)

    # 2. Deterministic Analytics Engine (Q1-Q4)
    engine = AnalyticsEngine(tables, as_of=as_of)
    analytics_result: AnalyticsResult = engine.analyze()

    # 3. Counterfactual Sensitivity Analysis (Q5)
    sensitivity_result: SensitivityReport = quantify_sensitivity(
        tables,
        audit_result=quality_result,
        as_of=as_of,
    )

    # 4. Advisory Candidate Action Queue (strictly advisory, requires human review)
    candidate_actions = generate_advisory_actions(tables, as_of=as_of)

    # 5. Synthesize Executive Daily Briefing & Isolated Cost Appendix
    briefing: Briefing = generate_executive_briefing(
        tables,
        analytics_result=analytics_result,
        quality_result=quality_result,
        sensitivity_result=sensitivity_result,
        candidate_actions=candidate_actions,
        period=period,
        as_of=as_of,
        include_cost_appendix=include_cost_appendix,
    )

    # 6. Persist All Output Artifacts
    artifacts = write_artifacts(
        output_dir,
        findings=briefing.findings,
        quality_warnings=briefing.quality_warnings,
        briefing=briefing,
    )

    return {
        "briefing": briefing,
        "analytics": analytics_result,
        "quality": quality_result,
        "sensitivity": sensitivity_result,
        "candidate_actions": candidate_actions,
        "artifacts": artifacts,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for pipeline execution."""
    parser = argparse.ArgumentParser(description="Run Recruitment Intelligence Offline Pipeline")
    parser.add_argument(
        "snapshot",
        nargs="?",
        type=Path,
        default=None,
        help="Path to cached Airtable JSON snapshot (defaults to data/raw or fixtures)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory to write output artifacts (default: outputs)",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Reference date for aging and stalled calculations (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--no-cost-appendix",
        action="store_true",
        help="Omit external cost research appendix",
    )
    args = parser.parse_args(argv)

    try:
        results = run_pipeline(
            snapshot=args.snapshot,
            output_dir=args.output_dir,
            as_of=args.as_of,
            include_cost_appendix=not args.no_cost_appendix,
        )
        print(f"Pipeline executed successfully. Artifacts written to {args.output_dir}:")
        for name, path in sorted(results["artifacts"].items()):
            print(f"  - {name}: {path}")
        return 0
    except Exception as exc:
        print(f"Pipeline error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
