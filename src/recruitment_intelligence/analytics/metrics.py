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
    stage = _text(_value(app, "stage")).lower().replace(" ", "_")
    if stage in {"hired", "joined", "start", "started", "offer_accepted"}:
        return True
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
    candidates: dict[str, Record] = {}
    if isinstance(tables, Mapping):
        for c in _rows(tables, "Candidates"):
            rid = _text(_value(c, "id", "record_id"))
            cid = _text(_value(c, "candidate_id"))
            if rid:
                candidates[rid] = c
            if cid:
                candidates[cid] = c
    offers = _offer_index(tables) if isinstance(tables, Mapping) else {}
    interview_ids = _interview_ids(tables) if isinstance(tables, Mapping) else set()

    app_interviews: dict[str, list[Record]] = defaultdict(list)
    if isinstance(tables, Mapping):
        for iv in _rows(tables, "Interviews"):
            aid = _text(_value(iv, "application_id", "application", "app_id"))
            if aid:
                app_interviews[aid].append(iv)

    app_offers_map: dict[str, list[Record]] = defaultdict(list)
    if isinstance(tables, Mapping):
        for off in _rows(tables, "Offers"):
            aid = _text(_value(off, "application_id", "application", "app_id"))
            cid = _text(_value(off, "candidate_id", "candidate"))
            if aid:
                app_offers_map[aid].append(off)
            elif cid:
                app_offers_map[f"candidate:{cid}"].append(off)

    grouped: dict[str, list[Record]] = defaultdict(list)
    for app in apps:
        source = _text(_value(app, "source", "recruiting_source", "channel"))
        if not source or source.lower() == "unknown":
            cid = _linked_id(_value(app, "candidate_id", "candidate"))
            cand = candidates.get(cid)
            source = _text(_value(cand, "source", "recruiting_source", "channel")) if cand else "Unknown"
        grouped[source or "Unknown"].append(app)
    output: dict[str, dict[str, Any]] = {}
    for source in sorted(grouped):
        rows = grouped[source]
        interviews = offers_count = hires = 0
        role_mix: Counter[str] = Counter()
        for app in rows:
            appid = _id(app)
            cid = _linked_id(_value(app, "candidate_id", "candidate"))
            app_offers = app_offers_map.get(appid, []) or (app_offers_map.get(f"candidate:{cid}", []) if cid else []) or offers.get(appid, []) or (offers.get(f"candidate:{cid}", []) if cid else [])
            if appid in app_interviews:
                interviews += len(app_interviews[appid])
            elif _is_interview(app, interview_ids):
                interviews += 1
            if app_offers:
                offers_count += len(app_offers)
            elif _is_offer(app, []):
                offers_count += 1
            if _is_hired(app):
                hires += 1
            role = _text(_value(app, "department", "role", "job_title", "job"), "Unknown") or "Unknown"
            role_mix[role] += 1
        n = len(rows)
        effort_touches = interviews + offers_count
        effort_yield = hires / effort_touches if effort_touches else 0.0
        effort_per_hire = (interviews / hires) if hires else None
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
            "interviews_per_hire": effort_per_hire,
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
        updated = _date(_value(app, "updated_at", "last_activity", "last_updated", "applied_at", "applied_on", "application_date", "created_at"))
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
        applied = _date(_value(app, "applied_at", "application_date", "created_at", "date_applied", "applied_on"))
        if applied is None:
            continue
        result.append({"application_id": _id(app), "candidate_id": _linked_id(_value(app, "candidate_id", "candidate")), "age_days": max(0, (today - applied).days), "status": _status(app) or "unknown"})
    return sorted(result, key=lambda item: (-item["age_days"], item["application_id"]))


