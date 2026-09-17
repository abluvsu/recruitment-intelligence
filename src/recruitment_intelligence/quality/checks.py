"""Deterministic data-quality checks for recruitment snapshots.

The quality layer deliberately returns ordinary JSON-compatible dictionaries.
This makes warnings easy to persist alongside a snapshot and keeps the module
independent from Airtable SDKs and model providers.  Unknown values are
reported; they are never silently normalised into a known category.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

Record = Mapping[str, Any]
Tables = Mapping[str, Sequence[Record]]


def _table(tables: Tables, name: str) -> list[Record]:
    wanted = name.lower().replace("_", " ")
    for key, rows in tables.items():
        if str(key).lower().replace("_", " ") == wanted:
            return list(rows)
    return []


def _key(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")


def _items(row: Record) -> dict[str, Any]:
    """Flatten Airtable ``fields`` while retaining the record envelope."""
    values: dict[str, Any] = {}
    nested = row.get("fields") if isinstance(row, Mapping) else None
    if isinstance(nested, Mapping):
        values.update({str(k): v for k, v in nested.items()})
    values.update({str(k): v for k, v in row.items() if k != "fields"})
    return values


def _value(row: Record, *names: str, default: Any = None) -> Any:
    lowered = {_key(k): value for k, value in _items(row).items()}
    for name in names:
        if _key(name) in lowered:
            return lowered[_key(name)]
    return default


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return _text(value[0]) if value else ""
    if isinstance(value, Mapping):
        return _text(value.get("id") or value.get("record_id") or value.get("name"))
    return str(value).strip()


def _record_id(row: Record, table: str, index: int) -> str:
    value = _value(
        row,
        "id",
        "record_id",
        f"{_key(table).rstrip('s')}_id",
        "application_id",
        "candidate_id",
        "interview_id",
        "offer_id",
        "job_id",
        "department_id",
        "person_id",
    )
    return _text(value) or f"{table}[{index}]"


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == [] or value == ()


def _issue(
    check: str,
    table: str,
    field: str | None,
    severity: str,
    affected_records: Iterable[str],
    metric_impact: Iterable[str],
    confidence: str,
    message: str,
) -> dict[str, Any]:
    """Build the stable warning shape consumed by memo and agent layers."""
    return {
        "check": check,
        "table": table,
        "field": field,
        "severity": severity,
        "affected_records": sorted({str(item) for item in affected_records}),
        "metric_impact": sorted({str(item) for item in metric_impact}),
        "confidence": confidence,
        "message": message,
    }


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "candidate_id": ("candidate_id", "candidate", "candidate_link"),
    "application_id": ("application_id", "application", "app_id", "application_link"),
    "job_id": ("job_id", "opening", "job_opening", "opening_id", "requisition_id"),
    "department_id": ("department_id", "department"),
    "person_id": ("person_id", "person"),
    "title": ("title", "job_title", "role"),
    "name": ("name", "department_name", "full_name", "title"),
    "id": ("id", "record_id"),
}

_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "Departments": ("id", "name"),
    "People": ("id",),
    "Job Openings": ("id", "title"),
    "Candidates": ("id",),
    "Applications": ("id", "candidate_id"),
    "Interviews": ("id", "application_id"),
    "Offers": ("id", "application_id"),
}

_METRIC_BY_FIELD = {
    "candidate_id": ("funnel_transitions", "hire_conversion_rate", "source_effectiveness"),
    "application_id": ("funnel_transitions", "offer_acceptance_rate"),
    "source": ("source_effectiveness", "source_department_segmentation"),
    "status": ("funnel_transitions", "offer_acceptance_rate", "stalled_applications"),
    "applied_at": ("aging", "stalled_applications", "funnel_transitions"),
    "updated_at": ("aging", "stalled_applications"),
}


def _metrics(field: str | None, *extra: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*_METRIC_BY_FIELD.get(_key(field or ""), ()), *extra)))


def missing_values(tables: Tables, required_fields: Mapping[str, Sequence[str]] | None = None) -> list[dict[str, Any]]:
    """Report missing required values, one warning per table and field."""
    required_fields = required_fields or _REQUIRED_FIELDS
    issues: list[dict[str, Any]] = []
    for table, fields in required_fields.items():
        rows = _table(tables, table)
        for field in fields:
            aliases = _FIELD_ALIASES.get(field, (field, "record_id") if field == "id" else (field,))
            affected = [_record_id(row, table, i) for i, row in enumerate(rows) if _empty(_value(row, *aliases))]
            if affected:
                issues.append(_issue("missing_value", table, field, "high", affected, _metrics(field, "table_counts"), "high", f"{len(affected)} record(s) are missing required field '{field}'."))
    return issues


def duplicate_records(tables: Tables) -> list[dict[str, Any]]:
    """Find duplicate record identifiers within each table."""
    issues: list[dict[str, Any]] = []
    for table, rows in tables.items():
        groups: dict[str, list[str]] = {}
        for i, row in enumerate(rows):
            rid = _text(_value(row, "id", "record_id"))
            if rid:
                groups.setdefault(rid, []).append(_record_id(row, str(table), i))
        for rid, records in sorted(groups.items()):
            if len(records) > 1:
                issues.append(_issue("duplicate_record", str(table), "id", "high", records, ("table_counts", "funnel_transitions", "source_effectiveness"), "high", f"Record identifier '{rid}' appears {len(records)} times."))
    return issues


_LINKS = {
    "Candidates": (("person_id", "People"),),
    "Job Openings": (("department_id", "Departments"),),
    "Applications": (("candidate_id", "Candidates"), ("job_id", "Job Openings")),
    "Interviews": (("application_id", "Applications"),),
    "Offers": (("application_id", "Applications"),),
}


def orphan_links(tables: Tables) -> list[dict[str, Any]]:
    """Report non-empty foreign keys whose target record is absent."""
    issues: list[dict[str, Any]] = []
    for table, links in _LINKS.items():
        rows = _table(tables, table)
        for field, target in links:
            target_ids = set()
            for i, row in enumerate(_table(tables, target)):
                target_ids.add(_record_id(row, target, i))
                for k in ("id", "record_id", f"{_key(target).rstrip('s')}_id", "candidate_id", "application_id", "job_id", "department_id", "person_id", "req_id", "code"):
                    v = _text(_value(row, k))
                    if v:
                        target_ids.add(v)
            affected: list[str] = []
            dangling: list[str] = []
            aliases = _FIELD_ALIASES.get(field, (field,))
            for i, row in enumerate(rows):
                linked = _text(_value(row, *aliases))
                if linked and linked not in target_ids:
                    affected.append(_record_id(row, table, i)); dangling.append(linked)
            if affected:
                issues.append(_issue("orphan_link", table, field, "high", affected, _metrics(field, "hire_conversion_rate", "funnel_transitions"), "high", f"{len(affected)} record(s) link to missing {target} record(s): {', '.join(sorted(set(dangling)))}."))
    return issues


def _parse_date(value: Any) -> datetime | date | None:
    if isinstance(value, (datetime, date)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def invalid_dates(tables: Tables) -> list[dict[str, Any]]:
    """Find values in date-like fields that cannot be parsed as ISO dates."""
    issues: list[dict[str, Any]] = []
    for table, rows in tables.items():
        by_field: dict[str, list[str]] = {}
        for i, row in enumerate(rows):
            rid = _record_id(row, str(table), i)
            for field, value in _items(row).items():
                field_name = _key(field)
                if not (field_name.endswith("_at") or field_name.endswith("_date") or field_name in {"date", "created_time", "modified_time"}):
                    continue
                if _empty(value):
                    continue
                if _parse_date(value) is None:
                    by_field.setdefault(field_name, []).append(rid)
        for field, affected in sorted(by_field.items()):
            issues.append(_issue("invalid_date", str(table), field, "high", affected, _metrics(field, "aging", "stalled_applications"), "high", f"{len(affected)} record(s) contain an invalid date in '{field}'."))
    return issues


_CHRONOLOGY = {
    "Job Openings": (("opened_at", "closed_at"),),
    "Interviews": (("scheduled_at", "completed_at"),),
    "Offers": (("offered_at", "responded_at"),),
    "Airtable": (("created_time", "modified_time"),),
}


def _normalize_date(value: Any) -> datetime | None:
    """Normalize string, date, or datetime into a naive UTC-aligned datetime for comparison."""
    parsed = _parse_date(value)
    if parsed is None:
        return None
    if isinstance(parsed, datetime):
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    if isinstance(parsed, date):
        return datetime.combine(parsed, datetime.min.time())
    return None


def _has_time_component(val: Any) -> bool:
    if isinstance(val, datetime):
        return val.time() != datetime.min.time() or (val.tzinfo is not None)
    if isinstance(val, str):
        s = val.strip()
        return "T" in s or ":" in s
    return False


def _is_chronology_error(start_raw: Any, end_raw: Any) -> bool:
    """Safely compare start and end dates/datetimes across naive, aware, and mixed formats."""
    start_parsed = _parse_date(start_raw)
    end_parsed = _parse_date(end_raw)
    if start_parsed is None or end_parsed is None:
        return False

    if _has_time_component(start_raw) and _has_time_component(end_raw):
        if isinstance(start_parsed, datetime) and isinstance(end_parsed, datetime):
            s_dt = start_parsed.astimezone(timezone.utc).replace(tzinfo=None) if start_parsed.tzinfo else start_parsed
            e_dt = end_parsed.astimezone(timezone.utc).replace(tzinfo=None) if end_parsed.tzinfo else end_parsed
            return e_dt < s_dt

    s_date = start_parsed.date() if isinstance(start_parsed, datetime) else start_parsed
    e_date = end_parsed.date() if isinstance(end_parsed, datetime) else end_parsed
    return e_date < s_date


def chronology_errors(tables: Tables) -> list[dict[str, Any]]:
    """Detect end timestamps that precede their corresponding start."""
    issues: list[dict[str, Any]] = []
    for table, pairs in _CHRONOLOGY.items():
        sources = list(tables.items()) if table == "Airtable" else [(table, _table(tables, table))]
        for start_field, end_field in pairs:
            for source_table, source_rows in sources:
                affected = []
                for i, row in enumerate(source_rows):
                    start_val, end_val = _value(row, start_field), _value(row, end_field)
                    if _is_chronology_error(start_val, end_val):
                        affected.append(_record_id(row, str(source_table), i))
                if affected:
                    issues.append(_issue("chronology_error", str(source_table), f"{start_field},{end_field}", "high", affected, _metrics(start_field, "aging", "funnel_transitions"), "high", f"'{end_field}' occurs before '{start_field}' for {len(affected)} record(s)."))
    return issues


_STATUS_VALUES = {
    "Applications": {"applied", "application", "screen", "screening", "interview", "interviewing", "offer", "offer_made", "accepted", "hired", "rejected", "withdrawn", "closed", "offer_accepted", "offer_rejected", "active"},
    "Candidates": {"new", "active", "screening", "interview", "offer", "hired", "rejected", "withdrawn", "archived", "joined"},
    "Interviews": {"scheduled", "completed", "cancelled", "canceled", "no_show", "passed", "failed", "pending"},
    "Offers": {"draft", "pending", "sent", "accepted", "rejected", "declined", "expired", "withdrawn", "hired", "joined"},
    "Job Openings": {"draft", "open", "active", "paused", "closed", "filled", "cancelled", "canceled", "on_hold", "on hold"},
}


def status_inconsistencies(tables: Tables, allowed_statuses: Mapping[str, Iterable[str]] | None = None) -> list[dict[str, Any]]:
    """Report unmapped statuses and explicit contradictory status flags."""
    allowed = {table: {_key(value) for value in values} for table, values in (allowed_statuses or _STATUS_VALUES).items()}
    issues: list[dict[str, Any]] = []
    for table, values in allowed.items():
        rows = _table(tables, table)
        affected_by_value: dict[str, list[str]] = {}
        for i, row in enumerate(rows):
            raw = _text(_value(row, "status", "stage", "application_status"))
            if raw and _key(raw) not in values:
                affected_by_value.setdefault(raw, []).append(_record_id(row, table, i))
            # A terminal state paired with a contradictory boolean is data corruption.
            if _key(raw) in {"hired", "accepted", "joined"} and bool(_value(row, "rejected", "is_rejected", default=False)):
                affected_by_value.setdefault("contradictory_terminal_flag", []).append(_record_id(row, table, i))
        for raw, affected in sorted(affected_by_value.items()):
            if raw == "contradictory_terminal_flag":
                message = "Terminal status is contradictory to a rejection flag."
            else:
                message = f"Status '{raw}' is not mapped for {table}; it was not coerced."
            issues.append(_issue("status_inconsistency", table, "status", "medium" if raw != "contradictory_terminal_flag" else "high", affected, _metrics("status"), "high", message))
    return issues


_DEFAULT_SOURCES = {"referral", "employee_referral", "job_board", "agency", "direct", "careers_page", "linkedin", "indeed", "recruiter", "university", "unknown"}


def source_taxonomy_issues(tables: Tables, allowed_sources: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Report source values absent from the explicit source taxonomy."""
    allowed = {_key(value) for value in (allowed_sources or _DEFAULT_SOURCES)}
    grouped: dict[str, list[str]] = {}
    for i, row in enumerate(_table(tables, "Applications")):
        source = _text(_value(row, "source", "recruiting_source", "channel"))
        if source and _key(source) not in allowed:
            grouped.setdefault(source, []).append(_record_id(row, "Applications", i))
    return [_issue("source_taxonomy", "Applications", "source", "medium", records, _metrics("source"), "medium", f"Source '{source}' is not in the configured taxonomy; it remains unmapped.") for source, records in sorted(grouped.items())]


