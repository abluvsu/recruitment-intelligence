"""Command-line entry point for an offline or cached recruitment run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .outputs.briefing import produce_daily_briefing


def run_snapshot(
    snapshot: dict[str, Any],
    output_dir: str | Path,
    *,
    as_of: str | None = None,
    include_cost_appendix: bool = True,
) -> dict[str, Path]:
    """Analyze a cached snapshot through the complete briefing pipeline."""
    tables = {str(k): list(v) for k, v in snapshot.items() if isinstance(v, list)}
    _briefing, written_paths = produce_daily_briefing(
        tables,
        output_dir=output_dir,
        as_of=as_of,
        include_cost_appendix=include_cost_appendix,
    )
    return written_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run recruitment intelligence on a cached JSON snapshot")
    parser.add_argument("snapshot", type=Path, help="JSON object mapping table names to record arrays")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--as-of", type=str, default=None, help="Reference date for deterministic aging (YYYY-MM-DD)")
    parser.add_argument("--no-cost-appendix", action="store_true", help="Omit the external benchmark appendix")
    args = parser.parse_args(argv)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        parser.error("snapshot must contain a JSON object")
    for path in run_snapshot(
        snapshot,
        args.output_dir,
        as_of=args.as_of,
        include_cost_appendix=not args.no_cost_appendix,
    ).values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
