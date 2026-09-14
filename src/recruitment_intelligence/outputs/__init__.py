"""Deterministic artifact renderers for recruitment intelligence results.

Renderers in this module are deliberately side-effect free by default.  They
accept domain contracts or JSON-compatible mappings and return stable strings
or dictionaries; :func:`write_artifacts` is the explicit persistence helper.
"""

from .briefing import (
    generate_executive_briefing,
    produce_daily_briefing,
)
from .cost_appendix import (
    DEFAULT_BENCHMARKS,
    build_cost_research_appendix,
)
from .renderers import (
    build_candidate_action_queue,
    compare_previous_run,
    render_briefing_html,
    render_briefing_json,
    render_briefing_markdown,
    render_findings_csv,
    render_findings_json,
    render_findings_markdown,
    write_artifacts,
)
from .memo import render_memo


# Friendly aliases for callers that do not need to choose a format explicitly.
render_findings = render_findings_markdown
render_briefing = render_briefing_markdown
render_candidate_actions = build_candidate_action_queue

__all__ = [
    "DEFAULT_BENCHMARKS",
    "build_candidate_action_queue",
    "build_cost_research_appendix",
    "compare_previous_run",
    "generate_executive_briefing",
    "produce_daily_briefing",
    "render_briefing",
    "render_briefing_html",
    "render_briefing_json",
    "render_briefing_markdown",
    "render_candidate_actions",
    "render_findings",
    "render_findings_csv",
    "render_findings_json",
    "render_findings_markdown",
    "render_memo",
    "write_artifacts",
]