def source_department_segmentation(tables: Tables) -> dict[str, dict[str, dict[str, Any]]]:
    """Return source metrics split by department/role."""
    apps = _rows(tables)
    candidates: dict[str, Record] = {}
    if isinstance(tables, Mapping):
        for c in _rows(tables, "Candidates"):
            rid = _text(_value(c, "id", "record_id"))
            cid = _text(_value(c, "candidate_id"))
            if rid:
                candidates[rid] = c
            if cid:
                candidates[cid] = c
    openings: dict[str, Record] = {}
    if isinstance(tables, Mapping):
        for o in _rows(tables, "Job Openings"):
            oid = _text(_value(o, "id", "record_id", "req_id"))
            if oid:
                openings[oid] = o
    segments: dict[str, dict[str, list[Record]]] = defaultdict(lambda: defaultdict(list))
    for app in apps:
        source = _text(_value(app, "source", "recruiting_source", "channel"))
        if not source or source.lower() == "unknown":
            cid = _linked_id(_value(app, "candidate_id", "candidate"))
            cand = candidates.get(cid)
            source = _text(_value(cand, "source", "recruiting_source", "channel")) if cand else "Unknown"
        source = source or "Unknown"
        dept = _text(_value(app, "department", "role", "job_title", "job"))
        if not dept or dept == "Unknown":
            op_id = _linked_id(_value(app, "opening", "opening_id", "job_id"))
            op = openings.get(op_id)
            dept = _text(_value(op, "department", "title", "role"), "Unknown") if op else "Unknown"
        dept = dept or "Unknown"
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


def recruiter_interviewer_bandwidth(tables: Tables) -> dict[str, Any]:
    """Analyze hiring workload and velocity across internal recruiters and interviewers."""
    people: dict[str, str] = {}
    for p in _rows(tables, "People"):
        pid = _text(_value(p, "id", "record_id"))
        p_cid = _text(_value(p, "person_id"))
        name = _text(_value(p, "full_name", "name"))
        if pid:
            people[pid] = name
        if p_cid:
            people[p_cid] = name

    # Recruiter load from Applications
    recruiter_apps: Counter[str] = Counter()
    for app in _rows(tables, "Applications"):
        for r in _value(app, "recruiter", "recruiter_id", default=[]) or []:
            r_str = _text(r)
            r_name = people.get(r_str, r_str)
            if r_name:
                recruiter_apps[r_name] += 1

    # Interviewer load and scores from Interviews
    interviewer_counts: Counter[str] = Counter()
    interviewer_scores: dict[str, list[float]] = defaultdict(list)
    interviews = _rows(tables, "Interviews")
    for iv in interviews:
        score_val = _value(iv, "score", "rating")
        for i in _value(iv, "interviewer", "interviewer_id", default=[]) or []:
            i_str = _text(i)
            i_name = people.get(i_str, i_str)
            if i_name:
                interviewer_counts[i_name] += 1
                if score_val is not None:
                    try:
                        interviewer_scores[i_name].append(float(score_val))
                    except (ValueError, TypeError):
                        pass

    interviewer_avg_scores = {
        name: round(sum(scores) / len(scores), 2)
        for name, scores in interviewer_scores.items()
        if scores
    }

    total_interviews = len(interviews)
    sorted_interviewers = sorted(interviewer_counts.items(), key=lambda x: (-x[1], x[0]))
    top_two = sum(cnt for _, cnt in sorted_interviewers[:2])
    top_two_share = (top_two / total_interviews) if total_interviews else 0.0

    strictest = min(interviewer_avg_scores.items(), key=lambda x: (x[1], x[0]))[0] if interviewer_avg_scores else ""

    return {
        "recruiter_load": dict(sorted(recruiter_apps.items(), key=lambda x: (-x[1], x[0]))),
        "interviewer_load": dict(sorted_interviewers),
        "interviewer_avg_scores": dict(sorted(interviewer_avg_scores.items(), key=lambda x: (x[1], x[0]))),
        "top_two_interviewer_share": top_two_share,
        "strictest_interviewer": strictest,
        "total_interviews": total_interviews,
    }


