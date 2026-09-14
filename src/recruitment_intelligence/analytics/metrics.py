"""Deterministic recruitment metrics.

The functions in this module intentionally operate on ordinary mappings and
sequences.  This keeps the calculation layer independent of Airtable and LLM
providers and makes an offline snapshot straightforward to replay.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

Record = Mapping[str, Any]
Tables = Mapping[str, Sequence[Record]]


def _flatten_record(row: Any) -> dict[str, Any]:
    """Flatten nested 'fields' while retaining top-level record attributes."""
    if hasattr(row, "to_dict"):
        row = row.to_dict()
    if not isinstance(row, Mapping):
        return {}
    values: dict[str, Any] = {}
    nested = row.get("fields")
    if isinstance(nested, Mapping):
        values.update({str(k): v for k, v in nested.items()})
    for k, v in row.items():
        if k == "fields":
            continue
        values[str(k)] = v
    if "id" not in values and "record_id" in values:
        values["id"] = values["record_id"]
    return values


def _flatten_tables(tables: Any) -> dict[str, list[dict[str, Any]]]:
    """Ensure all tables contain flattened records supporting both flat and nested envelopes."""
    if not isinstance(tables, Mapping):
        if isinstance(tables, Sequence):
            return {"Applications": [_flatten_record(r) for r in tables]}
        return {}
    result: dict[str, list[dict[str, Any]]] = {}
    for table_name, rows in tables.items():
        if isinstance(rows, Sequence):
            result[str(table_name)] = [_flatten_record(r) for r in rows]
        else:
            result[str(table_name)] = []
    return result


def _rows(tables: Tables | Sequence[Record], name: str = "Applications") -> list[dict[str, Any]]:
    if isinstance(tables, Mapping):
        for key, value in tables.items():
            if str(key).lower().replace("_", " ") == name.lower().replace("_", " "):
                return [_flatten_record(r) for r in value]
        return []
    return [_flatten_record(r) for r in tables]


def _value(row: Record, *names: str, default: Any = None) -> Any:
    flat = _flatten_record(row) if isinstance(row, Mapping) else {}
    lower = {str(k).lower().replace(" ", "_"): v for k, v in flat.items()}
    for name in names:
        key = name.lower().replace(" ", "_")
        if key in lower:
            return lower[key]
    return default


def _as_bool(value: Any, default: bool = False) -> bool:
    """Safely coerce boolean flags, handling boolean-like strings and numbers."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"true", "yes", "y", "1", "t", "accepted", "hired"}:
            return True
        if cleaned in {"false", "no", "n", "0", "f", "rejected", "declined", "withdrawn", ""}:
            return False
        return default
    return bool(value)


def _text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return _text(value[0], default) if value else default
    if isinstance(value, Mapping):
        return _text(value.get("name") or value.get("id"), default)
    return str(value).strip()


def _status(row: Record) -> str:
    return _text(_value(row, "status", "stage", "application_status")).lower().replace(" ", "_")


def _id(row: Record) -> str:
    return _text(_value(row, "id", "record_id", "application_id", "candidate_id"))


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _as_of(value: date | datetime | str | None) -> date:
    parsed = _date(value)
    return parsed or datetime.now(timezone.utc).date()


def _index(tables: Tables, name: str, key_names: tuple[str, ...] = ("id",)) -> dict[str, Record]:
    return {
        _text(_value(row, *key_names)): row
        for row in _rows(tables, name)
        if _text(_value(row, *key_names))
    }


def _linked_id(value: Any) -> str:
    return _text(value)


def table_counts(tables: Tables) -> dict[str, int]:
    """Return deterministic row counts for every supplied table."""
    return {str(name): len(rows) for name, rows in tables.items()}


def _offer_index(tables: Tables) -> dict[str, list[Record]]:
    result: dict[str, list[Record]] = defaultdict(list)
    for offer in _rows(tables, "Offers"):
        app = _text(_value(offer, "application_id", "application", "app_id"))
        candidate = _text(_value(offer, "candidate_id", "candidate"))
        if app:
            result[app].append(offer)
        elif candidate:
            result[f"candidate:{candidate}"].append(offer)
    return result



