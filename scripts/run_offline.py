"""Run a small deterministic recruitment pipeline without network or API keys.

Usage: ``python scripts/run_offline.py [output-directory]``.  The fixture is
embedded intentionally so a clean checkout can always reproduce an example.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure src is importable when executed directly
_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from recruitment_intelligence.agents import generate_advisory_actions
from recruitment_intelligence.analytics import source_effectiveness, offer_acceptance_rate, stalled_applications
from recruitment_intelligence.domain import Confidence, EvidenceReference, Finding, Briefing
from recruitment_intelligence.quality import run_quality_checks
from recruitment_intelligence.outputs import write_artifacts


def fixture() -> dict[str, list[dict[str, object]]]:
    return {
        "Applications": [
            {"id": "a1", "candidate_id": "c1", "source": "Referral", "status": "hired", "applied_at": "2025-01-01", "updated_at": "2025-01-20"},
            {"id": "a2", "candidate_id": "c2", "source": "Job board", "status": "interview", "applied_at": "2025-01-10", "updated_at": "2025-01-15"},
        ],
        "Candidates": [{"id": "c1", "status": "hired"}, {"id": "c2", "status": "active"}],
        "Offers": [{"id": "o1", "application_id": "a1", "status": "accepted"}],
        "Interviews": [{"id": "i1", "application_id": "a2"}],
    }


from recruitment_intelligence.outputs.briefing import generate_executive_briefing


def build(custom_tables: dict[str, list[dict[str, object]]] | None = None) -> tuple[list[Finding], list[dict[str, object]], Briefing]:
    tables = custom_tables or fixture()
    briefing = generate_executive_briefing(tables, include_cost_appendix=True)
    warnings = [w.to_dict() if hasattr(w, "to_dict") else dict(w) for w in briefing.quality_warnings]
    return list(briefing.findings), warnings, briefing


def main() -> int:
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outputs")
    findings, warnings, briefing = build()
    paths = write_artifacts(destination, findings=findings, quality_warnings=warnings, briefing=briefing)
    for path in sorted(paths.values()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