def compensation_competitiveness(tables: Tables, as_of: date | datetime | str | None = None) -> dict[str, Any]:
    """Contrast offered compensation against candidate expectations and salary bands."""
    today = _as_of(as_of)
    offers = _rows(tables, "Offers")
    apps = {_id(a): a for a in _rows(tables, "Applications")}
    openings = {_id(o): o for o in _rows(tables, "Job Openings")}
    candidates: dict[str, Record] = {}
    for c in _rows(tables, "Candidates"):
        rid = _text(_value(c, "id", "record_id"))
        cid = _text(_value(c, "candidate_id"))
        if rid:
            candidates[rid] = c
        if cid:
            candidates[cid] = c

    violations: list[dict[str, Any]] = []
    stale_pending: list[dict[str, Any]] = []
    decline_reasons: Counter[str] = Counter()

    for off in offers:
        off_id = _id(off)
        status = _text(_value(off, "status")).lower()
        base = _value(off, "base_ctc", "salary", "base_salary")
        try:
            base_val = float(base) if base is not None else None
        except (ValueError, TypeError):
            base_val = None

        app_ref = _text(_value(off, "application_id", "application", "app_id"))
        app = apps.get(app_ref, {})
        op_ref = _text(_value(app, "opening", "opening_id", "job_id", "job_opening"))
        op = openings.get(op_ref, {})
        cand_ref = _linked_id(_value(app, "candidate_id", "candidate")) or _linked_id(_value(off, "candidate_id", "candidate"))
        cand = candidates.get(cand_ref, {})

        b_min = _value(op, "salary_band_min", "band_min", "min_salary")
        b_max = _value(op, "salary_band_max", "band_max", "max_salary")

        cand_name = _text(_value(cand, "full_name", "name"))
        role_title = _text(_value(op, "title", "role"))

        if base_val is not None and b_max is not None:
            try:
                b_max_val = float(b_max)
                if base_val > b_max_val:
                    pct = (base_val - b_max_val) / b_max_val * 100
                    violations.append({
                        "offer_id": off_id,
                        "candidate_name": cand_name,
                        "role": role_title,
                        "base_offered": base_val,
                        "band_max": b_max_val,
                        "deviation_pct": pct,
                        "type": "over_max",
                    })
            except (ValueError, TypeError):
                pass

        if base_val is not None and b_min is not None:
            try:
                b_min_val = float(b_min)
                if base_val < b_min_val:
                    pct = (base_val - b_min_val) / b_min_val * 100
                    violations.append({
                        "offer_id": off_id,
                        "candidate_name": cand_name,
                        "role": role_title,
                        "base_offered": base_val,
                        "band_min": b_min_val,
                        "deviation_pct": pct,
                        "type": "below_min",
                    })
            except (ValueError, TypeError):
                pass

        if status == "pending":
            off_date = _date(_value(off, "offered_on", "offered_at", "created_at"))
            age_days = (today - off_date).days if off_date else None
            stale_pending.append({
                "offer_id": off_id,
                "candidate_id": cand_ref,
                "candidate_name": cand_name,
                "role": role_title,
                "offered_on": off_date.isoformat() if off_date else None,
                "age_days": age_days,
            })

        if status in {"declined", "rejected"}:
            reason = _text(_value(off, "decline_reason", "reason"), default="Unknown") or "Unknown"
            decline_reasons[reason] += 1

    total_declined = sum(decline_reasons.values())
    decline_reason_pcts = {
        r: (cnt / total_declined) if total_declined else 0.0
        for r, cnt in decline_reasons.items()
    }

    return {
        "salary_band_violations": sorted(violations, key=lambda x: (-abs(x["deviation_pct"]), str(x.get("offer_id") or ""))),
        "stale_pending_offers": sorted(stale_pending, key=lambda x: (-(x["age_days"] or 0), str(x.get("offer_id") or ""))),
        "decline_reasons": dict(sorted(decline_reasons.items(), key=lambda x: (-x[1], x[0]))),
        "decline_reason_pcts": dict(sorted(decline_reason_pcts.items(), key=lambda x: (-x[1], x[0]))),
    }


def time_to_hire_by_source(tables: Tables) -> dict[str, Any]:
    """Benchmark duration from Applied On to Offered On and Closed On across sources."""
    apps = _rows(tables, "Applications")
    candidates: dict[str, Record] = {}
    for c in _rows(tables, "Candidates"):
        rid = _text(_value(c, "id", "record_id"))
        cid = _text(_value(c, "candidate_id"))
        if rid:
            candidates[rid] = c
        if cid:
            candidates[cid] = c

    offers_by_app: dict[str, Record] = {}
    for o in _rows(tables, "Offers"):
        aid = _text(_value(o, "application_id", "application", "app_id"))
        if aid:
            offers_by_app[aid] = o

    time_to_offer: dict[str, list[int]] = defaultdict(list)
    time_to_hire: dict[str, list[int]] = defaultdict(list)

    for app in apps:
        if not _is_hired(app):
            continue
        cid = _linked_id(_value(app, "candidate_id", "candidate"))
        cand = candidates.get(cid)
        source = _text(_value(app, "source", "recruiting_source", "channel"))
        if not source or source.lower() == "unknown":
            source = _text(_value(cand, "source", "recruiting_source", "channel")) if cand else "Unknown"
        source = source or "Unknown"

        app_date = _date(_value(app, "applied_on", "applied_at", "application_date", "created_at"))
        if not app_date:
            continue

        aid = _id(app)
        off = offers_by_app.get(aid)
        if off:
            off_date = _date(_value(off, "offered_on", "offered_at"))
            if off_date:
                time_to_offer[source].append(max(0, (off_date - app_date).days))
            dec_date = _date(_value(off, "decision_on", "closed_on", "responded_at"))
            if dec_date:
                time_to_hire[source].append(max(0, (dec_date - app_date).days))

    avg_time_to_offer = {
        s: round(sum(vals) / len(vals), 1)
        for s, vals in sorted(time_to_offer.items())
        if vals
    }
    avg_time_to_hire = {
        s: round(sum(vals) / len(vals), 1)
        for s, vals in sorted(time_to_hire.items())
        if vals
    }

    return {
        "avg_days_to_offer": avg_time_to_offer,
        "avg_days_to_hire": avg_time_to_hire,
    }