def quality_confidence(issues: Sequence[Mapping[str, Any]], total_records: int | None = None) -> str:
    """Return confidence in the snapshot based on issue severity and coverage."""
    if not issues and (total_records is None or total_records > 0):
        return "high"
    if total_records == 0 or (total_records is None and not issues):
        return "insufficient"
    if any(str(issue.get("severity")) in {"critical", "high"} for issue in issues):
        return "low"
    return "medium"


def affected_metrics(issues: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Aggregate metric impact by quality check for sensitivity consumers."""
    grouped: dict[str, set[str]] = {}
    for issue in issues:
        check = str(issue.get("check", "unknown"))
        grouped.setdefault(check, set()).update(str(metric) for metric in issue.get("metric_impact", ()))
    return {check: sorted(metrics) for check, metrics in sorted(grouped.items())}


def run_quality_checks(tables: Tables) -> dict[str, Any]:
    """Run all checks and return issues, counts, and an overall confidence."""
    checks = (missing_values, duplicate_records, orphan_links, invalid_dates, chronology_errors, status_inconsistencies, source_taxonomy_issues)
    issues: list[dict[str, Any]] = []
    for check in checks:
        issues.extend(check(tables))
    total = sum(len(rows) for rows in tables.values())
    counts = Counter(str(issue["check"]) for issue in issues)
    return {"issues": issues, "confidence": quality_confidence(issues, total), "summary": {"total_records": total, "issue_count": len(issues), "by_check": dict(sorted(counts.items()))}}


# Friendly aliases used by orchestrators.
check_quality = run_quality_checks
find_quality_issues = run_quality_checks
assess_data_quality = run_quality_checks
data_quality_report = run_quality_checks
data_quality_confidence = quality_confidence


def duplicate_candidates(tables: Tables) -> list[dict[str, Any]]:
    """Detect duplicate candidate pairs sharing identical phone and name."""
    cands = _table(tables, "Candidates")
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for i, c in enumerate(cands):
        name = _text(_value(c, "full_name", "name"))
        phone = _text(_value(c, "phone", "phone_number"))
        if name and phone:
            cid = _text(_value(c, "candidate_id", "id")) or f"Candidates[{i}]"
            groups[(name, phone)].append(cid)
    issues = []
    for (name, phone), ids in sorted(groups.items()):
        if len(ids) > 1:
            issues.append(_issue(
                "duplicate_candidate_profile",
                "Candidates",
                "phone",
                "high",
                ids,
                ("candidate_counts", "source_effectiveness"),
                "high",
                f"Candidate '{name}' ({phone}) has {len(ids)} duplicate profiles: {', '.join(ids)}."
            ))
    return issues


def duplicate_applications(tables: Tables) -> list[dict[str, Any]]:
    """Detect candidates reapplying to identical openings."""
    apps = _table(tables, "Applications")
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for i, a in enumerate(apps):
        cid = _text(_value(a, "candidate_id", "candidate"))
        oid = _text(_value(a, "opening", "opening_id", "job_id", "job_opening"))
        aid = _text(_value(a, "application_id", "id")) or f"Applications[{i}]"
        if cid and oid:
            groups[(cid, oid)].append(aid)
    issues = []
    for (cid, oid), ids in sorted(groups.items()):
        if len(ids) > 1:
            issues.append(_issue(
                "duplicate_application_opening",
                "Applications",
                "opening",
                "high",
                ids,
                ("funnel_transitions", "application_counts"),
                "high",
                f"Candidate '{cid}' applied {len(ids)} times to opening '{oid}': {', '.join(ids)}."
            ))
    return issues


def salary_band_violations(tables: Tables) -> list[dict[str, Any]]:
    """Detect extended offers whose compensation violates requisition salary bands."""
    offers = _table(tables, "Offers")
    apps = {_record_id(a, "Applications", i): a for i, a in enumerate(_table(tables, "Applications"))}
    for i, a in enumerate(_table(tables, "Applications")):
        aid = _text(_value(a, "id", "record_id", "application_id"))
        if aid:
            apps[aid] = a
    openings = {_record_id(o, "Job Openings", i): o for i, o in enumerate(_table(tables, "Job Openings"))}
    for i, o in enumerate(_table(tables, "Job Openings")):
        oid = _text(_value(o, "id", "record_id", "req_id"))
        if oid:
            openings[oid] = o

    issues = []
    for i, off in enumerate(offers):
        base = _value(off, "base_ctc", "base_salary", "salary")
        if base is None:
            continue
        try:
            base_val = float(base)
        except (ValueError, TypeError):
            continue
        app_ref = _text(_value(off, "application", "application_id", "app_id"))
        app = apps.get(app_ref, {})
        op_ref = _text(_value(app, "opening", "opening_id", "job_id"))
        op = openings.get(op_ref, {})
        b_min = _value(op, "salary_band_min", "band_min", "min_salary")
        b_max = _value(op, "salary_band_max", "band_max", "max_salary")
        off_id = _record_id(off, "Offers", i)

        if b_max is not None:
            try:
                b_max_val = float(b_max)
                if base_val > b_max_val:
                    pct = (base_val - b_max_val) / b_max_val * 100
                    issues.append(_issue(
                        "salary_band_overrun",
                        "Offers",
                        "base_ctc",
                        "high",
                        [off_id],
                        ("offer_acceptance_rate", "compensation_competitiveness"),
                        "high",
                        f"Offer '{off_id}' base CTC {base_val:,.0f} exceeds band maximum {b_max_val:,.0f} (+{pct:.1f}%)."
                    ))
            except (ValueError, TypeError):
                pass
        if b_min is not None:
            try:
                b_min_val = float(b_min)
                if base_val < b_min_val:
                    pct = (base_val - b_min_val) / b_min_val * 100
                    issues.append(_issue(
                        "salary_band_underrun",
                        "Offers",
                        "base_ctc",
                        "medium",
                        [off_id],
                        ("offer_acceptance_rate", "compensation_competitiveness"),
                        "high",
                        f"Offer '{off_id}' base CTC {base_val:,.0f} is below band minimum {b_min_val:,.0f} ({pct:.1f}%)."
                    ))
            except (ValueError, TypeError):
                pass
    return sorted(issues, key=lambda x: x["affected_records"][0] if x["affected_records"] else "")


def stale_pending_offers(tables: Tables, as_of: date | datetime | str | None = None) -> list[dict[str, Any]]:
    """Detect pending offers that exceed typical response windows."""
    ref_date = _parse_date(as_of) or date(2026, 9, 2)
    ref = ref_date.date() if isinstance(ref_date, datetime) else ref_date
    offers = _table(tables, "Offers")
    issues = []
    for i, off in enumerate(offers):
        st = _key(_value(off, "status"))
        if st == "pending":
            off_date = _parse_date(_value(off, "offered_on", "offered_at"))
            if off_date:
                d = off_date.date() if isinstance(off_date, datetime) else off_date
                age = (ref - d).days
                off_id = _record_id(off, "Offers", i)
                if age >= 30:
                    issues.append(_issue(
                        "stale_pending_offer",
                        "Offers",
                        "status",
                        "high",
                        [off_id],
                        ("offer_acceptance_rate", "pipeline_velocity"),
                        "high",
                        f"Offer '{off_id}' has been pending for {age} days (exceeds 30 days threshold)."
                    ))
    return sorted(issues, key=lambda x: x["affected_records"][0] if x["affected_records"] else "")

