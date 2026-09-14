"""Tests for Airtable 8-table snapshot runner, caching, profiling, and offline replay.

Covers Milestone 2 requirements:
- Multi-table snapshot runner across 8 canonical tables
- Local snapshot caching (data/raw/airtable_snapshot.json) and offline loading
- Programmatic schema and volume profiling (Q1) across clean, dirty, and sparse snapshots
- Secret and API key redaction in cached files, errors, and string representations
- Rate limiting (5 req/s) and complete offline mock transport integration
- Validation of disk fixtures (fixtures/clean_snapshot.json, dirty, sparse)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
import pytest

from recruitment_intelligence.airtable.client import (
    DEFAULT_RATE_LIMIT_SECONDS,
    AirtableClient,
    AirtableError,
    AirtableResponse,
    SchemaProfile,
)
from recruitment_intelligence.airtable.ingest import (
    CANONICAL_TABLES,
    ingest_snapshot,
    load_snapshot,
    profile_all_tables,
)


# ---------------------------------------------------------------------------
# Fixtures and Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_clean_snapshot() -> dict[str, list[dict[str, Any]]]:
    """Synthetic clean snapshot covering all 8 canonical tables."""
    return {
        "Departments": [
            {"id": "dep-eng", "fields": {"name": "Engineering", "code": "ENG"}},
            {"id": "dep-sales", "fields": {"name": "Sales", "code": "SAL"}},
        ],
        "People": [
            {"id": "per-001", "fields": {"name": "Alice Recruiter", "role": "Recruiter"}},
            {"id": "per-002", "fields": {"name": "Bob HiringManager", "role": "Hiring Manager"}},
        ],
        "Job Openings": [
            {"id": "job-001", "fields": {"title": "Platform Engineer", "department_id": "dep-eng", "status": "open"}},
            {"id": "job-002", "fields": {"title": "Account Executive", "department_id": "dep-sales", "status": "open"}},
        ],
        "Candidates": [
            {"id": "cand-001", "fields": {"name": "Carol Candidate", "status": "hired"}},
            {"id": "cand-002", "fields": {"name": "Dave Candidate", "status": "active"}},
        ],
        "Applications": [
            {
                "id": "app-001",
                "fields": {
                    "candidate_id": "cand-001",
                    "job_id": "job-001",
                    "source": "Referral",
                    "status": "hired",
                    "applied_at": "2025-01-02",
                    "updated_at": "2025-01-28",
                },
            },
            {
                "id": "app-002",
                "fields": {
                    "candidate_id": "cand-002",
                    "job_id": "job-002",
                    "source": "Job board",
                    "status": "interview",
                    "applied_at": "2025-01-10",
                    "updated_at": "2025-01-20",
                },
            },
        ],
        "Interviews": [
            {"id": "int-001", "fields": {"application_id": "app-001", "scheduled_at": "2025-01-15", "status": "completed"}},
            {"id": "int-002", "fields": {"application_id": "app-002", "scheduled_at": "2025-01-25", "status": "scheduled"}},
        ],
        "Offers": [
            {"id": "off-001", "fields": {"application_id": "app-001", "status": "accepted", "offered_at": "2025-01-22"}},
        ],
        "Findings": [
            {"id": "fin-001", "fields": {"title": "Initial Baseline", "category": "system", "severity": "low"}},
        ],
    }


@pytest.fixture
def mock_dirty_snapshot() -> dict[str, list[dict[str, Any]]]:
    """Synthetic dirty snapshot containing data quality anomalies."""
    return {
        "Departments": [{"id": "dep-eng", "fields": {"name": "Engineering"}}],
        "People": [{"id": "per-001", "fields": {"name": None, "role": 123}}],  # null name, number role
        "Job Openings": [{"id": "job-001", "fields": {"title": "Platform Engineer"}}],
        "Candidates": [{"id": "cand-001", "fields": {"name": "Test", "status": "unmapped_status"}}],
        "Applications": [
            {
                "id": "app-001",
                "fields": {
                    "candidate_id": "cand-999",  # missing FK
                    "job_id": "job-001",
                    "source": "Unknown Channel",
                    "applied_at": "invalid-date",
                    "updated_at": "2025-01-01",
                },
            }
        ],
        "Interviews": [{"id": "int-001", "fields": {"application_id": "app-orphan"}}],  # orphan
        "Offers": [{"id": "off-001", "fields": {"application_id": "app-001", "status": "pending"}}],
        "Findings": [],
    }


@pytest.fixture
def mock_sparse_snapshot() -> dict[str, list[dict[str, Any]]]:
    """Synthetic sparse snapshot with empty tables and minimal fields."""
    return {
        "Departments": [],
        "People": [],
        "Job Openings": [],
        "Candidates": [{"id": "cand-001", "fields": {}}],  # empty fields mapping
        "Applications": [],
        "Interviews": [],
        "Offers": [],
        "Findings": [],
    }


# ---------------------------------------------------------------------------
# 1. Canonical Tables & Ingestion Runner Tests
# ---------------------------------------------------------------------------

def test_canonical_tables_constant():
    """Verify CANONICAL_TABLES contains the exact 8 required tables in order."""
    expected = (
        "Departments",
        "People",
        "Job Openings",
        "Candidates",
        "Applications",
        "Interviews",
        "Offers",
        "Findings",
    )
    assert CANONICAL_TABLES == expected
    assert len(CANONICAL_TABLES) == 8


def test_ingest_snapshot_all_8_tables(mock_clean_snapshot):
    """Verify ingest_snapshot queries all 8 canonical tables and produces a unified dictionary."""
    queried_tables: list[str] = []

    def mock_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        table_name = url.rsplit("/", 1)[-1]
        queried_tables.append(table_name)
        records = mock_clean_snapshot.get(table_name, [])
        return AirtableResponse(200, {"records": records})

    client = AirtableClient("base123", "pat.test_token", transport=mock_transport)
    snapshot = ingest_snapshot(client, output_path=None)

    assert set(snapshot.keys()) == set(CANONICAL_TABLES)
    assert queried_tables == list(CANONICAL_TABLES)
    assert len(snapshot["Departments"]) == 2
    assert len(snapshot["Candidates"]) == 2
    assert len(snapshot["Offers"]) == 1


def test_ingest_snapshot_custom_tables_subset():
    """Verify ingest_snapshot accepts a custom subset of table names."""
    queried_tables: list[str] = []

    def mock_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        table_name = url.rsplit("/", 1)[-1]
        queried_tables.append(table_name)
        return AirtableResponse(200, {"records": [{"id": f"rec_{table_name}"}]})

    client = AirtableClient("base123", "pat.test_token", transport=mock_transport)
    custom_tables = ("Departments", "Candidates")
    snapshot = ingest_snapshot(client, tables=custom_tables, output_path=None)

    assert set(snapshot.keys()) == set(custom_tables)
    assert queried_tables == list(custom_tables)
    assert len(snapshot["Departments"]) == 1
    assert len(snapshot["Candidates"]) == 1


def test_ingest_snapshot_handles_pagination():
    """Verify ingest_snapshot correctly consumes paginated records across tables."""
    page_counter = {"Applications": 0}

    def mock_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        table = url.rsplit("/", 1)[-1]
        if table == "Applications":
            page_counter["Applications"] += 1
            if page_counter["Applications"] == 1:
                return AirtableResponse(200, {
                    "records": [{"id": "app-1", "fields": {"status": "review"}}],
                    "offset": "page_2_offset",
                })
            return AirtableResponse(200, {
                "records": [{"id": "app-2", "fields": {"status": "interview"}}],
            })
        return AirtableResponse(200, {"records": []})

    client = AirtableClient("base123", "pat.test_token", transport=mock_transport)
    snapshot = ingest_snapshot(client, tables=("Applications",), output_path=None)

    assert len(snapshot["Applications"]) == 2
    assert [r["id"] for r in snapshot["Applications"]] == ["app-1", "app-2"]


def test_ingest_snapshot_normalizes_links_by_default():
    """Verify linked records are converted to ID arrays while preserving raw objects."""
    def mock_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        return AirtableResponse(200, {
            "records": [
                {
                    "id": "app-1",
                    "fields": {
                        "job_id": [{"id": "job-100", "name": "Platform Eng"}],
                    },
                }
            ]
        })

    client = AirtableClient("base123", "pat.test_token", transport=mock_transport)
    snapshot = ingest_snapshot(client, tables=("Applications",), output_path=None)

    app = snapshot["Applications"][0]
    assert app["fields"]["job_id"] == ["job-100"]
    assert app["fields"]["job_id__records"] == [{"id": "job-100", "name": "Platform Eng"}]


# ---------------------------------------------------------------------------
# 2. Caching, Persistence & Offline Loading Tests
# ---------------------------------------------------------------------------

def test_ingest_snapshot_writes_to_disk(tmp_path: Path, mock_clean_snapshot):
    """Verify ingest_snapshot writes indented, deterministic JSON to output_path."""
    output_file = tmp_path / "data" / "raw" / "airtable_snapshot.json"

    def mock_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        table = url.rsplit("/", 1)[-1]
        return AirtableResponse(200, {"records": mock_clean_snapshot.get(table, [])})

    client = AirtableClient("base123", "pat.test_token", transport=mock_transport)
    result = ingest_snapshot(client, output_path=output_file)

    assert output_file.exists()
    file_content = json.loads(output_file.read_text(encoding="utf-8"))
    assert file_content == result
    assert set(file_content.keys()) == set(CANONICAL_TABLES)


def test_load_snapshot_roundtrip(tmp_path: Path, mock_clean_snapshot):
    """Verify saving a snapshot and loading it returns exact data structure."""
    snapshot_path = tmp_path / "test_snapshot.json"
    snapshot_path.write_text(json.dumps(mock_clean_snapshot, indent=2), encoding="utf-8")

    loaded = load_snapshot(snapshot_path)
    assert loaded == mock_clean_snapshot


def test_load_snapshot_accepts_str_and_path(tmp_path: Path, mock_clean_snapshot):
    """Verify load_snapshot handles both str and Path instances seamlessly."""
    snapshot_path = tmp_path / "snap.json"
    snapshot_path.write_text(json.dumps(mock_clean_snapshot), encoding="utf-8")

    from_path = load_snapshot(snapshot_path)
    from_str = load_snapshot(str(snapshot_path))
    assert from_path == from_str == mock_clean_snapshot


def test_load_snapshot_missing_file_raises_airtable_error(tmp_path: Path):
    """Verify loading a nonexistent snapshot raises AirtableError."""
    missing = tmp_path / "does_not_exist.json"
    with pytest.raises(AirtableError, match="not found|does not exist"):
        load_snapshot(missing)


def test_load_snapshot_malformed_json_raises_airtable_error(tmp_path: Path):
    """Verify loading a corrupt/non-JSON file raises AirtableError."""
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("NOT VALID JSON {{{", encoding="utf-8")

    with pytest.raises(AirtableError, match="Invalid|corrupt|JSON"):
        load_snapshot(corrupt)


def test_load_snapshot_non_dict_root_raises_airtable_error(tmp_path: Path):
    """Verify loading a JSON file with root array raises AirtableError."""
    array_file = tmp_path / "array.json"
    array_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(AirtableError, match="mapping|object|dictionary"):
        load_snapshot(array_file)


def test_load_snapshot_non_list_table_records_raises_airtable_error(tmp_path: Path):
    """Verify loading a snapshot where a table contains a non-list value raises AirtableError."""
    bad_table_file = tmp_path / "bad_table.json"
    bad_table_file.write_text(json.dumps({"Departments": "not-a-list"}), encoding="utf-8")

    with pytest.raises(AirtableError, match="must be a list|list of records"):
        load_snapshot(bad_table_file)


# ---------------------------------------------------------------------------
# 3. Validation of Real Disk Fixtures
# ---------------------------------------------------------------------------

def test_load_real_clean_snapshot_fixture():
    """Verify loading fixtures/clean_snapshot.json and profiling all 8 tables."""
    fixture_path = Path("fixtures/clean_snapshot.json")
    assert fixture_path.exists(), "fixtures/clean_snapshot.json must exist"

    snapshot = load_snapshot(fixture_path)
    assert set(snapshot.keys()) == set(CANONICAL_TABLES)

    profiles = profile_all_tables(snapshot)
    assert len(profiles) == 8
    assert profiles["Departments"].record_count == 3
    assert profiles["People"].record_count == 4
    assert profiles["Job Openings"].record_count == 3
    assert profiles["Candidates"].record_count == 8
    assert profiles["Applications"].record_count == 10
    assert profiles["Interviews"].record_count == 6
    assert profiles["Offers"].record_count == 3
    assert profiles["Findings"].record_count == 2


def test_load_real_dirty_snapshot_fixture():
    """Verify loading fixtures/dirty_snapshot.json and profiling all 8 tables."""
    fixture_path = Path("fixtures/dirty_snapshot.json")
    assert fixture_path.exists(), "fixtures/dirty_snapshot.json must exist"

    snapshot = load_snapshot(fixture_path)
    assert set(snapshot.keys()) == set(CANONICAL_TABLES)

    profiles = profile_all_tables(snapshot)
    assert len(profiles) == 8
    assert profiles["Departments"].record_count == 2
    assert profiles["Applications"].record_count == 10


def test_load_real_sparse_snapshot_fixture():
    """Verify loading fixtures/sparse_snapshot.json and profiling all 8 tables."""
    fixture_path = Path("fixtures/sparse_snapshot.json")
    assert fixture_path.exists(), "fixtures/sparse_snapshot.json must exist"

    snapshot = load_snapshot(fixture_path)
    assert set(snapshot.keys()) == set(CANONICAL_TABLES)

    profiles = profile_all_tables(snapshot)
    assert len(profiles) == 8
    for table in CANONICAL_TABLES:
        assert profiles[table].record_count == 0
        assert profiles[table].fields == {}


# ---------------------------------------------------------------------------
# 4. Schema & Volume Profiler (Q1) Tests
# ---------------------------------------------------------------------------

def test_profile_all_tables_clean_snapshot(mock_clean_snapshot):
    """Verify profile_all_tables profiles exact record counts and field types across all 8 tables."""
    profiles = profile_all_tables(mock_clean_snapshot)

    assert set(profiles.keys()) == set(CANONICAL_TABLES)

    dept_prof = profiles["Departments"]
    assert isinstance(dept_prof, SchemaProfile)
    assert dept_prof.table == "Departments"
    assert dept_prof.record_count == 2
    assert dept_prof.fields["name"] == {"string": 2}
    assert dept_prof.fields["code"] == {"string": 2}

    app_prof = profiles["Applications"]
    assert app_prof.record_count == 2
    assert app_prof.fields["status"] == {"string": 2}
    assert app_prof.fields["source"] == {"string": 2}

    findings_prof = profiles["Findings"]
    assert findings_prof.record_count == 1
    assert findings_prof.fields["severity"] == {"string": 1}

    # Verify to_dict serializability
    d = dept_prof.to_dict()
    assert d["table"] == "Departments"
    assert d["record_count"] == 2
    assert d["fields"]["name"] == {"string": 2}


def test_profile_all_tables_dirty_snapshot(mock_dirty_snapshot):
    """Verify profiler handles mixed types, null values, and anomalies gracefully."""
    profiles = profile_all_tables(mock_dirty_snapshot)

    people_prof = profiles["People"]
    assert people_prof.record_count == 1
    assert people_prof.fields["name"] == {"null": 1}
    assert people_prof.fields["role"] == {"number": 1}

    findings_prof = profiles["Findings"]
    assert findings_prof.record_count == 0
    assert findings_prof.fields == {}


def test_profile_all_tables_sparse_snapshot(mock_sparse_snapshot):
    """Verify profiler handles empty tables and empty field dicts without division-by-zero."""
    profiles = profile_all_tables(mock_sparse_snapshot)

    assert set(profiles.keys()) == set(CANONICAL_TABLES)
    for table in ("Departments", "People", "Job Openings", "Applications", "Interviews", "Offers", "Findings"):
        assert profiles[table].record_count == 0
        assert profiles[table].fields == {}

    cand_prof = profiles["Candidates"]
    assert cand_prof.record_count == 1
    assert cand_prof.fields == {}


def test_profile_all_tables_supports_flat_records():
    """Verify profiler supports records with flat fields (without nested 'fields' key)."""
    flat_snapshot = {
        "Departments": [
            {"id": "dep-1", "name": "Engineering", "budget": 100000},
            {"id": "dep-2", "name": "Sales", "budget": 50000},
        ]
    }
    profiles = profile_all_tables(flat_snapshot)
    assert profiles["Departments"].record_count == 2
    assert profiles["Departments"].fields["name"] == {"string": 2}
    assert profiles["Departments"].fields["budget"] == {"number": 2}


def test_profile_all_tables_empty_snapshot():
    """Verify profiler handles empty snapshot dictionary cleanly."""
    profiles = profile_all_tables({})
    assert profiles == {}


# ---------------------------------------------------------------------------
# 5. Secret & Credential Redaction Tests
# ---------------------------------------------------------------------------

def test_client_repr_and_str_mask_api_key():
    """Verify client __repr__ and __str__ never leak the raw API key."""
    secret = "pat.SECRET_TOKEN_MASK_CHECK_999"
    client = AirtableClient("base_xyz", secret, transport=lambda *args, **kwargs: None)

    repr_str = repr(client)
    str_str = str(client)

    assert secret not in repr_str
    assert "SECRET_TOKEN" not in repr_str
    assert "***" in repr_str

    assert secret not in str_str
    assert "SECRET_TOKEN" not in str_str
    assert "***" in str_str


def test_ingest_snapshot_file_redacts_api_key(tmp_path: Path):
    """Verify sensitive API keys/tokens are NEVER written to snapshot JSON files."""
    secret_token = "pat.SECRET_TOKEN_XYZ_9876543210"
    output_file = tmp_path / "safe_snapshot.json"

    def mock_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        return AirtableResponse(200, {"records": [{"id": "r1", "fields": {"note": "safe"}}]})

    client = AirtableClient("base123", secret_token, transport=mock_transport)
    ingest_snapshot(client, tables=("Departments",), output_path=output_file)

    content = output_file.read_text(encoding="utf-8")
    assert "SECRET_TOKEN" not in content
    assert "9876543210" not in content
    assert secret_token not in content


def test_airtable_error_redacts_api_token():
    """Verify AirtableError messages do not leak the Authorization header or API token."""
    secret_token = "pat.SECRET_TOKEN_DO_NOT_LEAK"

    def failing_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        return AirtableResponse(401, {"error": {"type": "AUTHENTICATION_REQUIRED", "message": "Invalid token"}})

    client = AirtableClient("base123", secret_token, transport=failing_transport, max_retries=0)
    with pytest.raises(AirtableError) as exc_info:
        ingest_snapshot(client, tables=("Departments",), output_path=None)

    error_str = str(exc_info.value)
    error_repr = repr(exc_info.value)
    assert secret_token not in error_str
    assert secret_token not in error_repr
    assert "SECRET_TOKEN_DO_NOT_LEAK" not in error_str


def test_snapshot_memory_dict_has_no_credentials(mock_clean_snapshot):
    """Verify the returned snapshot dictionary contains pure data, with no credential metadata."""
    secret_token = "pat.SECRET_TOKEN_MEM_CHECK"

    def mock_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        return AirtableResponse(200, {"records": []})

    client = AirtableClient("base123", secret_token, transport=mock_transport)
    snapshot = ingest_snapshot(client, output_path=None)

    serialized = json.dumps(snapshot)
    assert secret_token not in serialized
    assert "SECRET_TOKEN" not in serialized


# ---------------------------------------------------------------------------
# 6. Rate Limiting (5 req/s) & Mock Transport Network Isolation
# ---------------------------------------------------------------------------

def test_rate_limiting_enforces_5_requests_per_second():
    """Verify client enforces maximum 5 requests/sec cadence (0.2s interval between calls)."""
    sleep_calls: list[float] = []

    def mock_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        return AirtableResponse(200, {"records": []})

    assert DEFAULT_RATE_LIMIT_SECONDS == 0.2

    client = AirtableClient(
        "base123",
        "pat.test_token",
        transport=mock_transport,
        rate_limit_seconds=0.2,
        sleep=sleep_calls.append,
    )

    # Fetch 3 tables sequentially
    ingest_snapshot(client, tables=("Departments", "People", "Candidates"), output_path=None)

    # Should have called sleep between successive requests
    assert len(sleep_calls) >= 2
    for delay in sleep_calls:
        assert 0.0 < delay <= 0.2


def test_mock_transport_guarantees_zero_network(monkeypatch, mock_clean_snapshot):
    """Verify running ingest_snapshot with mock transport makes zero real network connections."""
    def forbidden_network(*args, **kwargs):
        raise AssertionError("Real network call attempted during offline test!")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_network)

    def mock_transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
        table = url.rsplit("/", 1)[-1]
        return AirtableResponse(200, {"records": mock_clean_snapshot.get(table, [])})

    client = AirtableClient("base123", "pat.test_token", transport=mock_transport)
    snapshot = ingest_snapshot(client, output_path=None)
    assert set(snapshot.keys()) == set(CANONICAL_TABLES)