def departmental_headcount_fill_rate(tables: Tables) -> dict[str, Any]:
    """Compare headcount budget and req targets against actual offers and hires across departments."""
    depts: dict[str, str] = {}
    dept_names: dict[str, str] = {}
    dept_budgets: dict[str, int] = {}
    for d in _rows(tables, "Departments"):
        d_id = _id(d)
        d_code = _text(_value(d, "code", "department_code")) or d_id
        d_name = _text(_value(d, "name", "department_name")) or d_code
        try:
            budget = int(_value(d, "headcount_budget", "budget", default=0) or 0)
        except (ValueError, TypeError):
            budget = 0
        if d_id:
            depts[d_id] = d_code
            dept_names[d_code] = d_name
            dept_budgets[d_code] = budget
        if d_code:
            depts[d_code] = d_code
            dept_names[d_code] = d_name
            dept_budgets[d_code] = budget

    openings: dict[str, dict[str, Any]] = {}
    dept_req_targets: dict[str, int] = defaultdict(int)
    for o in _rows(tables, "Job Openings"):
        oid = _id(o)
        d_ref = _text(_value(o, "department", "department_id"))
        d_code = depts.get(d_ref, d_ref) or "Unknown"
        try:
            hc = int(_value(o, "headcount", "headcount_target", default=1) or 1)
        except (ValueError, TypeError):
            hc = 1
        openings[oid] = {"department_code": d_code, "headcount": hc}
        dept_req_targets[d_code] += hc

    apps = {_id(a): a for a in _rows(tables, "Applications")}
    dept_offers: dict[str, int] = defaultdict(int)
    dept_hires: dict[str, int] = defaultdict(int)

    for off in _rows(tables, "Offers"):
        app_ref = _text(_value(off, "application_id", "application", "app_id"))
        app = apps.get(app_ref, {})
        op_ref = _text(_value(app, "opening", "opening_id", "job_id"))
        op_info = openings.get(op_ref, {})
        d_code = op_info.get("department_code") or "Unknown"
        dept_offers[d_code] += 1
        st = _text(_value(off, "status")).lower()
        if st in {"accepted", "hired", "joined"}:
            dept_hires[d_code] += 1

    terminal = {"hired", "rejected", "withdrawn", "closed", "accepted"}
    dept_active: dict[str, int] = defaultdict(int)
    for app in _rows(tables, "Applications"):
        if _status(app) not in terminal:
            op_ref = _text(_value(app, "opening", "opening_id", "job_id"))
            op_info = openings.get(op_ref, {})
            d_code = op_info.get("department_code") or "Unknown"
            dept_active[d_code] += 1

    summary: dict[str, dict[str, Any]] = {}
    all_dept_codes = sorted(set(list(dept_budgets.keys()) + list(dept_req_targets.keys())))
    for code in all_dept_codes:
        if not code or code == "Unknown":
            continue
        req_hc = dept_req_targets.get(code, 0)
        hires = dept_hires.get(code, 0)
        offers_cnt = dept_offers.get(code, 0)
        fill_rate = (hires / req_hc) if req_hc > 0 else 0.0
        summary[code] = {
            "department_code": code,
            "department_name": dept_names.get(code, code),
            "headcount_budget": dept_budgets.get(code, 0),
            "req_headcount_target": req_hc,
            "offers_extended": offers_cnt,
            "hires_made": hires,
            "fill_rate": fill_rate,
            "fill_rate_pct": fill_rate * 100,
            "active_pipeline": dept_active.get(code, 0),
        }

    return summary

