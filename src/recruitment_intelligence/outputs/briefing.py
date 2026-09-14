"""Executive daily briefing generator (M5 / Feature 29).

Synthesizes validated metrics (Q1–Q4), data quality audits and sensitivity (Q5),
prioritized advisory candidate action queues, and strictly isolated cost research into
an immutable Briefing domain contract.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..agents.advisory_queue import generate_advisory_actions
from ..analytics.engine import AnalyticsEngine, AnalyticsResult
from ..domain import (
    Briefing,
    CandidateRecommendation,
    Confidence,
    EvidenceReference,
    Finding,
    MetricClaim,
    Severity,
)
from ..quality.auditor import QualityAuditResult, run_quality_audit
from ..quality.sensitivity import SensitivityReport, quantify_sensitivity
from .cost_appendix import build_cost_research_appendix
from .renderers import write_artifacts


def generate_executive_briefing(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    analytics_result: AnalyticsResult | None = None,
    quality_result: QualityAuditResult | None = None,
    sensitivity_result: SensitivityReport | None = None,
    candidate_actions: Sequence[CandidateRecommendation] | None = None,
    period: str = "daily",
    as_of: date | datetime | str | None = None,
    include_cost_appendix: bool = True,
    custom_cost_appendix: str | None = None,
    briefing_id: str | None = None,
) -> Briefing:
    """Synthesize complete recruitment intelligence into an executive Briefing contract."""
    # 1. Analytics Pass (Q1–Q4)
    if analytics_result is None:
        analytics_result = AnalyticsEngine(tables, as_of=as_of).analyze()

    # 2. Quality Audit Pass (Q5)
    if quality_result is None:
        quality_result = run_quality_audit(tables)

    # 3. Sensitivity Analysis Pass (Q5)
    if sensitivity_result is None:
        sensitivity_result = quantify_sensitivity(tables, audit_result=quality_result, as_of=as_of)

    # 4. Advisory Candidate Actions
    if candidate_actions is None:
        candidate_actions = generate_advisory_actions(tables, as_of=as_of)

    # 5. External Cost Appendix (strictly isolated)
    cost_appendix: str | None = None
    if include_cost_appendix:
        cost_appendix = custom_cost_appendix or build_cost_research_appendix()

    # 6. Synthesize Executive Takeaways
    # Pin generated metadata to the analysis reference date when supplied so
    # two runs over the same snapshot produce byte-identical artifacts.
    if as_of is not None:
        if isinstance(as_of, datetime):
            reference = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
        elif isinstance(as_of, date):
            reference = datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc)
        else:
            reference = datetime.fromisoformat(str(as_of).strip().replace("Z", "+00:00"))
            if reference.tzinfo is None:
                reference = reference.replace(tzinfo=timezone.utc)
        reference = reference.astimezone(timezone.utc)
        now_iso = reference.isoformat()
        b_id = briefing_id or f"briefing-{reference.strftime('%Y%m%d')}"
    else:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        b_id = briefing_id or f"briefing-{now.strftime('%Y%m%d-%H%M%S')}"

    total_records = sum(analytics_result.table_counts.values())
    top_source_claim = analytics_result.get_claim("top_recruiting_source")
    top_source_raw = str(top_source_claim.value if top_source_claim and top_source_claim.value is not None else "")
    has_valid_top_source = bool(top_source_raw and not top_source_raw.startswith("Unknown"))
    top_source = top_source_raw if has_valid_top_source else "Unknown — insufficient evidence"

    oar_claim = analytics_result.get_claim("offer_acceptance_rate")
    oar_val = float(oar_claim.value) if oar_claim and isinstance(oar_claim.value, (int, float)) else None

    bn_claim = analytics_result.get_claim("funnel_bottleneck_stage")
    bn_raw = str(
        bn_claim.value
        if bn_claim and bn_claim.value is not None
        else (analytics_result.funnel_metrics.get("bottleneck", "") if isinstance(analytics_result.funnel_metrics, Mapping) else "")
    )
    has_valid_bottleneck = bool(bn_raw and not bn_raw.lower().startswith("unknown") and bn_raw.lower() != "none")
    bottleneck = bn_raw if has_valid_bottleneck else "Unknown — insufficient evidence"

    stalled_claim = analytics_result.get_claim("stalled_applications_count")
    stalled_count = int(stalled_claim.value if stalled_claim and isinstance(stalled_claim.value, (int, float)) else len(analytics_result.stalled_applications))

    # What changed
    what_changed: list[str] = [
        f"Profiled {total_records} records across {len(analytics_result.table_counts)} recruitment tables.",
    ]
    if has_valid_top_source:
        what_changed.append(f"Leading source: '{top_source}' ranked top by hire conversion yield.")
    else:
        what_changed.append("Leading recruiting source could not be determined due to insufficient evidence.")

    if oar_val is not None:
        what_changed.append(f"Offer acceptance rate stands at {oar_val:.1%}.")

    if has_valid_bottleneck:
        what_changed.append(f"Primary hiring funnel bottleneck identified at '{bottleneck}'.")
    else:
        what_changed.append("Funnel bottleneck could not be determined due to insufficient transition evidence.")

    # Urgent items
    urgent_items: list[str] = []
    if total_records == 0:
        urgent_items.append("Zero recruitment records found in snapshot; insufficient data for pipeline analytics.")

    if stalled_count > 0:
        urgent_items.append(
            f"{stalled_count} active application(s) stalled for >= 14 days requiring prompt founder/hiring manager review."
        )

    high_sev_quality = quality_result.findings_by_severity(Severity.HIGH) + quality_result.findings_by_severity(Severity.CRITICAL)
    if high_sev_quality:
        urgent_items.append(
            f"{len(high_sev_quality)} high/critical data quality issue(s) detected that may distort conversion metrics."
        )

    if sensitivity_result.high_sensitivity_scenarios:
        urgent_items.append(
            f"Metric sensitivity alert: anomaly exclusions cause rank inversions or bottleneck shift in: "
            f"{', '.join(sensitivity_result.high_sensitivity_scenarios)}."
        )

    if not urgent_items:
        urgent_items.append("Pipeline operations operating within normal parameters; no critical blocks.")

    # Next actions
    next_actions: list[str] = [
        "Review prioritized advisory candidate action queue with hiring owners (no automated rejections).",
    ]
    if stalled_count > 0:
        next_actions.append(f"Triage {stalled_count} stalled application(s) to unblock candidates or close stale processes.")
    if high_sev_quality:
        next_actions.append("Audit and repair broken foreign keys and timestamp contradictions in Airtable.")
    if has_valid_bottleneck:
        next_actions.append(f"Address drop-off attrition at the '{bottleneck}' transition.")

    # Combine Findings: Analytical findings + Quality findings + Sensitivity findings
    all_findings: list[Finding] = []

    # Analytic findings
    evidence_deterministic = (EvidenceReference(source="analytics.engine", method="deterministic_python"),)
    if has_valid_top_source:
        src_data = analytics_result.source_metrics.get(top_source, {}) if isinstance(analytics_result.source_metrics, Mapping) else {}
        rec_src = f"Maintain pipeline volume in {top_source} while evaluating candidate quality."
        all_findings.append(Finding(
            finding_id="find-top-source",
            category="source_effectiveness",
            title=f"Top Recruiting Source: {top_source}",
            observed_fact=f"{top_source} produced {src_data.get('hires', 0)} hire(s) from {src_data.get('applications', 0)} application(s) ({src_data.get('hire_conversion_rate', 0.0):.1%} conversion).",
            severity=Severity.LOW,
            confidence=Confidence(src_data.get("confidence", "medium")),
            evidence=evidence_deterministic,
            interpretation="Observed funnel performance. Does not account for external agency placement fees.",
            recommendation=rec_src,
            recommendations=(rec_src,),
        ))

    if oar_val is not None:
        rec_oar = "Review unaccepted offers for competitive compensation and candidate objections."
        all_findings.append(Finding(
            finding_id="find-offer-acceptance",
            category="offer_acceptance",
            title="Formal Offer Acceptance Rate",
            observed_fact=f"Accepted {analytics_result.offer_metrics.get('accepted', 0)} of {analytics_result.offer_metrics.get('offers', 0)} formal offers ({oar_val:.1%}).",
            severity=Severity.LOW if oar_val >= 0.70 else Severity.MEDIUM,
            confidence=Confidence(analytics_result.offer_metrics.get("confidence", "medium")),
            evidence=evidence_deterministic,
            interpretation="Measures closing effectiveness. Denominator excludes draft/rescinded offers.",
            recommendation=rec_oar,
            recommendations=(rec_oar,),
        ))

    if has_valid_bottleneck:
        rec_bn = f"Investigate evaluation criteria and candidate drop-off reasons in {bottleneck}."
        all_findings.append(Finding(
            finding_id="find-funnel-bottleneck",
            category="funnel_diagnosis",
            title=f"Funnel Bottleneck: {bottleneck}",
            observed_fact=f"Highest stage-to-stage attrition occurs at the '{bottleneck}' transition.",
            severity=Severity.MEDIUM,
            confidence=Confidence.HIGH if total_records >= 20 else Confidence.MEDIUM,
            evidence=evidence_deterministic,
            interpretation="Stage with greatest drop-off rate between sequential recruitment milestones.",
            recommendation=rec_bn,
            recommendations=(rec_bn,),
        ))

    # Add sensitivity findings
    all_findings.extend(sensitivity_result.findings)

    # Executive Summary Text
    oar_text = f"{oar_val:.1%}" if oar_val is not None else "N/A"
    exec_summary = (
        f"Recruitment Intelligence Daily Briefing ({period}): Profiled {total_records} records across "
        f"{len(analytics_result.table_counts)} tables. Top recruiting source is '{top_source}'. "
        f"Offer acceptance rate is {oar_text}. Primary bottleneck is '{bottleneck}'. "
        f"Found {stalled_count} stalled application(s) requiring review and {len(quality_result.findings)} data quality finding(s)."
    )

    # Overall confidence
    overall_conf = quality_result.confidence
    if overall_conf == Confidence.INSUFFICIENT or total_records == 0:
        overall_conf = Confidence.INSUFFICIENT
    elif high_sev_quality or sensitivity_result.high_sensitivity_scenarios:
        overall_conf = Confidence.LOW
    elif overall_conf == Confidence.HIGH and total_records >= 20:
        overall_conf = Confidence.HIGH
    else:
        overall_conf = Confidence.MEDIUM

    return Briefing(
        briefing_id=b_id,
        generated_at=now_iso,
        period=period,
        period_start=now_iso[:10],
        period_end=now_iso[:10],
        executive_summary=exec_summary,
        what_changed=tuple(what_changed),
        urgent_items=tuple(urgent_items),
        findings=tuple(all_findings),
        candidate_actions=tuple(candidate_actions),
        quality_warnings=tuple(quality_result.findings),
        next_actions=tuple(next_actions),
        confidence=overall_conf,
        metrics=analytics_result.claims,
        cost_appendix=cost_appendix,
    )


def produce_daily_briefing(
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
    output_dir: str | Path = "outputs",
    *,
    as_of: date | datetime | str | None = None,
    include_cost_appendix: bool = True,
    period: str = "daily",
) -> tuple[Briefing, dict[str, Path]]:
    """Generate executive daily briefing and persist all output artifacts.

    Generates:
    - outputs/briefing.md
    - outputs/briefing.html
    - outputs/briefing.json
    - outputs/findings.md
    - outputs/findings.csv
    - outputs/memo.md
    - outputs/candidate_actions.json
    """
    quality_result = run_quality_audit(tables)
    analytics_result = AnalyticsEngine(tables, as_of=as_of).analyze()
    sensitivity_result = quantify_sensitivity(tables, audit_result=quality_result, as_of=as_of)
    candidate_actions = generate_advisory_actions(tables, as_of=as_of)

    briefing = generate_executive_briefing(
        tables,
        analytics_result=analytics_result,
        quality_result=quality_result,
        sensitivity_result=sensitivity_result,
        candidate_actions=candidate_actions,
        period=period,
        as_of=as_of,
        include_cost_appendix=include_cost_appendix,
    )

    written_paths = write_artifacts(
        output_dir,
        findings=briefing.findings,
        quality_warnings=briefing.quality_warnings,
        briefing=briefing,
    )
    return briefing, written_paths
