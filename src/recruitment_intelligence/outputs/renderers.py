"""Stable JSON, CSV, Markdown, and HTML output renderers.

The module performs presentation only.  It never computes a metric and never
turns a quality warning into a positive claim.  Inputs may be frozen domain
contracts or dictionaries loaded from an earlier run.
"""

from __future__ import annotations

import csv
import html
import io
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..domain import Briefing, CandidateRecommendation, Finding


def _dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        result = value.to_dict()
    elif isinstance(value, Mapping):
        result = dict(value)
    else:
        raise TypeError(f"expected a domain contract or mapping, got {type(value).__name__}")
    return result


def _items(values: Iterable[Any] | None) -> list[dict[str, Any]]:
    return [_dict(value) for value in (values or ())]


def _json(value: Any) -> str:
    """Canonical JSON for reproducible artifacts."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _scalar(value: Any) -> Any:
    """Return enum values as their contract wire representation."""
    return getattr(value, "value", value)


def _evidence_text(item: Mapping[str, Any]) -> str:
    source = str(item.get("source", "unknown"))
    table = item.get("table")
    method = item.get("method")
    refs = item.get("record_ids") or item.get("records") or ()
    suffix = f" ({table})" if table else ""
    if refs:
        suffix += f" records: {', '.join(str(v) for v in refs)}"
    if method:
        suffix += f"; method: {method}"
    return source + suffix


def _finding_rows(findings: Sequence[Any]) -> list[dict[str, Any]]:
    rows = []
    for finding in _items(findings):
        # Keep all contract fields in JSON while exposing useful CSV columns.
        evidence = finding.get("evidence", ())
        rec = finding.get("recommendation") or (
            " | ".join(str(r) for r in finding.get("recommendations", ()))
            if finding.get("recommendations")
            else ""
        )
        interp = finding.get("interpretation") or finding.get("description") or ""
        rows.append(
            {
                "finding_id": finding.get("finding_id", finding.get("id", "")),
                "title": finding.get("title", ""),
                "observed_fact": finding.get("observed_fact", finding.get("claim", "")),
                "interpretation": interp,
                "recommendation": rec,
                "confidence": str(_scalar(finding.get("confidence", "insufficient"))),
                "severity": str(_scalar(finding.get("severity", "medium"))),
                "caveats": " | ".join(str(v) for v in finding.get("caveats", ())),
                "evidence": " | ".join(_evidence_text(_dict(e)) for e in evidence),
            }
        )
    return sorted(rows, key=lambda row: (str(row["severity"]), str(row["finding_id"]), str(row["title"])))


def _warning_dict(warning: Any) -> dict[str, Any]:
    """Extract standard warning fields from either raw dicts or Finding contracts."""
    w = _dict(warning)
    severity = str(_scalar(w.get("severity", "medium")))
    check = str(w.get("check") or w.get("category") or "data_quality")
    evidence = w.get("evidence", ())
    first_ev = _dict(evidence[0]) if evidence and isinstance(evidence, (list, tuple)) and len(evidence) > 0 else {}
    table = str(w.get("table") or first_ev.get("table") or "Airtable")
    field_val = w.get("field")
    # Preserve 'title' separately from 'message' (observed_fact) for HTML rendering.
    title = str(w.get("title") or "")
    message = str(w.get("message") or w.get("observed_fact") or title or "")

    metric_impact = w.get("metric_impact")
    if not metric_impact and w.get("caveats"):
        caveats = w.get("caveats", ())
        metric_impact = [str(c).replace("Metric impact: ", "") for c in caveats if "Metric impact" in str(c)]
    if not metric_impact and w.get("interpretation"):
        metric_impact = [str(w.get("interpretation"))]
    if not metric_impact:
        metric_impact = []

    return {
        "check": check,
        "severity": severity,
        "table": table,
        "field": field_val,
        "title": title,
        "message": message,
        "metric_impact": list(metric_impact),
        "affected_records": list(w.get("affected_records", first_ev.get("record_ids", ()))),
    }


def render_findings_json(findings: Sequence[Any], quality_warnings: Sequence[Any] | None = None) -> str:
    """Render findings and quality warnings as canonical JSON."""
    payload = {
        "findings": [_dict(v) for v in findings],
        "quality_warnings": [_dict(v) for v in (quality_warnings or ())],
    }
    return _json(payload)


def render_findings_csv(findings: Sequence[Any]) -> str:
    """Render a stable, flat CSV suitable for spreadsheet review."""
    columns = ["finding_id", "title", "observed_fact", "interpretation", "recommendation", "confidence", "severity", "caveats", "evidence"]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(_finding_rows(findings))
    return stream.getvalue()


def render_findings_markdown(findings: Sequence[Any], quality_warnings: Sequence[Any] | None = None) -> str:
    """Render findings while retaining fact/interpretation/action boundaries."""
    rows = _finding_rows(findings)
    lines = ["# Recruitment findings", "", "Each item separates observed facts from interpretation and advisory action.", ""]
    if not rows:
        lines.append("_No findings were produced for this run._\n")
    for row in rows:
        lines.extend(
            [
                f"## {row['title']} (`{row['finding_id']}`)",
                "",
                f"- **Observed fact:** {row['observed_fact']}",
                f"- **Interpretation:** {row['interpretation'] or 'Not provided'}",
                f"- **Recommendation:** {row['recommendation'] or 'No recommendation'}",
                f"- **Confidence:** {row['confidence']}  ",
                f"- **Severity:** {row['severity']}",
                f"- **Caveat:** {row['caveats'] or 'None recorded'}",
                f"- **Evidence:** {row['evidence'] or 'No evidence reference (should be reviewed)'}",
                "",
            ]
        )
    warnings = [_warning_dict(v) for v in (quality_warnings or ())]
    lines.extend(["## Data-quality warnings", ""])
    if not warnings:
        lines.append("_No data-quality warnings were reported._\n")
    else:
        for warning in sorted(warnings, key=lambda x: (str(x.get("severity", "")), str(x.get("check", "")))):
            loc = f"{warning.get('table', 'unknown')}.{warning.get('field')}" if warning.get('field') else warning.get('table', 'unknown')
            impact_str = ", ".join(map(str, warning.get('metric_impact', ()))) or 'unspecified'
            lines.append(
                f"- **{warning.get('severity', 'unknown')}** `{warning.get('check', 'quality')}` "
                f"({loc}) — {warning.get('message', '')}; "
                f"metric impact: {impact_str}"
            )
        lines.append("")
    return "\n".join(lines)


def build_candidate_action_queue(recommendations: Sequence[Any]) -> list[dict[str, Any]]:
    """Return advisory candidate actions in urgency priority order."""
    action_priority = {
        "escalate": 0,
        "request_feedback": 1,
        "advance": 2,
        "review": 3,
        "close": 4,
    }
    queue = []
    for item in recommendations:
        rec = _dict(item)
        rec["requires_human_review"] = True  # domain contract enforces this too
        rec["human_review_note"] = "Advisory only: a founder or hiring manager must conduct human review before action."
        queue.append(rec)
    return sorted(
        queue,
        key=lambda x: (
            action_priority.get(str(x.get("action", "")).lower(), 99),
            str(x.get("action", "")),
            str(x.get("candidate_id", "")),
        ),
    )


def _quality_lines(warnings: Sequence[Any]) -> list[str]:
    if not warnings:
        return ["No data-quality warnings were reported."]
    lines = []
    for w in (_warning_dict(v) for v in warnings):
        impact_str = ", ".join(map(str, w.get('metric_impact', ()))) or 'unspecified'
        lines.append(f"{w.get('severity', 'unknown').upper()}: {w.get('message', '')} (impact: {impact_str})")
    return lines


def render_memo(
    findings: Sequence[Any],
    quality_warnings: Sequence[Any] | None = None,
    *,
    previous_run: Mapping[str, Any] | None = None,
    cost_appendix: str | None = None,
) -> str:
    """Render a concise one-page memo with explicit evidence and caveats."""
    lines = ["# Recruitment intelligence memo", "", "## Executive summary", ""]
    rows = _finding_rows(findings)
    lines.append(f"{len(rows)} validated finding(s) are available. Candidate actions remain advisory and require human review.")
    if previous_run:
        changes = compare_previous_run({"findings": list(findings)}, previous_run)
        lines.append(f"Previous-run comparison: {len(changes['added'])} added, {len(changes['changed'])} changed, {len(changes['removed'])} removed.")
    lines.extend(["", "## Findings", ""])
    if rows:
        for row in rows:
            lines.extend([f"### {row['title']}", f"**Observed fact:** {row['observed_fact']}", f"**Interpretation:** {row['interpretation'] or 'Not provided'}", f"**Recommendation:** {row['recommendation'] or 'No recommendation'}", f"**Confidence:** {row['confidence']}", f"**Caveat:** {row['caveats'] or 'None recorded'}", f"**Evidence:** {row['evidence'] or 'Missing evidence reference'}", ""])
    else:
        lines.append("_No findings were produced._\n")
    lines.extend(["## Data trust", ""] + [f"- {line}" for line in _quality_lines(quality_warnings or ())] + ["", "## Next action", "", "Review each recommendation with the hiring owner; no candidate should be rejected automatically.", ""])
    if cost_appendix:
        lines.extend(["## External cost research appendix (strictly isolated)", "", str(cost_appendix), ""])
    return "\n".join(lines)


def _briefing_dict(briefing: Any) -> dict[str, Any]:
    return _dict(briefing)


def render_briefing_json(briefing: Any) -> str:
    return _json(_briefing_dict(briefing))


def render_briefing_markdown(briefing: Any) -> str:
    data = _briefing_dict(briefing)
    lines = [f"# Daily recruitment briefing — {data.get('period', '')}", "", f"Generated: {data.get('generated_at', '')} | Confidence: {data.get('confidence', 'insufficient')}", "", "## What changed", ""]
    lines.extend(f"- {v}" for v in data.get("what_changed", ()) or ["No validated changes reported."])
    lines.extend(["", "## Urgent items", ""])
    lines.extend(f"- {v}" for v in data.get("urgent_items", ()) or ["Nothing urgent was reported."])
    lines.extend(["", "## Findings", ""])
    lines.append(render_findings_markdown(data.get("findings", ()), data.get("quality_warnings", ())).split("\n", 1)[-1])
    lines.extend(["", "## Candidate action queue", ""])
    actions = build_candidate_action_queue(data.get("candidate_actions", ()))
    if actions:
        lines.extend(f"- `{a.get('candidate_id')}` — **{a.get('action')}**: {a.get('rationale')} (human review required; confidence: {a.get('confidence', 'insufficient')})" for a in actions)
    else:
        lines.append("_No candidate actions were recommended._")
    lines.extend(["", "## Next actions", ""])
    lines.extend(f"- {v}" for v in data.get("next_actions", ()) or ["Review the validated findings with hiring owners."])
    if data.get("cost_appendix"):
        lines.extend(["", "## External cost research appendix (strictly isolated)", "", str(data["cost_appendix"])])
    return "\n".join(lines) + "\n"


def render_briefing_html(briefing: Any) -> str:
    """Render a dependency-free HTML briefing with escaped user/data content."""
    data = _briefing_dict(briefing)
    esc = lambda value: html.escape(str(value))
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Daily recruitment briefing</title></head><body>",
        f"<h1>Daily recruitment briefing — {esc(data.get('period', ''))}</h1>",
        f"<p>Generated: {esc(data.get('generated_at', ''))} | Confidence: {esc(data.get('confidence', 'insufficient'))}</p>",
    ]
    for title, key in (("What changed", "what_changed"), ("Urgent items", "urgent_items")):
        parts.append(f"<h2>{title}</h2><ul>")
        values = data.get(key, ()) or ["None reported."]
        parts.extend(f"<li>{esc(value)}</li>" for value in values)
        parts.append("</ul>")

    # Findings
    parts.append("<h2>Findings</h2><ul>")
    findings = data.get("findings", ())
    if findings:
        for f in findings:
            fd = _dict(f)
            title = esc(fd.get("title", ""))
            fact = esc(fd.get("observed_fact", ""))
            rec_val = fd.get("recommendation") or (fd.get("recommendations", [""])[0] if fd.get("recommendations") else "")
            rec = esc(rec_val or "None")
            sev = esc(_scalar(fd.get("severity", "medium")))
            conf = esc(_scalar(fd.get("confidence", "insufficient")))
            parts.append(f"<li><strong>{title}</strong>: {fact} <em>(Severity: {sev}, Confidence: {conf}, Recommendation: {rec})</em></li>")
    else:
        parts.append("<li><em>No findings produced.</em></li>")
    parts.append("</ul>")

    # Data Quality Warnings
    parts.append("<h2>Data-quality warnings</h2><ul>")
    warnings = data.get("quality_warnings", ())
    if warnings:
        for w in warnings:
            wd = _warning_dict(w)
            loc = f"{wd['table']}.{wd['field']}" if wd.get('field') else wd['table']
            impact_str = ", ".join(wd['metric_impact']) or 'unspecified'
            title_prefix = f"<strong>{esc(wd['title'])}</strong>: " if wd.get('title') else ""
            parts.append(
                f"<li><strong>{esc(wd['severity'].upper())}</strong> [{esc(wd['check'])}] ({esc(loc)}) — "
                f"{title_prefix}{esc(wd['message'])} <em>(Impact: {esc(impact_str)})</em></li>"
            )
    else:
        parts.append("<li><em>No data-quality warnings were reported.</em></li>")
    parts.append("</ul>")

    parts.append("<h2>Candidate action queue</h2><ul>")
    actions = build_candidate_action_queue(data.get("candidate_actions", ()))
    if actions:
        for action in actions:
            parts.append(f"<li><code>{esc(action.get('candidate_id'))}</code> — <strong>{esc(action.get('action'))}</strong>: {esc(action.get('rationale'))} (human review required)</li>")
    else:
        parts.append("<li><em>No candidate actions were recommended.</em></li>")
    parts.append("</ul>")

    parts.append("<h2>Next actions</h2><ul>")
    next_acts = data.get("next_actions", ()) or ["None reported."]
    parts.extend(f"<li>{esc(na)}</li>" for na in next_acts)
    parts.append("</ul>")

    if data.get("cost_appendix"):
        parts.append(f"<h2>External cost research appendix (strictly isolated)</h2><pre>{esc(data['cost_appendix'])}</pre>")
    parts.append("</body></html>")
    return "".join(parts)


def compare_previous_run(current: Mapping[str, Any] | Sequence[Any], previous: Mapping[str, Any] | Sequence[Any]) -> dict[str, list[dict[str, Any]]]:
    """Compare finding IDs and canonical content between two runs."""
    def index(payload: Mapping[str, Any] | Sequence[Any]) -> dict[str, dict[str, Any]]:
        result = {}
        values = payload.get("findings", ()) if isinstance(payload, Mapping) else payload
        for item in values or ():
            finding = _dict(item)
            key = str(finding.get("finding_id", finding.get("id", finding.get("title", ""))))
            result[key] = finding
        return result
    now, old = index(current), index(previous)
    return {
        "added": [now[key] for key in sorted(now.keys() - old.keys())],
        "removed": [old[key] for key in sorted(old.keys() - now.keys())],
        "changed": [{"finding_id": key, "previous": old[key], "current": now[key]} for key in sorted(now.keys() & old.keys()) if _json(now[key]) != _json(old[key])],
    }


def write_artifacts(
    output_dir: str | Path,
    *,
    findings: Sequence[Any] = (),
    quality_warnings: Sequence[Any] = (),
    briefing: Any | None = None,
    previous_run: Mapping[str, Any] | None = None,
    cost_appendix: str | None = None,
) -> dict[str, Path]:
    """Persist the requested artifacts under an explicit directory."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    cost_app = cost_appendix or (_briefing_dict(briefing).get("cost_appendix") if briefing is not None else None)
    payloads = {
        "findings.json": render_findings_json(findings, quality_warnings),
        "findings.csv": render_findings_csv(findings),
        "findings.md": render_findings_markdown(findings, quality_warnings),
        "memo.md": render_memo(findings, quality_warnings, previous_run=previous_run, cost_appendix=cost_app),
    }
    if briefing is not None:
        payloads.update({
            "briefing.json": render_briefing_json(briefing),
            "briefing.md": render_briefing_markdown(briefing),
            "briefing.html": render_briefing_html(briefing),
            "candidate_actions.json": _json(build_candidate_action_queue(_briefing_dict(briefing).get("candidate_actions", ()))),
        })
    for name, content in payloads.items():
        path = root / name
        path.write_text(content, encoding="utf-8", newline="\n")
        result[name] = path
    return result
