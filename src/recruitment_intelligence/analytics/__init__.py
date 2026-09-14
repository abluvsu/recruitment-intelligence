"""Public deterministic recruitment analytics API."""

from .engine import (
    CANONICAL_TABLES,
    INSUFFICIENT_FALLBACK,
    AnalyticsEngine,
    AnalyticsResult,
    run_analytics,
)
from .metrics import (
    _flatten_record,
    _flatten_tables,
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

__all__ = [
    "CANONICAL_TABLES",
    "INSUFFICIENT_FALLBACK",
    "AnalyticsEngine",
    "AnalyticsResult",
    "_flatten_record",
    "_flatten_tables",
    "aging",
    "funnel_bottleneck",
    "funnel_stage_conversions",
    "funnel_transitions",
    "offer_acceptance_rate",
    "pipeline_effort_sinks",
    "run_analytics",
    "sensitivity_analysis",
    "source_department_segmentation",
    "source_effectiveness",
    "stalled_applications",
    "table_counts",
]
