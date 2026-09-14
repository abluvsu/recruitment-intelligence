"""Isolated external recruitment cost research appendix.

Benchmarks industry cost-per-hire and recruiting channel cost structures
without modifying or corrupting Airtable-derived baseline metrics.
"""
from __future__ import annotations

from typing import Mapping

DEFAULT_BENCHMARKS: dict[str, str] = {
    "engineering_cost_per_hire": "$4,500 - $6,000 (SHRM Benchmark)",
    "sales_cost_per_hire": "$3,800 - $5,200",
    "executive_cost_per_hire": "$14,000 - $22,000",
    "agency_fee_percentage": "20% - 25% of first-year base salary",
    "job_board_monthly_seat": "$300 - $600 per recruiter seat",
    "referral_bonus_average": "$2,000 - $5,000 for technical roles",
}


def build_cost_research_appendix(custom_benchmarks: Mapping[str, str] | None = None) -> str:
    """Return formatted external cost benchmarks strictly isolated from Airtable metrics."""
    benchmarks = dict(custom_benchmarks or DEFAULT_BENCHMARKS)
    lines = [
        "### External Recruitment Cost Research (Strictly Isolated)",
        "",
        "> **Note:** The benchmarks below are compiled from external industry surveys (SHRM, LinkedIn Talent Solutions) "
        "and are provided solely as context for founder planning. They are NOT derived from Airtable data and do NOT "
        "modify any baseline funnel or conversion metrics.",
        "",
        "| Category / Channel | Industry Benchmark Range | Operational Context |",
        "|---|---|---|",
        f"| Software Engineering | {benchmarks.get('engineering_cost_per_hire', 'N/A')} | Blended cost including sourcing, time-to-hire, and tooling |",
        f"| Sales & Go-to-Market | {benchmarks.get('sales_cost_per_hire', 'N/A')} | High volume screening with lower assessment overhead |",
        f"| Leadership / Executive | {benchmarks.get('executive_cost_per_hire', 'N/A')} | Retained search partner fee structure |",
        f"| External Recruiting Agency | {benchmarks.get('agency_fee_percentage', 'N/A')} | Contingent search fee on placed candidates |",
        f"| Job Boards & Aggregators | {benchmarks.get('job_board_monthly_seat', 'N/A')} | Fixed monthly subscription cost |",
        f"| Employee Referral Bonus | {benchmarks.get('referral_bonus_average', 'N/A')} | Cash bonus paid after 90 days retention |",
        "",
        "**Founder takeaway:** Prioritize employee referrals and high-conversion inbound channels to minimize "
        "agency fee exposure while monitoring pipeline effort yield.",
    ]
    return "\n".join(lines)
