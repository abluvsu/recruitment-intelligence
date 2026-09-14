"""Deterministic recruitment analytics engine.

Orchestrates deterministic recruitment analytics answering executive questions
Q1–Q4, wrapping all calculations into typed MetricClaim instances with structured
EvidenceReference objects, confidence scoring, and standardized fallbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Sequence

from ..domain import (
    Confidence,
    EvidenceReference,
    MetricClaim,
)
from ..domain.models import Serializable
from .metrics import (
    _date,
    _flatten_record,
    _flatten_tables,
    _id,
    _linked_id,
    _rows,
    _status,
    _text,
    _value,
    aging,
    funnel_bottleneck,
    funnel_stage_conversions,
    funnel_transitions,
    offer_acceptance_rate,
    pipeline_effort_sinks,
    sensitivity_analysis,
    source_department_segmentation,
    source_effectiveness,
    stalled_applications,
    table_counts,
)

CANONICAL_TABLES: tuple[str, ...] = (
    "Departments",
    "People",
    "Job Openings",
    "Candidates",
    "Applications",
    "Interviews",
    "Offers",
    "Findings",
)

INSUFFICIENT_FALLBACK = "Unknown — insufficient evidence"


def _clean_ids(records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Extract non-empty sorted record IDs for evidence references."""
    ids: list[str] = []
    for r in records:
        rid = _id(r)
        if rid:
            ids.append(rid)
    return tuple(sorted(ids))


def _confidence_bucket(n: int) -> Confidence:
    if n >= 30:
        return Confidence.HIGH
    if n >= 10:
        return Confidence.MEDIUM
    if n >= 1:
        return Confidence.LOW
    return Confidence.INSUFFICIENT


@dataclass(frozen=True, slots=True)
class AnalyticsResult(Serializable):
    claims: tuple[MetricClaim, ...]
    table_counts: Mapping[str, int]
    source_metrics: Mapping[str, Any]
    offer_metrics: Mapping[str, Any]
    funnel_metrics: Mapping[str, Any]
    aging_records: tuple[Mapping[str, Any], ...]
    stalled_applications: tuple[Mapping[str, Any], ...]

    def get_claim(self, name: str) -> MetricClaim | None:
        for claim in self.claims:
            if claim.name == name or claim.metric == name:
                return claim
        return None

    def claims_for_question(self, question: str) -> tuple[MetricClaim, ...]:
        q = question.upper().strip()
        if q == "Q1":
            return tuple(
                c for c in self.claims
                if c.name.startswith("table_") or c.name == "total_snapshot_records" or c.name == "table_row_counts"
            )
        if q == "Q2":
            return tuple(
                c for c in self.claims
                if c.name.startswith("source_") or c.name in ("top_recruiting_source", "recruiting_effort_sinks", "source_effectiveness")
            )
        if q == "Q3":
            return tuple(c for c in self.claims if c.name == "offer_acceptance_rate")
        if q == "Q4":
            return tuple(
                c for c in self.claims
                if c.name.startswith("funnel_") or c.name.endswith("_application_age_days") or c.name == "stalled_applications_count"
            )
        return ()


