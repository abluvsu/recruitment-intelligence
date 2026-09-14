"""Counterfactual metric sensitivity analysis engine (Q5).

Quantifies the sensitivity and distortion of executive recruitment metrics (recruiting source
ranking, hire conversion, offer acceptance rate, funnel bottleneck migration) when data quality
anomalies are excluded. All outputs are deterministic and wrapped in typed MetricClaim and Finding
domain contracts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

from ..analytics.engine import AnalyticsEngine, AnalyticsResult
from ..analytics.metrics import source_effectiveness
from ..domain import (
    Confidence,
    EvidenceReference,
    Finding,
    MetricClaim,
    Severity,
)
from ..domain.models import Serializable
from .checks import (
    Record,
    Tables,
    _empty,
    _key,
    _record_id,
    _text,
    _value,
    run_quality_checks,
)


@dataclass(frozen=True, slots=True)
class MetricSensitivityDelta(Serializable):
    """Represents counterfactual shift for an individual metric."""
    metric_name: str
    baseline_value: Any
    counterfactual_value: Any
    absolute_delta: float | None = None
    relative_delta: float | None = None
    is_sensitive: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ScenarioEvaluation(Serializable):
    """Evaluation of a specific anomaly exclusion scenario."""
    scenario_id: str
    scenario_name: str
    excluded_record_count: int
    excluded_record_ids: tuple[str, ...]

    # Q2 Sensitivity
    top_source_baseline: str
    top_source_counterfactual: str
    rank_inversion: bool
    source_conversion_deltas: Mapping[str, float]
    new_effort_sinks: tuple[str, ...]
    resolved_effort_sinks: tuple[str, ...]

    # Q3 Sensitivity
    offer_acceptance_baseline: float | None
    offer_acceptance_counterfactual: float | None
    offer_acceptance_delta: float | None

    # Q4 Sensitivity
    bottleneck_baseline: str
    bottleneck_counterfactual: str
    bottleneck_shifted: bool
    funnel_stage_deltas: Mapping[str, float]

    # Typed Contracts
    claims: tuple[MetricClaim, ...] = ()
    findings: tuple[Finding, ...] = ()


@dataclass(frozen=True, slots=True)
class SensitivityReport(Serializable):
    """Comprehensive multi-scenario sensitivity report (Q5)."""
    baseline_top_source: str
    baseline_offer_acceptance_rate: float | None
    baseline_bottleneck: str
    scenarios: Mapping[str, ScenarioEvaluation]
    claims: tuple[MetricClaim, ...]
    findings: tuple[Finding, ...]
    high_sensitivity_scenarios: tuple[str, ...]


def filter_tables_by_exclusions(tables: Tables, excluded_ids: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """Deterministically filter snapshot tables, omitting records whose IDs match excluded_ids."""
    excl = {str(item).strip() for item in excluded_ids if str(item).strip()}
    filtered: dict[str, list[dict[str, Any]]] = {}
    for table_name, rows in tables.items():
        filtered[table_name] = [
            dict(row) for i, row in enumerate(rows)
            if _record_id(row, str(table_name), i) not in excl
            and str(row.get("id", "")).strip() not in excl
            and str(row.get("record_id", "")).strip() not in excl
        ]
    return filtered


def build_exclusion_scenarios(
    tables: Tables,
    issues: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Build standard anomaly exclusion scenarios from quality audit issues."""
    if issues is None:
        report = run_quality_checks(tables)
        issues = report.get("issues", [])

    by_check: dict[str, set[str]] = {}
    all_anomalies: set[str] = set()

    for issue in issues:
        check = str(issue.get("check", "unknown"))
        recs = {str(r).strip() for r in issue.get("affected_records", []) if str(r).strip()}
        by_check.setdefault(check, set()).update(recs)
        all_anomalies.update(recs)

    scenarios: dict[str, tuple[str, ...]] = {}

    if all_anomalies:
        scenarios["exclude_all_anomalies"] = tuple(sorted(all_anomalies))

    check_mapping = {
        "orphan_link": "exclude_orphans",
        "chronology_error": "exclude_chronology_errors",
        "status_inconsistency": "exclude_status_contradictions",
        "duplicate_record": "exclude_duplicates",
        "invalid_date": "exclude_invalid_dates",
        "source_taxonomy": "exclude_source_taxonomy",
        "missing_value": "exclude_missing_values",
        "transitive_orphan": "exclude_transitive_orphans",
    }

    for check_key, scenario_name in check_mapping.items():
        recs = by_check.get(check_key, set())
        if recs:
            scenarios[scenario_name] = tuple(sorted(recs))

    return scenarios


