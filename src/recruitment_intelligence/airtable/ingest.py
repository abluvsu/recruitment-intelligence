"""Multi-table snapshot runner, caching, and programmatic schema profiling.

Provides read-only multi-table orchestration across canonical recruitment
tables, local filesystem caching and loading for offline replay, and
comprehensive schema/volume profiling answering Question 1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .client import (
    AirtableClient,
    AirtableError,
    SchemaProfile,
    _value_type,
)

CANONICAL_TABLES: tuple[str, ...] = (
    "Departments",
    "People",
    "Job Openings",
    "Candidates",
    "Applications",
    "Interviews",
    "Offers",
    "Findings",
)


def ingest_snapshot(
    client: AirtableClient,
    tables: Sequence[str] = CANONICAL_TABLES,
    output_path: str | Path | None = "data/raw/airtable_snapshot.json",
    normalize_links: bool = True,
    use_cache: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Fetch all records across requested tables and optionally persist snapshot to disk.

    Ensures read-only access by delegating queries to AirtableClient.
    Sensitive credentials and authorization tokens are strictly excluded from output.
    """
    snapshot: dict[str, list[dict[str, Any]]] = {}
    for table in tables:
        records = client.fetch_table(table, normalize_links=normalize_links, use_cache=use_cache)
        snapshot[table] = records

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )

    return snapshot


def load_snapshot(snapshot_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Load and validate an offline snapshot JSON file from disk.

    Raises AirtableError if the file does not exist, cannot be decoded as valid JSON,
    or does not match the expected format (mapping of table names to record lists).
    """
    path = Path(snapshot_path)
    if not path.exists():
        raise AirtableError(f"Snapshot file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AirtableError(f"Invalid JSON in snapshot file {path}") from exc

    if not isinstance(data, Mapping):
        raise AirtableError("Malformed snapshot: root must be a mapping of table names to records")

    validated: dict[str, list[dict[str, Any]]] = {}
    for table, records in data.items():
        if not isinstance(records, list):
            raise AirtableError(f"Malformed snapshot: records for table '{table}' must be a list")
        validated[str(table)] = list(records)

    return validated


def profile_all_tables(
    snapshot: Mapping[str, Sequence[Mapping[str, Any]]],
    tables: Sequence[str] | None = None,
) -> dict[str, SchemaProfile]:
    """Profile schema field types and exact record counts across tables in a snapshot (Q1).

    Supports both nested Airtable {"fields": {...}} envelope and flattened record dicts.
    """
    if not snapshot:
        return {}

    if tables is not None:
        target_tables = list(tables)
    else:
        canonical_present = [t for t in CANONICAL_TABLES if t in snapshot]
        other_present = [t for t in snapshot.keys() if t not in CANONICAL_TABLES]
        target_tables = canonical_present + other_present

    profiles: dict[str, SchemaProfile] = {}
    for table in target_tables:
        rows = list(snapshot.get(table, []))
        fields: dict[str, dict[str, int]] = {}
        for record in rows:
            if not isinstance(record, Mapping):
                continue

            values: Mapping[str, Any]
            if "fields" in record and isinstance(record["fields"], Mapping):
                values = record["fields"]
            else:
                values = {k: v for k, v in record.items() if k not in ("id", "record_id", "created_time", "createdTime")}

            for key, value in values.items():
                kind = _value_type(value)
                fields.setdefault(str(key), {})[kind] = (
                    fields.setdefault(str(key), {}).get(kind, 0) + 1
                )

        profiles[table] = SchemaProfile(table=table, record_count=len(rows), fields=fields)

    return profiles