def _interview_ids(tables: Tables) -> set[str]:
    ids: set[str] = set()
    for item in _rows(tables, "Interviews"):
        for key in ("application_id", "application", "app_id"):
            value = _text(_value(item, key))
            if value:
                ids.add(value)
    return ids


def _is_hired(app: Record, candidate: Record | None = None) -> bool:
    app_st = _status(app)
    terminal_non_hire = {
        "rejected", "withdrawn", "closed", "declined", "archived",
        "offer_rejected", "offer_declined", "declined_offer",
    }
    if app_st in terminal_non_hire:
        return False
    if app_st in {"hired", "joined", "start", "started"}:
        return True
    return _as_bool(_value(app, "hired", "is_hired", "hire_outcome", default=False))


def _is_offer(app: Record, offers: list[Record]) -> bool:
    if offers:
        return True
    return _status(app) in {"offer", "offer_made", "accepted", "offer_accepted", "offer_rejected", "hired"}


def _is_interview(app: Record, interview_ids: set[str]) -> bool:
    return _id(app) in interview_ids or _status(app) in {
        "interview", "interviewing", "onsite", "offer", "accepted", "hired", "offer_accepted", "offer_rejected"
    }


def source_effectiveness(tables: Tables | Sequence[Record]) -> dict[str, dict[str, Any]]:
    """Calculate source funnel performance, conversion, effort touches, yield, and sinks."""
    apps = _rows(tables)
    candidates = _index(tables, "Candidates") if isinstance(tables, Mapping) else {}
    offers = _offer_index(tables) if isinstance(tables, Mapping) else {}
    interview_ids = _interview_ids(tables) if isinstance(tables, Mapping) else set()
    grouped: dict[str, list[Record]] = defaultdict(list)
    for app in apps:
        grouped[_text(_value(app, "source", "recruiting_source", "channel"), "Unknown") or "Unknown"].append(app)
    output: dict[str, dict[str, Any]] = {}
    for source in sorted(grouped):
        rows = grouped[source]
        interviews = offers_count = hires = 0
        role_mix: Counter[str] = Counter()
        for app in rows:
            appid = _id(app)
            cid = _linked_id(_value(app, "candidate_id", "candidate"))
            app_offers = offers.get(appid, []) or (offers.get(f"candidate:{cid}", []) if cid else [])
            if _is_interview(app, interview_ids):
                interviews += 1
            if _is_offer(app, app_offers):
                offers_count += 1
            if _is_hired(app):
                hires += 1
            role = _text(_value(app, "department", "role", "job_title", "job"), "Unknown") or "Unknown"
            role_mix[role] += 1
        n = len(rows)
        effort_touches = interviews + offers_count
        effort_yield = hires / effort_touches if effort_touches else 0.0
        effort_per_hire = effort_touches / hires if hires else None
        is_sink = hires == 0 and (n >= 2 or interviews >= 1)
        output[source] = {
            "applications": n,
            "interviews": interviews,
            "offers": offers_count,
            "hires": hires,
            "hire_conversion_rate": hires / n if n else 0.0,
            "offer_to_hire_rate": hires / offers_count if offers_count else 0.0,
            "sample_size": n,
            "role_mix": dict(sorted(role_mix.items())),
            "confidence": "high" if n >= 30 else "medium" if n >= 10 else "low",
            "effort_touches": effort_touches,
            "effort_yield": effort_yield,
            "effort_per_hire": effort_per_hire,
            "is_effort_sink": is_sink,
        }
    return output


def pipeline_effort_sinks(tables: Tables | Sequence[Record]) -> list[str]:
    """Identify sources that consume candidate or interview volume without producing hires."""
    sources = source_effectiveness(tables)
    sinks = [s for s, data in sources.items() if data.get("is_effort_sink", False)]
    return sorted(sinks, key=lambda s: (-sources[s]["effort_touches"], -sources[s]["applications"], s))