def _quantify_scenario_evaluation(
    scenario_id: str,
    scenario_name: str,
    excluded_ids: Sequence[str],
    tables: Tables,
    baseline_result: AnalyticsResult,
    as_of: date | datetime | str | None = None,
) -> ScenarioEvaluation:
    """Evaluate one counterfactual scenario against baseline analytics."""
    filtered_tables = filter_tables_by_exclusions(tables, excluded_ids)
    engine = AnalyticsEngine(filtered_tables, as_of=as_of)
    cf_result = engine.analyze()

    # Baseline extractions
    base_top_claim = baseline_result.get_claim("top_recruiting_source")
    top_source_baseline = str(base_top_claim.value if base_top_claim else "Unknown — insufficient evidence")

    base_oar_claim = baseline_result.get_claim("offer_acceptance_rate")
    base_oar: float | None = None
    if base_oar_claim and isinstance(base_oar_claim.value, (int, float)):
        base_oar = float(base_oar_claim.value)

    base_bn_claim = baseline_result.get_claim("funnel_bottleneck")
    bottleneck_baseline = str(base_bn_claim.value if base_bn_claim else baseline_result.funnel_metrics.get("bottleneck", "none"))

    base_srcs = baseline_result.source_metrics.get("sources", baseline_result.source_metrics)
    base_src_conv = {s: data.get("hire_conversion_rate", 0.0) for s, data in base_srcs.items() if isinstance(data, Mapping)}
    base_sinks = tuple(sorted(s for s, data in base_srcs.items() if isinstance(data, Mapping) and data.get("is_effort_sink")))
    base_trans = baseline_result.funnel_metrics.get("transitions", {})

    # Counterfactual extractions
    cf_top_claim = cf_result.get_claim("top_recruiting_source")
    top_source_cf = str(cf_top_claim.value if cf_top_claim else "Unknown — insufficient evidence")
    rank_inversion = (top_source_baseline != top_source_cf)

    cf_oar_claim = cf_result.get_claim("offer_acceptance_rate")
    cf_oar: float | None = None
    if cf_oar_claim and isinstance(cf_oar_claim.value, (int, float)):
        cf_oar = float(cf_oar_claim.value)

    oar_delta: float | None = None
    if base_oar is not None and cf_oar is not None:
        oar_delta = round(cf_oar - base_oar, 4)

    cf_bn_claim = cf_result.get_claim("funnel_bottleneck")
    bottleneck_cf = str(cf_bn_claim.value if cf_bn_claim else cf_result.funnel_metrics.get("bottleneck", "none"))
    bottleneck_shifted = (bottleneck_baseline != bottleneck_cf)

    cf_srcs = cf_result.source_metrics.get("sources", cf_result.source_metrics)
    cf_src_conv = {s: data.get("hire_conversion_rate", 0.0) for s, data in cf_srcs.items() if isinstance(data, Mapping)}
    cf_sinks = tuple(sorted(s for s, data in cf_srcs.items() if isinstance(data, Mapping) and data.get("is_effort_sink")))
    new_sinks = tuple(sorted(s for s in cf_sinks if s not in base_sinks))
    resolved_sinks = tuple(sorted(s for s in base_sinks if s not in cf_sinks))

    all_sources = set(base_src_conv) | set(cf_src_conv)
    source_deltas = {
        s: round(cf_src_conv.get(s, 0.0) - base_src_conv.get(s, 0.0), 4)
        for s in sorted(all_sources)
    }

    cf_trans = cf_result.funnel_metrics.get("transitions", {})
    all_stages = set(base_trans) | set(cf_trans)
    stage_deltas = {
        st: round(cf_trans.get(st, 0.0) - base_trans.get(st, 0.0), 4)
        for st in sorted(all_stages)
    }

    # Generate typed MetricClaims
    claims: list[MetricClaim] = []
    excl_tuple = tuple(sorted({str(i).strip() for i in excluded_ids if str(i).strip()}))

    evidence_ref = EvidenceReference(
        source="counterfactual_sensitivity",
        table=None,
        record_ids=excl_tuple,
        method=f"exclusion_{scenario_id}",
        caveats=(f"Excluded {len(excl_tuple)} record(s) under scenario '{scenario_name}'.",),
    )

    claims.append(MetricClaim(
        metric=f"sensitivity_{scenario_id}_rank_inversion",
        value="True" if rank_inversion else "False",
        confidence=Confidence.HIGH,
        evidence=(evidence_ref,),
        caveats=(f"Baseline: {top_source_baseline}, Counterfactual: {top_source_cf}",),
    ))

    if oar_delta is not None:
        claims.append(MetricClaim(
            metric=f"sensitivity_{scenario_id}_offer_acceptance_delta",
            value=oar_delta,
            confidence=Confidence.HIGH,
            unit="fraction",
            evidence=(evidence_ref,),
            caveats=(f"Baseline: {base_oar:.4f}, Counterfactual: {cf_oar:.4f}",),
        ))

    claims.append(MetricClaim(
        metric=f"sensitivity_{scenario_id}_bottleneck_shifted",
        value="True" if bottleneck_shifted else "False",
        confidence=Confidence.HIGH,
        evidence=(evidence_ref,),
        caveats=(f"Baseline: {bottleneck_baseline}, Counterfactual: {bottleneck_cf}",),
    ))

    # Generate typed Findings
    findings: list[Finding] = []

    if rank_inversion:
        rec_rank = f"Verify source attribution for '{top_source_baseline}' before committing recruiting budget."
        interp_rank = "Relying on raw un-audited data would lead to misallocating recruiting budget."
        findings.append(Finding(
            finding_id=f"sens-rank-{scenario_id}",
            category="metric_sensitivity",
            title=f"Source Ranking Inversion under {scenario_name}",
            observed_fact=(
                f"Top recruiting source flips from '{top_source_baseline}' to '{top_source_cf}' "
                f"when {scenario_name} anomalies ({len(excl_tuple)} records) are excluded."
            ),
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
            evidence=(evidence_ref,),
            affected_records=excl_tuple,
            recommendation=rec_rank,
            recommendations=(rec_rank,),
            description=(
                f"Excluding data quality anomalies in {scenario_name} inverts the top-performing recruiting "
                f"source from '{top_source_baseline}' to '{top_source_cf}'."
            ),
            interpretation=interp_rank,
        ))

    if oar_delta is not None and abs(oar_delta) >= 0.05:
        sev = Severity.HIGH if abs(oar_delta) >= 0.15 else Severity.MEDIUM
        rec_oar = "Resolve offer table data anomalies before evaluating compensation or closing competitiveness."
        interp_oar = "Data quality defects create an inaccurate signal of offer competitiveness."
        findings.append(Finding(
            finding_id=f"sens-offer-{scenario_id}",
            category="metric_sensitivity",
            title=f"Offer Acceptance Rate Distortion under {scenario_name}",
            observed_fact=(
                f"Offer acceptance rate shifts from {base_oar:.1%} to {cf_oar:.1%} "
                f"(delta: {oar_delta:+.1%}) when {scenario_name} anomalies ({len(excl_tuple)} records) are excluded."
            ),
            severity=sev,
            confidence=Confidence.HIGH,
            evidence=(evidence_ref,),
            affected_records=excl_tuple,
            recommendation=rec_oar,
            recommendations=(rec_oar,),
            description=f"Offer acceptance rate is materially distorted by {scenario_name} anomalies.",
            interpretation=interp_oar,
        ))

    if bottleneck_shifted:
        rec_bn = f"Address funnel data anomalies before reorganizing recruiter screening or interviewing stages."
        interp_bn = "Executive interventions aimed at the baseline bottleneck may target phantom issues."
        findings.append(Finding(
            finding_id=f"sens-funnel-{scenario_id}",
            category="metric_sensitivity",
            title=f"Funnel Bottleneck Migration under {scenario_name}",
            observed_fact=(
                f"Primary funnel bottleneck migrates from '{bottleneck_baseline}' to '{bottleneck_cf}' "
                f"when {scenario_name} anomalies are excluded."
            ),
            severity=Severity.HIGH,
            confidence=Confidence.HIGH,
            evidence=(evidence_ref,),
            affected_records=excl_tuple,
            recommendation=rec_bn,
            recommendations=(rec_bn,),
            description=f"Funnel throughput bottleneck shifts from '{bottleneck_baseline}' to '{bottleneck_cf}'.",
            interpretation=interp_bn,
        ))

    return ScenarioEvaluation(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        excluded_record_count=len(excl_tuple),
        excluded_record_ids=excl_tuple,
        top_source_baseline=top_source_baseline,
        top_source_counterfactual=top_source_cf,
        rank_inversion=rank_inversion,
        source_conversion_deltas=source_deltas,
        new_effort_sinks=new_sinks,
        resolved_effort_sinks=resolved_sinks,
        offer_acceptance_baseline=base_oar,
        offer_acceptance_counterfactual=cf_oar,
        offer_acceptance_delta=oar_delta,
        bottleneck_baseline=bottleneck_baseline,
        bottleneck_counterfactual=bottleneck_cf,
        bottleneck_shifted=bottleneck_shifted,
        funnel_stage_deltas=stage_deltas,
        claims=tuple(claims),
        findings=tuple(findings),
    )


