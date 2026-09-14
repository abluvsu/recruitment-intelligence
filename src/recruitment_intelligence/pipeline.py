"""Offline end-to-end orchestration pipeline.

Converts read-only Airtable recruitment data into deterministic, evidence-backed
founder decisions answering Q1–Q5, generating advisory candidate actions, diagnosing
data quality anomalies, and producing daily recruitment briefings offline.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .agents.advisory_queue import generate_advisory_actions
from .analytics.engine import AnalyticsEngine, AnalyticsResult
from .airtable import AirtableClient, CANONICAL_TABLES, ingest_snapshot, load_snapshot as load_airtable_snapshot
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


def _load_dotenv(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE entries without adding a runtime dependency.

    Existing environment variables always win. Values are never printed or
    included in snapshots; this only makes the documented ``.env`` workflow
    work for the command-line entry point.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key in {"AIRTABLE_API_KEY", "AIRTABLE_BASE_ID", "AIRTABLE_API_URL", "AIRTABLE_TABLES", "AIRTABLE_CACHE_DIR", "AIRTABLE_SNAPSHOT_PATH"}:
            os.environ.setdefault(key, value)


def load_live_snapshot(
    *,
    output_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
    tables: tuple[str, ...] = CANONICAL_TABLES,
    refresh: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch current Airtable data with read-only GETs and cache one snapshot."""
    _load_dotenv()
    snapshot_path = Path(
        output_path or os.getenv("AIRTABLE_SNAPSHOT_PATH", "data/raw/airtable_snapshot.json")
    )
    if not refresh and snapshot_path.is_file():
        return load_airtable_snapshot(snapshot_path)
    configured_tables = tuple(
        item.strip() for item in os.getenv("AIRTABLE_TABLES", "").split(",") if item.strip()
    )
    requested_tables = configured_tables or tables
    client = AirtableClient(
        base_url=os.getenv("AIRTABLE_API_URL", "https://api.airtable.com/v0"),
        cache_dir=cache_dir or os.getenv("AIRTABLE_CACHE_DIR"),
    )
    return ingest_snapshot(
        client,
        tables=requested_tables,
        output_path=snapshot_path,
        use_cache=not refresh,
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
    live: bool = False,
    cache_dir: str | Path | None = None,
    refresh: bool = True,
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
    if live:
        _load_dotenv()
        tables = load_live_snapshot(
            output_path=None,
            cache_dir=cache_dir,
            refresh=refresh,
        )
    elif isinstance(snapshot, (str, Path)) or snapshot is None:
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
        "--live",
        action="store_true",
        help="Fetch current Airtable tables using AIRTABLE_API_KEY and AIRTABLE_BASE_ID",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Per-table Airtable response cache directory",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Replay per-table cache files in live mode instead of fetching current pages",
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
        if args.live and args.snapshot is not None:
            parser.error("provide either SNAPSHOT or --live, not both")
        results = run_pipeline(
            snapshot=args.snapshot,
            output_dir=args.output_dir,
            as_of=args.as_of,
            include_cost_appendix=not args.no_cost_appendix,
            live=args.live,
            cache_dir=args.cache_dir,
            refresh=not args.no_refresh,
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
