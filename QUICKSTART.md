# Founder quickstart

This project reads Airtable through read-only GET requests, stores one local
snapshot, and generates a briefing. It never writes back to Airtable.

## 1. Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## 2. Configure credentials

Copy `.env.example` to `.env` and set:

```text
AIRTABLE_API_KEY=pat_...
AIRTABLE_BASE_ID=app...
```

The CLI reads `.env` without printing the values. You can optionally set
`AIRTABLE_TABLES` to a comma-separated list, `AIRTABLE_CACHE_DIR` for per-table
response caches, and `AIRTABLE_SNAPSHOT_PATH` for the aggregate snapshot.

## 3. Run the live report

```powershell
python -m recruitment_intelligence.pipeline --live --as-of 2025-02-01 --output-dir outputs/live
```

Review `outputs/live/briefing.md`, `memo.md`, and
`candidate_actions.json`. Candidate actions are advisory and require a human
review before anyone advances, escalates, requests feedback, or closes a
process.

## 4. Replay the snapshot offline

```powershell
python -m recruitment_intelligence.pipeline data/raw/airtable_snapshot.json --as-of 2025-02-01 --output-dir outputs/replay
```

Run `python scripts/release_check.py` before handing the repository to another
operator.
