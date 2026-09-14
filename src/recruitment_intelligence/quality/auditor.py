"""Quality auditor generating typed Finding domain contracts.

Audits recruitment snapshot tables across referential integrity, multi-link arrays,
transitive orphans, intra-record and cross-table chronological paradoxes, and unmapped
or contradictory enums.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from ..domain import (
    Confidence,
    EvidenceReference,
    Finding,
    Severity,
)
from ..domain.models import Serializable
from .checks import (
    _CHRONOLOGY,
    _DEFAULT_SOURCES,
    _METRIC_BY_FIELD,
    _REQUIRED_FIELDS,
    _STATUS_VALUES,
    Record,
    Tables,
    _empty,
    _is_chronology_error,
    _items,
    _key,
    _metrics,
    _normalize_date,
    _parse_date,
    _record_id,
    _table,
    _text,
    _value,
    chronology_errors,
    duplicate_records,
    invalid_dates,
    missing_values,
    orphan_links,
    quality_confidence,
    source_taxonomy_issues,
    status_inconsistencies,
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

# Comprehensive foreign key schema across all 8 tables
_ALL_FOREIGN_KEYS: dict[str, tuple[tuple[str, str], ...]] = {
    "Departments": (),
    "People": (("department_id", "Departments"),),
    "Job Openings": (
        ("department_id", "Departments"),
        ("hiring_manager_id", "People"),
    ),
    "Candidates": (("person_id", "People"),),
    "Applications": (
        ("candidate_id", "Candidates"),
        ("job_id", "Job Openings"),
    ),
    "Interviews": (
        ("application_id", "Applications"),
        ("interviewer_id", "People"),
    ),
    "Offers": (
        ("application_id", "Applications"),
        ("candidate_id", "Candidates"),
    ),
    "Findings": (),
}

_VALID_INTERVIEW_STAGES = {
    "initial_screen",
    "screen",
    "screening",
    "technical",
    "technical_screen",
    "technical_interview",
    "sales_pitch",
    "founder_interview",
    "founder",
    "culture_fit",
    "hiring_manager",
    "hiring_manager_screen",
    "on_site",
    "onsite",
    "case_study",
    "final_round",
    "panel",
    "offer_review",
    "general",
    "phone_screen",
}

_VALID_FINDINGS_SEVERITIES = {"low", "medium", "high", "critical"}
_VALID_FINDINGS_CONFIDENCES = {"high", "medium", "low", "insufficient"}


def _extract_linked_ids(value: Any) -> list[str]:
    """Extract all linked record IDs from a field, supporting scalar, list, and dict forms."""
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set)):
        results: list[str] = []
        for item in value:
            results.extend(_extract_linked_ids(item))
        return results
    if isinstance(value, Mapping):
        val = value.get("id") or value.get("record_id") or value.get("name")
        return _extract_linked_ids(val)
    str_val = str(value).strip()
    return [str_val] if str_val else []


@dataclass(frozen=True, slots=True)
class QualityAuditResult(Serializable):
    """Immutable result of a full data quality audit."""
    findings: tuple[Finding, ...]
    confidence: Confidence
    summary: Mapping[str, Any]
    issues: tuple[Mapping[str, Any], ...] = ()
    tables_audited: tuple[str, ...] = CANONICAL_TABLES
    total_records: int = 0
    clean: bool = True

    def get_finding(self, finding_id: str) -> Finding | None:
        for f in self.findings:
            if f.finding_id == finding_id:
                return f
        return None

    def findings_by_category(self, category: str) -> tuple[Finding, ...]:
        cat = _key(category)
        return tuple(f for f in self.findings if _key(f.category or "") == cat)

    def findings_by_severity(self, severity: Severity | str) -> tuple[Finding, ...]:
        target = Severity(severity) if isinstance(severity, str) else severity
        return tuple(f for f in self.findings if f.severity == target)

    def findings_by_table(self, table: str) -> tuple[Finding, ...]:
        target = table.lower().replace("_", " ")
        results: list[Finding] = []
        for f in self.findings:
            if any(ev.table and ev.table.lower().replace("_", " ") == target for ev in f.evidence):
                results.append(f)
        return tuple(results)

    @property
    def affected_record_ids(self) -> tuple[str, ...]:
        ids: set[str] = set()
        for f in self.findings:
            ids.update(f.affected_records)
        return tuple(sorted(ids))


class QualityAuditor:
    """Deterministic quality auditor generating typed Finding objects."""

    def __init__(self, snapshot: Tables | None = None) -> None:
        self._snapshot = snapshot

    def _get_tables(self, snapshot: Tables | None = None) -> Tables:
        if snapshot is not None:
            return snapshot
        if self._snapshot is not None:
            return self._snapshot
        return {}

    def audit(self, snapshot: Tables | None = None) -> QualityAuditResult:
        """Run complete quality audit across all 8 tables."""
        tables = self._get_tables(snapshot)
        findings: list[Finding] = []
        raw_issues: list[dict[str, Any]] = []

        # 1. Base checks (missing values, duplicates, invalid dates, base chronology, base status, taxonomy)
        base_issues: list[dict[str, Any]] = []
        base_issues.extend(missing_values(tables))
        base_issues.extend(duplicate_records(tables))
        base_issues.extend(invalid_dates(tables))
        base_issues.extend(chronology_errors(tables))
        base_issues.extend(status_inconsistencies(tables))
        base_issues.extend(source_taxonomy_issues(tables))
        base_issues.extend(orphan_links(tables))

        raw_issues.extend(base_issues)

        # Convert base issues into typed Findings
        for i, issue in enumerate(base_issues):
            check = str(issue.get("check", "data_quality"))
            table = str(issue.get("table", "unknown"))
            field_name = issue.get("field")
            sev_str = str(issue.get("severity", "medium")).lower()
            severity = Severity(sev_str) if sev_str in Severity._value2member_map_ else Severity.MEDIUM
            conf_str = str(issue.get("confidence", "high")).lower()
            confidence = Confidence(conf_str) if conf_str in Confidence._value2member_map_ else Confidence.HIGH
            affected = tuple(sorted(str(r) for r in issue.get("affected_records", ())))
            message = str(issue.get("message", ""))
            metric_impact = tuple(str(m) for m in issue.get("metric_impact", ()))

            fid = f"qual-{check}-{_key(table)}-{_key(str(field_name))}-{i+1}"
            title = f"{check.replace('_', ' ').title()} in {table}"
            if field_name:
                title += f" ({field_name})"

            evidence_ref = EvidenceReference(
                source="quality_checks",
                table=table,
                record_ids=affected,
                method=check,
                caveats=(f"Metric impact: {', '.join(metric_impact)}",) if metric_impact else (),
            )

            finding = Finding(
                finding_id=fid,
                category=check,
                title=title,
                observed_fact=message,
                severity=severity,
                confidence=confidence,
                evidence=(evidence_ref,),
                affected_records=affected,
                recommendations=(
                    f"Review affected records in {table} and resolve {check.replace('_', ' ')} anomalies.",
                ),
                description=f"Automated quality audit detected {check} anomaly affecting {len(affected)} record(s) in {table}.",
                interpretation=f"May distort downstream analytics: {', '.join(metric_impact)}" if metric_impact else None,
            )
            findings.append(finding)

        # 2. Deep Foreign Key & Multi-Link Integrity Audit (across all 8 tables and multi-link arrays)
        # Avoid duplicating links already reported in base orphan_links
        base_orphan_pairs = {
            (str(iss.get("table")), str(iss.get("field")))
            for iss in base_issues if iss.get("check") == "orphan_link"
        }
        deep_fk_findings = self._audit_deep_foreign_keys(tables, exclude_pairs=base_orphan_pairs)
        for dfk in deep_fk_findings:
            findings.append(dfk)
            raw_issues.append({
                "check": "orphan_link",
                "table": dfk.evidence[0].table if dfk.evidence else "unknown",
                "field": dfk.finding_id.split("-")[-2] if "-" in dfk.finding_id else None,
                "severity": dfk.severity.value,
                "affected_records": list(dfk.affected_records),
                "metric_impact": ["referential_integrity"],
                "confidence": dfk.confidence.value,
                "message": dfk.observed_fact,
            })

        # 3. Transitive Orphan Cascades
        transitive_findings = self._audit_transitive_orphans(tables)
        for tf in transitive_findings:
            findings.append(tf)
            raw_issues.append({
                "check": "transitive_orphan",
                "table": tf.evidence[0].table if tf.evidence else "unknown",
                "field": "application_id",
                "severity": tf.severity.value,
                "affected_records": list(tf.affected_records),
                "metric_impact": ["funnel_transitions", "hire_conversion_rate"],
                "confidence": tf.confidence.value,
                "message": tf.observed_fact,
            })

        # 4. Cross-Table Timestamp Paradoxes
        cross_chrono_findings = self._audit_cross_table_chronology(tables)
        for ccf in cross_chrono_findings:
            findings.append(ccf)
            raw_issues.append({
                "check": "chronology_error",
                "table": ccf.evidence[0].table if ccf.evidence else "unknown",
                "field": "cross_table_timestamp",
                "severity": ccf.severity.value,
                "affected_records": list(ccf.affected_records),
                "metric_impact": ["funnel_transitions", "aging"],
                "confidence": ccf.confidence.value,
                "message": ccf.observed_fact,
            })

        # 5. Domain Enum & Contradiction Audit (Findings enums, Offer contradiction, Interview stages)
        enum_findings = self._audit_domain_enums(tables)
        for ef in enum_findings:
            findings.append(ef)
            raw_issues.append({
                "check": "unmapped_enum",
                "table": ef.evidence[0].table if ef.evidence else "unknown",
                "field": "enum",
                "severity": ef.severity.value,
                "affected_records": list(ef.affected_records),
                "metric_impact": ["data_governance"],
                "confidence": ef.confidence.value,
                "message": ef.observed_fact,
            })

        total_records = sum(len(_table(tables, t)) for t in CANONICAL_TABLES) or sum(len(rows) for rows in tables.values())
        overall_conf = quality_confidence(raw_issues, total_records)
        conf_enum = Confidence(overall_conf) if overall_conf in Confidence._value2member_map_ else Confidence.HIGH

        cat_counts = Counter(str(f.category) for f in findings)
        sev_counts = Counter(f.severity.value for f in findings)

        summary = {
            "total_records": total_records,
            "finding_count": len(findings),
            "by_category": dict(sorted(cat_counts.items())),
            "by_severity": dict(sorted(sev_counts.items())),
            "clean": len(findings) == 0,
        }

        return QualityAuditResult(
            findings=tuple(findings),
            confidence=conf_enum,
            summary=summary,
            issues=tuple(raw_issues),
            tables_audited=CANONICAL_TABLES,
            total_records=total_records,
            clean=len(findings) == 0,
        )

    def _audit_deep_foreign_keys(
        self,
        tables: Tables,
        exclude_pairs: set[tuple[str, str]] | None = None,
    ) -> list[Finding]:
        """Audit foreign keys including secondary relationships and multi-link arrays."""
        exclude = exclude_pairs or set()
        findings: list[Finding] = []

        for source_table, link_specs in _ALL_FOREIGN_KEYS.items():
            source_rows = _table(tables, source_table)
            if not source_rows:
                continue

            for field_name, target_table in link_specs:
                if (source_table, field_name) in exclude:
                    continue

                target_rows = _table(tables, target_table)
                target_ids = {_record_id(r, target_table, idx) for idx, r in enumerate(target_rows)}

                affected_rids: list[str] = []
                dangling_target_ids: list[str] = []

                for idx, row in enumerate(source_rows):
                    val = _value(row, field_name)
                    if _empty(val):
                        continue
                    linked_ids = _extract_linked_ids(val)
                    broken = [lid for lid in linked_ids if lid and lid not in target_ids]
                    if broken:
                        affected_rids.append(_record_id(row, source_table, idx))
                        dangling_target_ids.extend(broken)

                if affected_rids:
                    affected_sorted = tuple(sorted(set(affected_rids)))
                    dangling_sorted = sorted(set(dangling_target_ids))
                    findings.append(Finding(
                        finding_id=f"qual-fk-{_key(source_table)}-{_key(field_name)}",
                        category="foreign_key_integrity",
                        title=f"Foreign Key Link Integrity Violation in {source_table}.{field_name}",
                        observed_fact=(
                            f"{len(affected_sorted)} record(s) in {source_table} link to missing "
                            f"{target_table} record(s): {', '.join(dangling_sorted)}."
                        ),
                        severity=Severity.HIGH,
                        confidence=Confidence.HIGH,
                        evidence=(
                            EvidenceReference(
                                source="quality_auditor",
                                table=source_table,
                                record_ids=affected_sorted,
                                method="foreign_key_integrity",
                                caveats=(f"Target table: {target_table}",),
                            ),
                        ),
                        affected_records=affected_sorted,
                        recommendations=(
                            f"Restore missing {target_table} records or update foreign keys in {source_table}.{field_name}.",
                        ),
                        description=f"Records in {source_table} contain foreign key references to nonexistent records in {target_table}.",
                        interpretation="Breaks referential integrity, causing joins and relationship traversals to fail.",
                    ))
        return findings

    def _audit_transitive_orphans(self, tables: Tables) -> list[Finding]:
        """Detect child records whose parent record exists but is itself an orphaned record."""
        findings: list[Finding] = []

        # Find directly orphaned Applications (missing candidate_id or job_id)
        candidates = _table(tables, "Candidates")
        candidate_ids = {_record_id(r, "Candidates", i) for i, r in enumerate(candidates)}
        jobs = _table(tables, "Job Openings")
        job_ids = {_record_id(r, "Job Openings", i) for i, r in enumerate(jobs)}

        apps = _table(tables, "Applications")
        orphaned_app_ids: set[str] = set()
        for i, app in enumerate(apps):
            app_id = _record_id(app, "Applications", i)
            cand_id = _text(_value(app, "candidate_id"))
            job_id = _text(_value(app, "job_id"))
            if (cand_id and cand_id not in candidate_ids) or (job_id and job_id not in job_ids):
                orphaned_app_ids.add(app_id)

        if not orphaned_app_ids:
            return findings

        # Check Interviews linked to orphaned Applications
        interviews = _table(tables, "Interviews")
        affected_interviews: list[str] = []
        for i, iv in enumerate(interviews):
            app_id = _text(_value(iv, "application_id"))
            if app_id in orphaned_app_ids:
                affected_interviews.append(_record_id(iv, "Interviews", i))

        if affected_interviews:
            sorted_affected = tuple(sorted(set(affected_interviews)))
            findings.append(Finding(
                finding_id="qual-transitive-orphan-interviews-applications",
                category="transitive_orphan",
                title="Transitive Orphan Interviews Linked to Invalid Applications",
                observed_fact=(
                    f"{len(sorted_affected)} Interview record(s) link to Applications that are themselves "
                    f"orphaned due to missing Candidate or Job records."
                ),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                evidence=(
                    EvidenceReference(
                        source="quality_auditor",
                        table="Interviews",
                        record_ids=sorted_affected,
                        method="transitive_orphan_detection",
                        caveats=("Parent applications have broken foreign keys.",),
                    ),
                ),
                affected_records=sorted_affected,
                recommendations=(
                    "Resolve upstream candidate and job links on parent applications to restore funnel validity.",
                ),
                description="Interviews appear valid locally but their parent applications cannot be tied to a candidate or job.",
                interpretation="Corrupts interview-to-application pass-through conversion metrics and recruiter workload tracking.",
            ))

        # Check Offers linked to orphaned Applications
        offers = _table(tables, "Offers")
        affected_offers: list[str] = []
        for i, off in enumerate(offers):
            app_id = _text(_value(off, "application_id"))
            if app_id in orphaned_app_ids:
                affected_offers.append(_record_id(off, "Offers", i))

        if affected_offers:
            sorted_affected = tuple(sorted(set(affected_offers)))
            findings.append(Finding(
                finding_id="qual-transitive-orphan-offers-applications",
                category="transitive_orphan",
                title="Transitive Orphan Offers Linked to Invalid Applications",
                observed_fact=(
                    f"{len(sorted_affected)} Offer record(s) link to Applications that are themselves "
                    f"orphaned due to missing Candidate or Job records."
                ),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                evidence=(
                    EvidenceReference(
                        source="quality_auditor",
                        table="Offers",
                        record_ids=sorted_affected,
                        method="transitive_orphan_detection",
                        caveats=("Parent applications have broken foreign keys.",),
                    ),
                ),
                affected_records=sorted_affected,
                recommendations=(
                    "Resolve upstream candidate and job links on parent applications.",
                ),
                description="Offers reference applications with invalid parent entities.",
                interpretation="Distorts offer acceptance rates and hire attribution.",
            ))

        return findings

    def _audit_cross_table_chronology(self, tables: Tables) -> list[Finding]:
        """Detect cross-table chronological paradoxes between linked entities."""
        findings: list[Finding] = []

        jobs = {
            _record_id(r, "Job Openings", i): r
            for i, r in enumerate(_table(tables, "Job Openings"))
        }
        apps = {
            _record_id(r, "Applications", i): r
            for i, r in enumerate(_table(tables, "Applications"))
        }
        interviews = _table(tables, "Interviews")
        offers = _table(tables, "Offers")

        # 1. Applications.applied_at vs Job Openings.closed_at
        applied_after_closed: list[str] = []
        app_updated_before_applied: list[str] = []
        for app_id, app in apps.items():
            applied_val = _value(app, "applied_at")
            updated_val = _value(app, "updated_at", "closed_at")

            # Updated before applied (intra-app: updated_at < applied_at)
            if _is_chronology_error(applied_val, updated_val):
                app_updated_before_applied.append(app_id)

            # Applied after job requisition was closed (cross-table: job_closed < applied_at)
            job_id = _text(_value(app, "job_id"))
            if job_id and job_id in jobs:
                job_closed = _value(jobs[job_id], "closed_at")
                if _is_chronology_error(applied_val, job_closed):
                    applied_after_closed.append(app_id)

        if applied_after_closed:
            sorted_aff = tuple(sorted(set(applied_after_closed)))
            findings.append(Finding(
                finding_id="qual-cross-chrono-applied-after-job-closed",
                category="chronology_error",
                title="Applications Submitted After Job Opening Was Closed",
                observed_fact=(
                    f"{len(sorted_aff)} Application(s) have 'applied_at' timestamps occurring after "
                    f"their linked Job Opening 'closed_at' date."
                ),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                evidence=(
                    EvidenceReference(
                        source="quality_auditor",
                        table="Applications",
                        record_ids=sorted_aff,
                        method="cross_table_chronology",
                        caveats=("Requisition closed before application submission.",),
                    ),
                ),
                affected_records=sorted_aff,
                recommendations=(
                    "Verify requisition closure dates or candidate application submission timestamps.",
                ),
                description="Applications received after a requisition closed indicates retroactive data entry or timestamp mismatch.",
                interpretation="Distorts requisition time-to-fill and funnel duration calculations.",
            ))

        if app_updated_before_applied:
            sorted_aff = tuple(sorted(set(app_updated_before_applied)))
            findings.append(Finding(
                finding_id="qual-chrono-app-updated-before-applied",
                category="chronology_error",
                title="Applications Updated Before Submission Date",
                observed_fact=(
                    f"{len(sorted_aff)} Application(s) have 'updated_at' timestamps preceding 'applied_at'."
                ),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                evidence=(
                    EvidenceReference(
                        source="quality_auditor",
                        table="Applications",
                        record_ids=sorted_aff,
                        method="intra_record_chronology",
                    ),
                ),
                affected_records=sorted_aff,
                recommendations=("Correct application timestamps.",),
                description="Application update date precedes application creation date.",
                interpretation="Distorts application aging and stalled process detection.",
            ))

        # 2. Interviews.scheduled_at vs Applications.applied_at (iv_scheduled < app_applied)
        interview_before_app: list[str] = []
        for i, iv in enumerate(interviews):
            iv_id = _record_id(iv, "Interviews", i)
            app_id = _text(_value(iv, "application_id"))
            if app_id and app_id in apps:
                app_applied = _value(apps[app_id], "applied_at")
                iv_scheduled = _value(iv, "scheduled_at", "date")
                if _is_chronology_error(app_applied, iv_scheduled):
                    interview_before_app.append(iv_id)

        if interview_before_app:
            sorted_aff = tuple(sorted(set(interview_before_app)))
            findings.append(Finding(
                finding_id="qual-cross-chrono-interview-before-application",
                category="chronology_error",
                title="Interview Scheduled Before Candidate Application Date",
                observed_fact=(
                    f"{len(sorted_aff)} Interview(s) have 'scheduled_at' timestamps preceding "
                    f"the candidate's application submission date."
                ),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                evidence=(
                    EvidenceReference(
                        source="quality_auditor",
                        table="Interviews",
                        record_ids=sorted_aff,
                        method="cross_table_chronology",
                    ),
                ),
                affected_records=sorted_aff,
                recommendations=("Align interview schedule with application submission date.",),
                description="Interviews recorded prior to application submission indicate retroactive scheduling.",
                interpretation="Produces negative stage elapsed days and corrupts funnel velocity metrics.",
            ))

        # 3. Offers.offered_at vs Applications.applied_at (off_offered < app_applied)
        offer_before_app: list[str] = []
        for i, off in enumerate(offers):
            off_id = _record_id(off, "Offers", i)
            app_id = _text(_value(off, "application_id"))
            if app_id and app_id in apps:
                app_applied = _value(apps[app_id], "applied_at")
                off_offered = _value(off, "offered_at")
                if _is_chronology_error(app_applied, off_offered):
                    offer_before_app.append(off_id)

        if offer_before_app:
            sorted_aff = tuple(sorted(set(offer_before_app)))
            findings.append(Finding(
                finding_id="qual-cross-chrono-offer-before-application",
                category="chronology_error",
                title="Offer Extended Before Candidate Application Date",
                observed_fact=(
                    f"{len(sorted_aff)} Offer(s) have 'offered_at' timestamps preceding "
                    f"the candidate's application submission date."
                ),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                evidence=(
                    EvidenceReference(
                        source="quality_auditor",
                        table="Offers",
                        record_ids=sorted_aff,
                        method="cross_table_chronology",
                    ),
                ),
                affected_records=sorted_aff,
                recommendations=("Verify offer extension and application creation timestamps.",),
                description="Formal offer extension date precedes application date.",
                interpretation="Distorts hiring cycle duration and funnel stage sequence.",
            ))

        return findings

    def _audit_domain_enums(self, tables: Tables) -> list[Finding]:
        """Audit status, stage, Findings severity/confidence, and contradictory offer flags."""
        findings: list[Finding] = []

        # 1. Findings table enum validation
        findings_rows = _table(tables, "Findings")
        invalid_sev_findings: list[str] = []
        invalid_conf_findings: list[str] = []

        for i, f_row in enumerate(findings_rows):
            f_id = _record_id(f_row, "Findings", i)
            sev = _key(_value(f_row, "severity"))
            conf = _key(_value(f_row, "confidence"))
            if sev and sev not in _VALID_FINDINGS_SEVERITIES:
                invalid_sev_findings.append(f_id)
            if conf and conf not in _VALID_FINDINGS_CONFIDENCES:
                invalid_conf_findings.append(f_id)

        if invalid_sev_findings:
            sorted_aff = tuple(sorted(set(invalid_sev_findings)))
            findings.append(Finding(
                finding_id="qual-enum-findings-severity",
                category="unmapped_enum",
                title="Unmapped Severity Enum in Findings Table",
                observed_fact=(
                    f"{len(sorted_aff)} Finding record(s) contain unmapped severity values not in "
                    f"{sorted(_VALID_FINDINGS_SEVERITIES)}."
                ),
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                evidence=(
                    EvidenceReference(
                        source="quality_auditor",
                        table="Findings",
                        record_ids=sorted_aff,
                        method="enum_validation",
                    ),
                ),
                affected_records=sorted_aff,
                recommendations=("Map findings severity to canonical enum: low, medium, high, critical.",),
                description="Findings record severity does not match domain Severity enum.",
                interpretation="Prevents automated triage and alerting by executive report generators.",
            ))

        if invalid_conf_findings:
            sorted_aff = tuple(sorted(set(invalid_conf_findings)))
            findings.append(Finding(
                finding_id="qual-enum-findings-confidence",
                category="unmapped_enum",
                title="Unmapped Confidence Enum in Findings Table",
                observed_fact=(
                    f"{len(sorted_aff)} Finding record(s) contain unmapped confidence values not in "
                    f"{sorted(_VALID_FINDINGS_CONFIDENCES)}."
                ),
                severity=Severity.MEDIUM,
                confidence=Confidence.HIGH,
                evidence=(
                    EvidenceReference(
                        source="quality_auditor",
                        table="Findings",
                        record_ids=sorted_aff,
                        method="enum_validation",
                    ),
                ),
                affected_records=sorted_aff,
                recommendations=("Map findings confidence to canonical enum: high, medium, low, insufficient.",),
                description="Findings record confidence does not match domain Confidence enum.",
                interpretation="Weakens executive decision confidence scoring.",
            ))

        # 2. Offer contradictions (accepted flag vs declined/rejected flags or statuses)
        offers_rows = _table(tables, "Offers")
        contradictory_offers: list[str] = []
        for i, off in enumerate(offers_rows):
            off_id = _record_id(off, "Offers", i)
            is_accepted = bool(_value(off, "is_accepted", "accepted", default=False))
            status = _key(_value(off, "status"))
            declined = bool(_value(off, "declined", "rejected", "is_declined", "is_rejected", default=False))
            is_terminal_reject = status in {"rejected", "declined", "withdrawn"}

            if (is_accepted or status in {"accepted", "hired", "joined"}) and (declined or is_terminal_reject):
                contradictory_offers.append(off_id)

        if contradictory_offers:
            sorted_aff = tuple(sorted(set(contradictory_offers)))
            findings.append(Finding(
                finding_id="qual-offer-contradiction-accepted-vs-declined",
                category="status_inconsistency",
                title="Contradictory Offer Acceptance and Rejection Flags",
                observed_fact=(
                    f"{len(sorted_aff)} Offer record(s) have contradictory acceptance and decline/rejection states."
                ),
                severity=Severity.HIGH,
                confidence=Confidence.HIGH,
                evidence=(
                    EvidenceReference(
                        source="quality_auditor",
                        table="Offers",
                        record_ids=sorted_aff,
                        method="contradiction_audit",
                    ),
                ),
                affected_records=sorted_aff,
                recommendations=("Clarify formal offer outcome: accepted vs declined.",),
                description="An offer is simultaneously marked as accepted and declined/rejected.",
                interpretation="Directly corrupts Offer Acceptance Rate (Q3) calculation.",
            ))

        return findings


def run_quality_audit(snapshot: Tables) -> QualityAuditResult:
    """Run full quality audit returning typed QualityAuditResult."""
    return QualityAuditor(snapshot).audit()
