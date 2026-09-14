# Recruitment Intelligence

An evidence-backed founder operating system for hiring: read-only Airtable data
is cached locally, normalized, checked for quality, analyzed deterministically,
and rendered as findings, candidate action queues, and daily briefings.

## Status

The repository ships as a local, offline-first CLI. Mock mode is the default so
it runs without a paid LLM API; a Gemini adapter can be enabled later through
the provider interface.

## Safety and scope

- Airtable is the only system of record and is accessed read-only.
- Data is pulled once and replayed from a local snapshot.
- Core metrics are deterministic Python; an LLM may synthesize validated facts
  but may not calculate or invent unsupported figures.
- Candidate recommendations are advisory (`review`, `advance`, `escalate`,
  `request_feedback`, or `close`) and never autonomous rejection decisions.
- Source ROI and recruiting-cost research belong in a separately labelled appendix
  and are not inferred from application data.
- No scheduler or dashboard is included in the first implementation.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m pytest -q
python -m compileall src tests
```

## Offline run

Run the complete pipeline against a cached fixture without Airtable credentials
or a paid LLM provider:

```powershell
python -m recruitment_intelligence.cli fixtures/recruitment_snapshot.json --output-dir outputs/run
```

Pin a reference date when you need byte-identical output across runs:

```powershell
recruitment-intelligence fixtures/clean_snapshot.json --as-of 2025-02-01 --output-dir outputs/release-check
```

The convenience wrapper is equivalent:

```powershell
python scripts/run_offline.py
```

Both commands use `MockProvider` by default (`RI_PROVIDER=mock`) and write
reproducible JSON/CSV/Markdown artifacts under the selected output directory.
Set `RI_PROVIDER` only when an explicitly configured provider adapter and its
required credentials are available; Airtable access remains read-only.

Before sharing the repository, run `python scripts/release_check.py`. It performs
a clean editable install, runs the pinned offline pipeline twice, checks the
required artifacts, and scans them for common secret markers.

See [docs/implementation-plan.md](docs/implementation-plan.md) for the staged
build loop and [docs/decision-log.md](docs/decision-log.md) for architectural
decisions.