def quantify_scenario(
    scenario_id: str,
    scenario_name: str,
    excluded_ids: Sequence[str],
    tables: Tables,
    baseline_result: AnalyticsResult | None = None,
    as_of: date | datetime | str | None = None,
) -> ScenarioEvaluation:
    """Evaluate one counterfactual scenario against baseline analytics."""
    if baseline_result is None:
        baseline_result = AnalyticsEngine(tables, as_of=as_of).analyze()
    return _quantify_scenario_evaluation(
        scenario_id=scenario_id,
        scenario_name=scenario_name,
        excluded_ids=excluded_ids,
        tables=tables,
        baseline_result=baseline_result,
        as_of=as_of,
    )


def quantify_sensitivity(
    tables: Tables,
    issues: Sequence[Mapping[str, Any]] | None = None,
    exclusions: Mapping[str, Iterable[str]] | None = None,
    as_of: date | datetime | str | None = None,
    audit_result: Any | None = None,
) -> SensitivityReport:
    """Run comprehensive counterfactual sensitivity quantification across all scenarios."""
    if issues is None and audit_result is not None:
        issues = getattr(audit_result, "issues", None)
    baseline_engine = AnalyticsEngine(tables, as_of=as_of)
    baseline_result = baseline_engine.analyze()

    base_top_claim = baseline_result.get_claim("top_recruiting_source")
    top_source_baseline = str(base_top_claim.value if base_top_claim else "Unknown — insufficient evidence")

    base_oar_claim = baseline_result.get_claim("offer_acceptance_rate")
    base_oar: float | None = None
    if base_oar_claim and isinstance(base_oar_claim.value, (int, float)):
        base_oar = float(base_oar_claim.value)

    base_bn_claim = baseline_result.get_claim("funnel_bottleneck")
    bottleneck_baseline = str(base_bn_claim.value if base_bn_claim else baseline_result.funnel_metrics.get("bottleneck", "none"))

    # Determine scenarios to evaluate
    scenarios_to_run: dict[str, tuple[str, ...]] = {}

    if exclusions:
        for name, ids in exclusions.items():
            scenarios_to_run[str(name)] = tuple(sorted({str(i).strip() for i in ids if str(i).strip()}))
    else:
        scenarios_to_run = build_exclusion_scenarios(tables, issues)

    evaluated_scenarios: dict[str, ScenarioEvaluation] = {}
    all_claims: list[MetricClaim] = []
    all_findings: list[Finding] = []
    high_sensitivity_scenarios: list[str] = []

    for sc_id, excl_ids in sorted(scenarios_to_run.items()):
        sc_name = sc_id.replace("exclude_", "").replace("_", " ").title()
        eval_result = _quantify_scenario_evaluation(
            scenario_id=sc_id,
            scenario_name=sc_name,
            excluded_ids=excl_ids,
            tables=tables,
            baseline_result=baseline_result,
            as_of=as_of,
        )
        evaluated_scenarios[sc_id] = eval_result
        all_claims.extend(eval_result.claims)
        all_findings.extend(eval_result.findings)

        if (
            eval_result.rank_inversion
            or eval_result.bottleneck_shifted
            or (eval_result.offer_acceptance_delta is not None and abs(eval_result.offer_acceptance_delta) >= 0.10)
        ):
            high_sensitivity_scenarios.append(sc_id)

    return SensitivityReport(
        baseline_top_source=top_source_baseline,
        baseline_offer_acceptance_rate=base_oar,
        baseline_bottleneck=bottleneck_baseline,
        scenarios=evaluated_scenarios,
        claims=tuple(all_claims),
        findings=tuple(all_findings),
        high_sensitivity_scenarios=tuple(sorted(high_sensitivity_scenarios)),
    )


def sensitivity_analysis(
    tables: Tables,
    exclusions: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, Any]:
    """Backward-compatible functional adapter returning nested dictionary."""
    baseline = source_effectiveness(tables)
    scenarios: dict[str, Any] = {}
    for name, ids in (exclusions or {}).items():
        filtered = filter_tables_by_exclusions(tables, ids)
        scenarios[str(name)] = source_effectiveness(filtered)
    return {"baseline": baseline, "scenarios": scenarios}