def offer_acceptance_rate(tables: Tables | Sequence[Record]) -> dict[str, Any]:
    """Return accepted offers divided by formal extended offers with an explicit denominator."""
    raw_offers = _rows(tables, "Offers") if isinstance(tables, Mapping) else []
    if not raw_offers and not isinstance(tables, Mapping):
        raw_offers = [r for r in tables if _status(r) in {"offer", "accepted", "offer_accepted", "offer_rejected"}]
    formal_offers = [
        o for o in raw_offers
        if _status(o) not in {"draft", "rescinded", "withdrawn_by_company", "internal_review"}
    ]
    accepted = 0
    for offer in formal_offers:
        status = _status(offer)
        accepted += int(
            status in {"accepted", "offer_accepted", "hired", "joined"}
            or _as_bool(_value(offer, "accepted", "is_accepted", default=False))
        )
    total = len(formal_offers)
    rate = accepted / total if total else 0.0
    conf = "high" if total >= 30 else "medium" if total >= 10 else "low"
    justification = (
        "Denominator defined as total formal offers extended in the Offers table, "
        "excluding draft or rescinded offers. Numerator counts affirmative candidate "
        "acceptances (status in {accepted, offer_accepted, hired, joined} or accepted=True)."
    )
    return {
        "accepted": accepted,
        "offers": total,
        "rate": rate,
        "confidence": conf,
        "denominator_justification": justification,
    }


def funnel_transitions(tables: Tables | Sequence[Record]) -> dict[str, int]:
    """Count applications in each canonical funnel stage."""
    apps = _rows(tables)
    aliases = {
        "applied": "applied", "application": "applied",
        "screen": "screening", "screening": "screening",
        "interviewing": "interview", "interview": "interview",
        "offer_made": "offer", "offer": "offer",
        "accepted": "accepted",
        "hired": "hired",
        "rejected": "rejected", "withdrawn": "withdrawn",
    }
    counts: Counter[str] = Counter()
    for app in apps:
        raw = _status(app)
        counts[aliases.get(raw, raw or "unknown")] += 1
    return dict(sorted(counts.items()))


def funnel_stage_conversions(tables: Tables | Sequence[Record]) -> dict[str, Any]:
    """Compute sequential pass-through conversion percentages and bottleneck stage."""
    apps = _rows(tables, "Applications")
    if not apps:
        return {
            "stages": {},
            "transitions": {},
            "bottleneck": "Unknown — insufficient evidence",
        }

    interview_ids = _interview_ids(tables) if isinstance(tables, Mapping) else set()
    offer_rows = _rows(tables, "Offers") if isinstance(tables, Mapping) else []
    offer_apps = {
        _text(_value(o, "application_id", "application", "app_id"))
        for o in offer_rows
        if _text(_value(o, "application_id", "application", "app_id"))
    }
    accepted_offer_apps = {
        _text(_value(o, "application_id", "application", "app_id"))
        for o in offer_rows
        if _text(_value(o, "application_id", "application", "app_id"))
        and (
            _status(o) in {"accepted", "offer_accepted", "hired", "joined"}
            or _as_bool(_value(o, "accepted", "is_accepted", default=False))
        )
    }

    stage_order = ("applied", "screening", "interview", "offer", "accepted", "hired")
    reached = {s: 0 for s in stage_order}

    for app in apps:
        st = _status(app)
        aid = _id(app)
        is_h = _is_hired(app)
        reached["applied"] += 1
        if (
            st in {"screening", "interview", "interviewing", "onsite", "offer", "offer_made", "accepted", "hired"}
            or aid in interview_ids
            or aid in offer_apps
            or is_h
        ):
            reached["screening"] += 1
        if (
            st in {"interview", "interviewing", "onsite", "offer", "offer_made", "accepted", "hired"}
            or aid in interview_ids
            or aid in offer_apps
            or is_h
        ):
            reached["interview"] += 1
        if st in {"offer", "offer_made", "accepted", "hired"} or aid in offer_apps or is_h:
            reached["offer"] += 1
        if st in {"accepted", "hired"} or aid in accepted_offer_apps or is_h:
            reached["accepted"] += 1
        if is_h:
            reached["hired"] += 1

    transitions_list = [
        ("applied", "screening"),
        ("screening", "interview"),
        ("interview", "offer"),
        ("offer", "accepted"),
        ("accepted", "hired"),
    ]

    transitions: dict[str, dict[str, Any]] = {}
    bottleneck_stage = "Unknown — insufficient evidence"
    max_drop_rate = -1.0

    for from_stage, to_stage in transitions_list:
        denom = reached[from_stage]
        num = reached[to_stage]
        rate = num / denom if denom > 0 else 0.0
        drop_rate = (1.0 - rate) if denom > 0 else 0.0
        trans_key = f"{from_stage}_to_{to_stage}"
        transitions[trans_key] = {
            "from_stage": from_stage,
            "to_stage": to_stage,
            "numerator": num,
            "denominator": denom,
            "conversion_rate": rate,
            "drop_off_rate": drop_rate,
        }
        if denom > 0 and drop_rate > max_drop_rate:
            max_drop_rate = drop_rate
            bottleneck_stage = trans_key

    return {
        "stages": reached,
        "transitions": transitions,
        "bottleneck": bottleneck_stage,
    }