class AnalyticsEngine:
    """Pure deterministic recruitment analytics engine returning typed MetricClaims."""

    def __init__(
        self,
        snapshot: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]] | None = None,
        as_of: date | datetime | str | None = None,
    ) -> None:
        self._snapshot = _flatten_tables(snapshot) if snapshot is not None else None
        self.as_of = as_of

    def _get_tables(
        self,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if tables is not None:
            return _flatten_tables(tables)
        if self._snapshot is not None:
            return self._snapshot
        return {}

    def compute_table_counts(
        self,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]] | None = None,
    ) -> MetricClaim:
        """Q1: Return table row counts claim."""
        t = self._get_tables(tables)
        raw_counts = table_counts(t)
        all_counts = {table: len(t.get(table, [])) for table in CANONICAL_TABLES}
        for k, v in raw_counts.items():
            if k not in all_counts:
                all_counts[str(k)] = v
        total_records = sum(all_counts.values())

        all_ids: list[str] = []
        for rows in t.values():
            all_ids.extend(_clean_ids(rows))

        if total_records == 0:
            evidence = EvidenceReference(
                source="airtable_snapshot",
                table=None,
                method="table_counts",
                caveats=("Snapshot contains 0 records or no canonical tables.",),
            )
            return MetricClaim(
                metric="table_row_counts",
                value=INSUFFICIENT_FALLBACK,
                confidence=Confidence.INSUFFICIENT,
                unit="records",
                evidence=(evidence,),
                caveats=("Snapshot contains 0 records across canonical tables.",),
            )

        breakdown_str = ", ".join(f"{k}: {v}" for k, v in sorted(all_counts.items()))
        evidence = EvidenceReference(
            source="airtable_snapshot",
            record_ids=tuple(sorted(all_ids)[:100]),
            method="table_counts",
            caveats=(f"Table row counts: {breakdown_str}",),
        )
        return MetricClaim(
            metric="table_row_counts",
            value=total_records,
            confidence=_confidence_bucket(total_records),
            unit="records",
            evidence=(evidence,),
            caveats=(f"Total records: {total_records} across {len(all_counts)} profiled tables.",),
        )

    def compute_individual_table_counts(
        self,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[MetricClaim, ...]:
        """Q1: Return individual claims for each canonical table."""
        t = self._get_tables(tables)
        claims: list[MetricClaim] = []
        for table in CANONICAL_TABLES:
            rows = t.get(table, [])
            count = len(rows)
            ids = _clean_ids(rows)
            evidence = EvidenceReference(
                source="airtable_snapshot",
                table=table,
                record_ids=ids[:50],
                method="table_counts",
                caveats=("Table profiled from local snapshot.",) if count > 0 else ("Table absent or empty in snapshot.",),
            )
            claims.append(
                MetricClaim(
                    metric=f"table_record_count:{table}",
                    value=count,
                    confidence=_confidence_bucket(count),
                    unit="records",
                    evidence=(evidence,),
                )
            )
        return tuple(claims)

    def compute_source_effectiveness(
        self,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[MetricClaim, ...]:
        """Q2: Return source effectiveness claims, ranking vs effort, and sink detection."""
        t = self._get_tables(tables)
        apps = _rows(t, "Applications")
        if not apps:
            ref = EvidenceReference(
                source="airtable_snapshot",
                table="Applications",
                caveats=("No application records found.",),
            )
            return (
                MetricClaim(metric="source_effectiveness", value=INSUFFICIENT_FALLBACK, confidence=Confidence.INSUFFICIENT, evidence=(ref,)),
                MetricClaim(metric="top_recruiting_source", value=INSUFFICIENT_FALLBACK, confidence=Confidence.INSUFFICIENT, evidence=(ref,)),
                MetricClaim(metric="recruiting_effort_sinks", value=INSUFFICIENT_FALLBACK, confidence=Confidence.INSUFFICIENT, evidence=(ref,)),
            )

        sources = source_effectiveness(t)
        claims: list[MetricClaim] = []
        sinks: list[str] = []
        ranked_candidates: list[tuple[str, float, int, int]] = []

        for source, data in sources.items():
            n = data["applications"]
            hires = data["hires"]
            offers = data["offers"]
            interviews = data["interviews"]
            hire_rate = data["hire_conversion_rate"]
            offer_to_hire = data["offer_to_hire_rate"]
            effort_touches = data.get("effort_touches", interviews + offers)
            effort_yield = data.get("effort_yield", hires / effort_touches if effort_touches else 0.0)
            conf = Confidence(data["confidence"])

            source_app_ids = tuple(sorted(
                _id(a) for a in apps
                if (_text(_value(a, "source", "recruiting_source", "channel"), "Unknown") or "Unknown") == source and _id(a)
            ))

            evidence = EvidenceReference(
                source="airtable_snapshot",
                table="Applications",
                record_ids=source_app_ids[:50],
                filters={"source": source},
                method="source_effectiveness",
            )

            claims.append(
                MetricClaim(
                    metric=f"source_hire_conversion_rate:{source}",
                    value=hire_rate,
                    confidence=conf,
                    numerator=hires if hires <= n else None,
                    denominator=n if hires <= n else None,
                    unit="ratio",
                    evidence=(evidence,),
                )
            )

            if offers > 0:
                claims.append(
                    MetricClaim(
                        metric=f"source_offer_to_hire_rate:{source}",
                        value=offer_to_hire,
                        confidence=conf,
                        numerator=hires if hires <= offers else None,
                        denominator=offers if hires <= offers else None,
                        unit="ratio",
                        evidence=(evidence,),
                    )
                )

            claims.append(
                MetricClaim(
                    metric=f"source_effort_touches:{source}",
                    value=effort_touches,
                    confidence=conf,
                    unit="touches",
                    evidence=(evidence,),
                )
            )

            claims.append(
                MetricClaim(
                    metric=f"source_effort_yield:{source}",
                    value=effort_yield,
                    confidence=conf,
                    numerator=hires if effort_touches > 0 and hires <= effort_touches else None,
                    denominator=effort_touches if effort_touches > 0 and hires <= effort_touches else None,
                    unit="ratio",
                    evidence=(evidence,),
                )
            )

            if data.get("is_effort_sink", False):
                sinks.append(source)

            ranked_candidates.append((source, hire_rate, hires, effort_touches))

        # Rank sources: hire_conversion_rate DESC, hires DESC, effort_touches ASC
        ranked = sorted(ranked_candidates, key=lambda item: (-item[1], -item[2], item[3]))
        top_source = ranked[0][0] if ranked and ranked[0][2] > 0 else INSUFFICIENT_FALLBACK
        top_conf = Confidence(sources[top_source]["confidence"]) if top_source in sources else Confidence.INSUFFICIENT

        claims.append(
            MetricClaim(
                metric="top_recruiting_source",
                value=top_source,
                confidence=top_conf,
                evidence=(EvidenceReference(source="airtable_snapshot", table="Applications", method="source_effectiveness"),),
                caveats=("Ranked by ultimate hire conversion vs pipeline effort consumed.",),
            )
        )

        sinks_sorted = sorted(sinks, key=lambda s: (-sources[s]["effort_touches"], -sources[s]["applications"], s))
        sinks_value = ", ".join(sinks_sorted) if sinks_sorted else "None observed"
        claims.append(
            MetricClaim(
                metric="recruiting_effort_sinks",
                value=sinks_value,
                confidence=Confidence.MEDIUM if sinks else Confidence.LOW,
                evidence=(EvidenceReference(source="airtable_snapshot", table="Applications", method="source_effectiveness"),),
                caveats=("Sources that consume candidate or interview volume without producing hires (hires == 0 and (apps >= 2 or interviews >= 1)).",),
            )
        )

        return tuple(claims)

    def compute_offer_acceptance_rate(
        self,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]] | None = None,
    ) -> MetricClaim:
        """Q3: Return offer acceptance rate claim with explicit denominator justification."""
        t = self._get_tables(tables)
        raw = offer_acceptance_rate(t)
        total = raw["offers"]
        accepted = raw["accepted"]
        rate = raw["rate"]
        justification = raw.get(
            "denominator_justification",
            (
                "Denominator defined as total formal offers extended in the Offers table, "
                "excluding draft or rescinded offers. Numerator counts affirmative candidate "
                "acceptances (status in {accepted, offer_accepted, hired, joined} or is_accepted=True)."
            ),
        )
        offer_rows = _rows(t, "Offers")
        offer_ids = _clean_ids(offer_rows)

        if total == 0:
            return MetricClaim(
                metric="offer_acceptance_rate",
                value=INSUFFICIENT_FALLBACK,
                confidence=Confidence.INSUFFICIENT,
                numerator=None,
                denominator=None,
                unit="ratio",
                evidence=(EvidenceReference(
                    source="airtable_snapshot",
                    table="Offers",
                    method="offer_acceptance_rate",
                    caveats=(justification,),
                ),),
                caveats=(justification, "Zero formal offers found in Offers table."),
            )

        safe_num = min(accepted, total)
        return MetricClaim(
            metric="offer_acceptance_rate",
            value=rate,
            confidence=_confidence_bucket(total),
            numerator=safe_num,
            denominator=total,
            unit="ratio",
            evidence=(EvidenceReference(
                source="airtable_snapshot",
                table="Offers",
                record_ids=offer_ids[:50],
                method="offer_acceptance_rate",
                caveats=(justification,),
            ),),
            caveats=(justification,),
        )

    def compute_funnel_diagnosis(
        self,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]] | None = None,
        as_of: date | datetime | str | None = None,
    ) -> tuple[MetricClaim, ...]:
        """Q4: Return funnel conversion pass-through, aging, bottleneck, and stalled applications."""
        t = self._get_tables(tables)
        ref_date = as_of if as_of is not None else self.as_of
        apps = _rows(t, "Applications")
        app_ids = _clean_ids(apps)
        n_apps = len(apps)

        if n_apps == 0:
            ref = EvidenceReference(source="airtable_snapshot", table="Applications", caveats=("No applications found.",))
            return (
                MetricClaim(metric="funnel_bottleneck_stage", value=INSUFFICIENT_FALLBACK, confidence=Confidence.INSUFFICIENT, evidence=(ref,)),
                MetricClaim(metric="mean_application_age_days", value=INSUFFICIENT_FALLBACK, confidence=Confidence.INSUFFICIENT, evidence=(ref,)),
                MetricClaim(metric="median_application_age_days", value=INSUFFICIENT_FALLBACK, confidence=Confidence.INSUFFICIENT, evidence=(ref,)),
                MetricClaim(metric="max_application_age_days", value=INSUFFICIENT_FALLBACK, confidence=Confidence.INSUFFICIENT, evidence=(ref,)),
                MetricClaim(metric="stalled_applications_count", value=INSUFFICIENT_FALLBACK, confidence=Confidence.INSUFFICIENT, evidence=(ref,)),
            )

        claims: list[MetricClaim] = []
        conv = funnel_stage_conversions(t)

        for trans_key, trans_data in conv["transitions"].items():
            num = trans_data["numerator"]
            denom = trans_data["denominator"]
            rate = trans_data["conversion_rate"]
            conf = _confidence_bucket(denom)
            claims.append(
                MetricClaim(
                    metric=f"funnel_conversion:{trans_key}",
                    value=rate if denom > 0 else INSUFFICIENT_FALLBACK,
                    confidence=conf if denom > 0 else Confidence.INSUFFICIENT,
                    numerator=min(num, denom) if denom > 0 else None,
                    denominator=denom if denom > 0 else None,
                    unit="ratio",
                    evidence=(EvidenceReference(
                        source="airtable_snapshot",
                        table="Applications",
                        record_ids=app_ids[:50],
                        method="funnel_diagnosis",
                    ),),
                )
            )

        bottleneck = conv["bottleneck"]
        claims.append(
            MetricClaim(
                metric="funnel_bottleneck_stage",
                value=bottleneck,
                confidence=_confidence_bucket(n_apps),
                evidence=(EvidenceReference(
                    source="airtable_snapshot",
                    table="Applications",
                    method="funnel_diagnosis",
                ),),
                caveats=("Identified as stage transition with highest candidate attrition rate.",),
            )
        )

        app_ages = aging(t, as_of=ref_date)
        if app_ages:
            ages = [a["age_days"] for a in app_ages]
            mean_age = round(sum(ages) / len(ages), 1)
            sorted_ages = sorted(ages)
            median_age = sorted_ages[len(sorted_ages) // 2]
            max_age = max(ages)
            conf_age = _confidence_bucket(len(ages))

            claims.append(
                MetricClaim(
                    metric="mean_application_age_days",
                    value=mean_age,
                    confidence=conf_age,
                    unit="days",
                    evidence=(EvidenceReference(source="airtable_snapshot", table="Applications", method="aging"),),
                )
            )
            claims.append(
                MetricClaim(
                    metric="median_application_age_days",
                    value=median_age,
                    confidence=conf_age,
                    unit="days",
                    evidence=(EvidenceReference(source="airtable_snapshot", table="Applications", method="aging"),),
                )
            )
            claims.append(
                MetricClaim(
                    metric="max_application_age_days",
                    value=max_age,
                    confidence=conf_age,
                    unit="days",
                    evidence=(EvidenceReference(source="airtable_snapshot", table="Applications", method="aging"),),
                )
            )
        else:
            ref_age = EvidenceReference(
                source="airtable_snapshot",
                table="Applications",
                caveats=("No parseable application dates found.",),
            )
            claims.append(
                MetricClaim(
                    metric="mean_application_age_days",
                    value=INSUFFICIENT_FALLBACK,
                    confidence=Confidence.INSUFFICIENT,
                    unit="days",
                    evidence=(ref_age,),
                )
            )
            claims.append(
                MetricClaim(
                    metric="median_application_age_days",
                    value=INSUFFICIENT_FALLBACK,
                    confidence=Confidence.INSUFFICIENT,
                    unit="days",
                    evidence=(ref_age,),
                )
            )
            claims.append(
                MetricClaim(
                    metric="max_application_age_days",
                    value=INSUFFICIENT_FALLBACK,
                    confidence=Confidence.INSUFFICIENT,
                    unit="days",
                    evidence=(ref_age,),
                )
            )

        stalled = stalled_applications(t, threshold_days=14, as_of=ref_date)
        terminal = {"hired", "rejected", "withdrawn", "closed", "accepted"}
        active_count = sum(1 for a in apps if _status(a) not in terminal)
        stalled_count = len(stalled)
        stalled_ids = tuple(s["application_id"] for s in stalled if s.get("application_id"))

        claims.append(
            MetricClaim(
                metric="stalled_applications_count",
                value=stalled_count,
                confidence=_confidence_bucket(active_count),
                numerator=min(stalled_count, active_count) if active_count > 0 else None,
                denominator=active_count if active_count > 0 else None,
                unit="applications",
                evidence=(EvidenceReference(
                    source="airtable_snapshot",
                    table="Applications",
                    record_ids=stalled_ids[:50],
                    method="stalled_applications",
                    caveats=("Threshold: >= 14 days without activity for active applications.",),
                ),),
                caveats=("Active applications without activity for at least 14 days.",),
            )
        )

        return tuple(claims)

    def compute_all_claims(
        self,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]] | None = None,
        as_of: date | datetime | str | None = None,
    ) -> tuple[MetricClaim, ...]:
        """Aggregate all deterministic claims answering Q1–Q4."""
        t = self._get_tables(tables)
        q1_claim = self.compute_table_counts(t)
        q1_ind = self.compute_individual_table_counts(t)
        q2_claims = self.compute_source_effectiveness(t)
        q3_claim = self.compute_offer_acceptance_rate(t)
        q4_claims = self.compute_funnel_diagnosis(t, as_of=as_of)
        return (q1_claim,) + q1_ind + q2_claims + (q3_claim,) + q4_claims

    def analyze(
        self,
        tables: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]] | None = None,
        as_of: date | datetime | str | None = None,
    ) -> AnalyticsResult:
        """Run full analytics pass returning structured AnalyticsResult."""
        t = self._get_tables(tables)
        ref_date = as_of if as_of is not None else self.as_of
        all_claims = self.compute_all_claims(t, as_of=ref_date)
        raw_counts = table_counts(t)
        raw_sources = source_effectiveness(t)
        raw_offers = offer_acceptance_rate(t)
        raw_aging = tuple(aging(t, as_of=ref_date))
        raw_stalled = tuple(stalled_applications(t, as_of=ref_date))
        conv = funnel_stage_conversions(t)

        funnel_summary = {
            "transitions": {k: v["conversion_rate"] for k, v in conv["transitions"].items()},
            "bottleneck": conv["bottleneck"],
            "stages": conv["stages"],
        }

        return AnalyticsResult(
            claims=all_claims,
            table_counts=raw_counts,
            source_metrics=raw_sources,
            offer_metrics=raw_offers,
            funnel_metrics=funnel_summary,
            aging_records=raw_aging,
            stalled_applications=raw_stalled,
        )

    # Explorer aliases for maximum compatibility
    profile_volume_q1 = compute_individual_table_counts
    analyze_sources_q2 = compute_source_effectiveness
    analyze_offers_q3 = compute_offer_acceptance_rate
    diagnose_funnel_q4 = compute_funnel_diagnosis


def run_analytics(
    tables: Mapping[str, Sequence[Mapping[str, Any]]] | Sequence[Mapping[str, Any]],
    as_of: date | datetime | str | None = None,
) -> AnalyticsResult:
    """Convenience top-level runner for AnalyticsEngine."""
    return AnalyticsEngine(snapshot=tables, as_of=as_of).analyze()
