"""Command-line entry point for an offline or cached recruitment run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .outputs.briefing import produce_daily_briefing
from .pipeline import load_live_snapshot


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
    parser.add_argument("snapshot", type=Path, nargs="?", help="Cached JSON snapshot")
    parser.add_argument("--live", action="store_true", help="Fetch current Airtable data from environment credentials")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--as-of", type=str, default=None, help="Reference date for deterministic aging (YYYY-MM-DD)")
    parser.add_argument("--no-cost-appendix", action="store_true", help="Omit the external benchmark appendix")
    parser.add_argument("--cache-dir", type=Path, default=None, help="Per-table Airtable response cache directory")
    parser.add_argument("--no-refresh", action="store_true", help="Replay Airtable cache files in live mode")
    args = parser.parse_args(argv)
    if args.live and args.snapshot is not None:
        parser.error("provide either SNAPSHOT or --live, not both")
    if args.live:
        try:
            snapshot = load_live_snapshot(
                cache_dir=args.cache_dir,
                refresh=not args.no_refresh,
            )
        except Exception as exc:
            parser.error(f"live Airtable fetch failed: {type(exc).__name__}: {exc}")
    else:
        if args.snapshot is None:
            parser.error("provide SNAPSHOT or --live")
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