def funnel_bottleneck(tables: Tables | Sequence[Record]) -> str:
    """Identify the funnel transition with the highest drop-off rate."""
    return str(funnel_stage_conversions(tables)["bottleneck"])



def stalled_applications(tables: Tables | Sequence[Record], threshold_days: int = 14, as_of: date | datetime | str | None = None) -> list[dict[str, Any]]:
    """List active applications with no update for ``threshold_days`` days."""
    today = _as_of(as_of)
    result = []
    terminal = {"hired", "rejected", "withdrawn", "closed", "accepted"}
    for app in _rows(tables):
        if _status(app) in terminal:
            continue
        updated = _date(_value(app, "updated_at", "last_activity", "last_updated", "applied_at", "application_date", "created_at"))
        if updated is None:
            continue
        age = (today - updated).days
        if age >= threshold_days:
            result.append({"application_id": _id(app), "candidate_id": _linked_id(_value(app, "candidate_id", "candidate")), "status": _status(app) or "unknown", "days_stalled": age})
    return sorted(result, key=lambda item: (-item["days_stalled"], item["application_id"]))


def aging(tables: Tables | Sequence[Record], as_of: date | datetime | str | None = None) -> list[dict[str, Any]]:
    """Return application age records, excluding rows with invalid dates."""
    today = _as_of(as_of)
    result = []
    for app in _rows(tables):
        applied = _date(_value(app, "applied_at", "application_date", "created_at", "date_applied"))
        if applied is None:
            continue
        result.append({"application_id": _id(app), "candidate_id": _linked_id(_value(app, "candidate_id", "candidate")), "age_days": max(0, (today - applied).days), "status": _status(app) or "unknown"})
    return sorted(result, key=lambda item: (-item["age_days"], item["application_id"]))


def source_department_segmentation(tables: Tables) -> dict[str, dict[str, dict[str, Any]]]:
    """Return source metrics split by department/role."""
    apps = _rows(tables)
    segments: dict[str, dict[str, list[Record]]] = defaultdict(lambda: defaultdict(list))
    for app in apps:
        source = _text(_value(app, "source", "recruiting_source", "channel"), "Unknown") or "Unknown"
        dept = _text(_value(app, "department", "role", "job_title", "job"), "Unknown") or "Unknown"
        segments[source][dept].append(app)
    return {source: {dept: source_effectiveness(rows).get(source, source_effectiveness(rows).get("Unknown", {})) for dept, rows in sorted(depts.items())} for source, depts in sorted(segments.items())}


def sensitivity_analysis(tables: Tables, exclusions: Mapping[str, Iterable[str]] | None = None) -> dict[str, Any]:
    """Compare baseline source metrics with deterministic record exclusions."""
    baseline = source_effectiveness(tables)
    scenarios: dict[str, Any] = {}
    for name, ids in (exclusions or {}).items():
        excluded = {str(item) for item in ids}
        filtered = {table: [row for row in rows if _id(row) not in excluded] for table, rows in tables.items()}
        scenarios[str(name)] = source_effectiveness(filtered)
    return {"baseline": baseline, "scenarios": scenarios}

