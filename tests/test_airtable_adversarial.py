"""Adversarial stress-test suite for Milestone M2 (Airtable Ingestion, Rate Limiting & Profiling).

Challenges edge cases, failure modes, boundary limits, and security constraints:
1. Malformed, corrupt, or truncated snapshot JSON files in load_snapshot.
2. Snapshot caching with missing nested dirs, unwritable paths, and concurrent access.
3. Network failure injection during ingest_snapshot: partial table failures, retry exhaustion,
   status code boundaries (400, 401, 403, 404, 429, 500, 503), malformed envelopes.
4. Schema profiler resilience with extreme inputs: nested arrays, nulls, boolean vs int
   disambiguation, deeply nested dicts, unicode table names, non-string field keys.
5. Zero secrets leaked in tracebacks, exception chains, string representations, or cache files.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any, Mapping
import pytest

from recruitment_intelligence.airtable.client import (
    DEFAULT_RATE_LIMIT_SECONDS,
    AirtableClient,
    AirtableError,
    AirtableResponse,
    SchemaProfile,
    _value_type,
    normalize_linked_records,
)
from recruitment_intelligence.airtable.ingest import (
    CANONICAL_TABLES,
    ingest_snapshot,
    load_snapshot,
    profile_all_tables,
)


SECRET_TOKEN = "pat.SUPER_SENSITIVE_SECRET_TOKEN_DO_NOT_LEAK_12345"


# ===========================================================================
# 1. Malformed, Corrupt, and Truncated Snapshot JSON Tests
# ===========================================================================

class TestLoadSnapshotAdversarial:
    """Stress-test load_snapshot with adversarial disk payloads."""

    def test_truncated_json(self, tmp_path: Path):
        """Truncated JSON cut off mid-token must raise AirtableError."""
        p = tmp_path / "truncated.json"
        p.write_text('{"Departments": [{"id": "dep-1", "fields": {"na', encoding="utf-8")
        with pytest.raises(AirtableError, match="Invalid JSON"):
            load_snapshot(p)

    def test_zero_byte_file(self, tmp_path: Path):
        """Zero-byte empty file must raise AirtableError."""
        p = tmp_path / "empty.json"
        p.write_text("", encoding="utf-8")
        with pytest.raises(AirtableError, match="Invalid JSON"):
            load_snapshot(p)

    def test_whitespace_only_file(self, tmp_path: Path):
        """Whitespace-only file must raise AirtableError."""
        p = tmp_path / "spaces.json"
        p.write_text("   \n\t  \n  ", encoding="utf-8")
        with pytest.raises(AirtableError, match="Invalid JSON"):
            load_snapshot(p)

    def test_corrupt_json_html_error_page(self, tmp_path: Path):
        """HTML error page (e.g. from 502 gateway) saved as JSON must raise AirtableError."""
        p = tmp_path / "gateway_error.json"
        p.write_text("<html><body>502 Bad Gateway</body></html>", encoding="utf-8")
        with pytest.raises(AirtableError, match="Invalid JSON"):
            load_snapshot(p)

    def test_null_bytes_in_json(self, tmp_path: Path):
        """JSON file embedded with null bytes must raise AirtableError."""
        p = tmp_path / "null_bytes.json"
        p.write_bytes(b'{"Departments": \x00\x00}')
        with pytest.raises(AirtableError, match="Invalid JSON"):
            load_snapshot(p)

    def test_invalid_utf8_encoding(self, tmp_path: Path):
        """File with invalid UTF-8 byte sequences must raise AirtableError without unhandled crash."""
        p = tmp_path / "bad_utf8.json"
        p.write_bytes(b'{"Departments": ["\xff\xfe invalid byte sequence"]}')
        with pytest.raises(AirtableError, match="Invalid JSON"):
            load_snapshot(p)

    @pytest.mark.parametrize("bad_root", [
        [{"Departments": []}],    # Root list
        "string_root",            # Root string
        123456,                   # Root int
        99.99,                    # Root float
        True,                     # Root bool
        None,                     # Root null
    ])
    def test_non_mapping_root_types(self, tmp_path: Path, bad_root: Any):
        """Root JSON element that is not a dictionary must raise AirtableError."""
        p = tmp_path / f"bad_root_{type(bad_root).__name__}.json"
        p.write_text(json.dumps(bad_root), encoding="utf-8")
        with pytest.raises(AirtableError, match="root must be a mapping"):
            load_snapshot(p)

    @pytest.mark.parametrize("bad_table_value", [
        "not_a_list",
        1234,
        True,
        None,
        {"nested": "dict"},
    ])
    def test_non_list_table_value(self, tmp_path: Path, bad_table_value: Any):
        """Table entry whose value is not a list must raise AirtableError."""
        p = tmp_path / "bad_table.json"
        p.write_text(json.dumps({"Departments": bad_table_value}), encoding="utf-8")
        with pytest.raises(AirtableError, match="must be a list"):
            load_snapshot(p)

    def test_directory_path_instead_of_file(self, tmp_path: Path):
        """Passing a directory path to load_snapshot must raise AirtableError."""
        dir_path = tmp_path / "some_dir"
        dir_path.mkdir()
        with pytest.raises(AirtableError):
            load_snapshot(dir_path)


# ===========================================================================
# 2. Snapshot Caching, Disk IO & Concurrency Tests
# ===========================================================================

class TestSnapshotCachingAndIOAdversarial:
    """Stress-test filesystem caching, permissions, and concurrency."""

    def test_deeply_nested_output_directory(self, tmp_path: Path):
        """ingest_snapshot creates all missing parent directories automatically."""
        deep_dir = tmp_path / "a" / "b" / "c" / "d" / "snapshot.json"
        client = AirtableClient("base_id", "pat.key", transport=lambda *a, **k: AirtableResponse(200, {"records": []}))
        result = ingest_snapshot(client, tables=("Departments",), output_path=deep_dir)
        assert deep_dir.exists()
        assert json.loads(deep_dir.read_text(encoding="utf-8")) == {"Departments": []}

    def test_output_path_is_existing_directory_raises_os_error(self, tmp_path: Path):
        """Pointing output_path to an existing directory must fail safely."""
        existing_dir = tmp_path / "dir_output"
        existing_dir.mkdir()
        client = AirtableClient("base_id", "pat.key", transport=lambda *a, **k: AirtableResponse(200, {"records": []}))
        with pytest.raises(OSError):
            ingest_snapshot(client, tables=("Departments",), output_path=existing_dir)

    def test_corrupt_client_cache_raises_airtable_error(self, tmp_path: Path):
        """Corrupt client cache file must raise AirtableError with clear message."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        client = AirtableClient("base_id", "pat.key", cache_dir=cache_dir, transport=lambda *a, **k: AirtableResponse(200, {"records": []}))
        cache_file = client._cache_path("Departments", None)
        assert cache_file is not None
        cache_file.write_text("NOT VALID JSON", encoding="utf-8")

        with pytest.raises(AirtableError, match="Invalid Airtable snapshot cache"):
            client.fetch_table("Departments", use_cache=True)

    @pytest.mark.parametrize("bad_cache_payload", [
        "[1, 2, 3]",                    # list root
        '{"table": "T"}',              # missing records key
        '{"records": "not_a_list"}',   # non-list records
        '{"records": 123}',              # integer records
    ])
    def test_malformed_client_cache_structures_raise(self, tmp_path: Path, bad_cache_payload: str):
        """Malformed client cache JSON structures raise AirtableError."""
        cache_dir = tmp_path / "cache_bad"
        cache_dir.mkdir()
        client = AirtableClient("base_id", "pat.key", cache_dir=cache_dir, transport=lambda *a, **k: AirtableResponse(200, {"records": []}))
        cache_file = client._cache_path("Departments", None)
        assert cache_file is not None
        cache_file.write_text(bad_cache_payload, encoding="utf-8")

        with pytest.raises(AirtableError, match="Invalid Airtable snapshot cache"):
            client.fetch_table("Departments", use_cache=True)

    def test_concurrent_ingest_snapshot_writes(self, tmp_path: Path):
        """Multiple threads concurrently writing snapshots do not crash or corrupt state."""
        client = AirtableClient("base_id", "pat.key", transport=lambda *a, **k: AirtableResponse(200, {"records": [{"id": "rec-1"}]}))

        def worker(thread_idx: int) -> dict[str, Any]:
            out_file = tmp_path / f"concurrent_snap_{thread_idx}.json"
            return ingest_snapshot(client, tables=("Departments", "People"), output_path=out_file)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 5
        for i in range(5):
            out_file = tmp_path / f"concurrent_snap_{i}.json"
            assert out_file.exists()
            data = json.loads(out_file.read_text(encoding="utf-8"))
            assert len(data["Departments"]) == 1
            assert len(data["People"]) == 1


# ===========================================================================
# 3. Network Failure, Retries & Status Code Boundary Tests
# ===========================================================================

class TestNetworkFailureAndRetriesAdversarial:
    """Stress-test network failures, exponential backoffs, status codes, and timeouts."""

    def test_partial_table_failure_aborts_without_writing_snapshot(self, tmp_path: Path):
        """If table 5 of 8 fails, ingest_snapshot must raise and not write partial output."""
        out_file = tmp_path / "partial_snapshot.json"
        attempt_count = 0

        def transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
            nonlocal attempt_count
            attempt_count += 1
            table = url.rsplit("/", 1)[-1]
            if table == "Candidates":
                return AirtableResponse(500, {"error": "Internal Server Error"})
            return AirtableResponse(200, {"records": [{"id": f"{table}-1"}]})

        client = AirtableClient("base_id", "pat.key", transport=transport, max_retries=1, sleep=lambda _: None)

        with pytest.raises(AirtableError, match="failed with status 500"):
            ingest_snapshot(client, output_path=out_file)

        assert not out_file.exists()

    def test_retry_exhaustion_on_429_rate_limiting(self):
        """Exhausting retries on 429 raises AirtableError with status 429."""
        attempts = 0
        delays: list[float] = []

        def transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
            nonlocal attempts
            attempts += 1
            return AirtableResponse(429, {}, {"Retry-After": "0.5"})

        client = AirtableClient("base_id", "pat.key", transport=transport, max_retries=3, sleep=delays.append)

        with pytest.raises(AirtableError, match="status 429"):
            client.fetch_table("Departments")

        assert attempts == 4  # Initial + 3 retries
        assert len(delays) == 3
        assert all(d == 0.5 for d in delays)

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    def test_retry_exhaustion_on_5xx_server_errors(self, status_code: int):
        """Exhausting retries on 5xx server errors raises AirtableError with exact status."""
        attempts = 0
        delays: list[float] = []

        def transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
            nonlocal attempts
            attempts += 1
            return AirtableResponse(status_code, {"error": "Server Error"})

        client = AirtableClient("base_id", "pat.key", transport=transport, max_retries=2, sleep=delays.append)

        with pytest.raises(AirtableError, match=f"status {status_code}"):
            client.fetch_table("Departments")

        assert attempts == 3  # 1 initial + 2 retries
        assert delays == [1.0, 2.0]  # Exponential backoff 2^0=1, 2^1=2

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
    def test_non_retryable_client_errors_fail_immediately(self, status_code: int):
        """4xx errors (except 429) must fail immediately without retrying."""
        attempts = 0

        def transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
            nonlocal attempts
            attempts += 1
            return AirtableResponse(status_code, {"error": "Client Error"})

        client = AirtableClient("base_id", "pat.key", transport=transport, max_retries=5, sleep=lambda _: None)

        with pytest.raises(AirtableError, match=f"status {status_code}"):
            client.fetch_table("Departments")

        assert attempts == 1  # ZERO retries on non-retryable 4xx errors

    def test_transport_exception_retry_exhaustion(self):
        """Transport-level exceptions (timeouts, socket errors) are retried until max_retries."""
        attempts = 0

        def transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
            nonlocal attempts
            attempts += 1
            raise TimeoutError("Gateway connection timed out")

        client = AirtableClient("base_id", "pat.key", transport=transport, max_retries=2, sleep=lambda _: None)

        with pytest.raises(AirtableError, match="request failed after retries"):
            client.fetch_table("Departments")

        assert attempts == 3

    @pytest.mark.parametrize("invalid_response_data", [
        "plain string body",
        [{"id": "rec-1"}],
        12345,
        None,
    ])
    def test_non_dict_json_body_raises_airtable_error(self, invalid_response_data: Any):
        """HTTP 200 response with non-dict JSON body raises AirtableError."""
        client = AirtableClient(
            "base_id",
            "pat.key",
            transport=lambda *a, **k: AirtableResponse(200, invalid_response_data),
        )
        with pytest.raises(AirtableError, match="JSON object required"):
            client.fetch_table("Departments")

    @pytest.mark.parametrize("bad_records", [
        "not a list",
        1234,
        None,
        {"id": "rec-1"},
        [1, 2, 3],                   # list of non-mappings
        ["str1", "str2"],           # list of strings
        [None],                      # list with None
    ])
    def test_invalid_records_envelope_raises_airtable_error(self, bad_records: Any):
        """HTTP 200 response with malformed records field raises AirtableError."""
        client = AirtableClient(
            "base_id",
            "pat.key",
            transport=lambda *a, **k: AirtableResponse(200, {"records": bad_records}),
        )
        with pytest.raises(AirtableError, match="records must be a list"):
            client.fetch_table("Departments")

    @pytest.mark.parametrize("bad_offset", [
        12345,
        True,
        ["nested_offset"],
        {"offset": "val"},
    ])
    def test_non_string_offset_raises_airtable_error(self, bad_offset: Any):
        """HTTP 200 response with non-string offset raises AirtableError."""
        client = AirtableClient(
            "base_id",
            "pat.key",
            transport=lambda *a, **k: AirtableResponse(200, {"records": [], "offset": bad_offset}),
        )
        with pytest.raises(AirtableError, match="offset must be a string"):
            client.fetch_table("Departments")

    @pytest.mark.parametrize("invalid_retry_after", [
        "not-a-number",
        "Wed, 21 Oct 2015 07:28:00 GMT",
        None,
        "-10.5",
    ])
    def test_invalid_retry_after_header_handled_gracefully(self, invalid_retry_after: Any):
        """Malformed or negative Retry-After headers fall back to default exponential backoff."""
        delays: list[float] = []
        calls = 0

        def transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
            nonlocal calls
            calls += 1
            if calls == 1:
                hdr = {"Retry-After": invalid_retry_after} if invalid_retry_after is not None else {}
                return AirtableResponse(429, {}, hdr)
            return AirtableResponse(200, {"records": []})

        client = AirtableClient("base_id", "pat.key", transport=transport, max_retries=2, sleep=delays.append)
        records = client.fetch_table("Departments")
        assert records == []
        assert len(delays) == 1
        assert delays[0] >= 0.0


# ===========================================================================
# 4. Schema Profiler Resilience with Extreme & Exotic Inputs
# ===========================================================================

class TestSchemaProfilerExtremeInputs:
    """Stress-test schema profiler with nested arrays, nulls, booleans, and unicode."""

    def test_boolean_vs_integer_disambiguation(self):
        """Strictly disambiguate Python bool (True/False) from integer (1/0)."""
        snapshot = {
            "TestTable": [
                {"id": "1", "fields": {"is_active": True, "count": 1, "flag": False, "zero": 0}},
                {"id": "2", "fields": {"is_active": False, "count": 42, "flag": True, "zero": 0}},
            ]
        }
        profiles = profile_all_tables(snapshot)
        fields = profiles["TestTable"].fields

        assert fields["is_active"] == {"boolean": 2}
        assert fields["count"] == {"number": 2}
        assert fields["flag"] == {"boolean": 2}
        assert fields["zero"] == {"number": 2}

    def test_mixed_boolean_and_number_in_same_column(self):
        """Same field holding bool in row 1 and number in row 2 records both kinds accurately."""
        snapshot = {
            "TestTable": [
                {"id": "1", "fields": {"mixed_val": True}},
                {"id": "2", "fields": {"mixed_val": 1}},
                {"id": "3", "fields": {"mixed_val": None}},
            ]
        }
        profiles = profile_all_tables(snapshot)
        fields = profiles["TestTable"].fields

        assert fields["mixed_val"] == {"boolean": 1, "number": 1, "null": 1}

    def test_nested_arrays_and_multidimensional_lists(self):
        """Nested arrays are classified as 'array'."""
        snapshot = {
            "TestTable": [
                {"id": "1", "fields": {"matrix": [[1, 2], [3, 4]], "tags": ["a", "b"]}},
            ]
        }
        profiles = profile_all_tables(snapshot)
        fields = profiles["TestTable"].fields

        assert fields["matrix"] == {"array": 1}
        assert fields["tags"] == {"array": 1}

    def test_deeply_nested_objects(self):
        """Deeply nested dictionaries are classified as 'object'."""
        snapshot = {
            "TestTable": [
                {"id": "1", "fields": {"deep": {"l1": {"l2": {"l3": {"val": 99}}}}}},
            ]
        }
        profiles = profile_all_tables(snapshot)
        fields = profiles["TestTable"].fields

        assert fields["deep"] == {"object": 1}

    def test_unicode_table_and_field_names(self):
        """Unicode table and field names profile accurately."""
        snapshot = {
            "📋 部门": [
                {"id": "1", "fields": {"名称": "技术部", "🌟 评分": 4.9}},
            ],
            "Департамент": [
                {"id": "2", "fields": {"имя": "IT", "бюджет": 500000}},
            ]
        }
        profiles = profile_all_tables(snapshot)
        assert "📋 部门" in profiles
        assert "Департамент" in profiles
        assert profiles["📋 部门"].fields["名称"] == {"string": 1}
        assert profiles["📋 部门"].fields["🌟 评分"] == {"number": 1}
        assert profiles["Департамент"].fields["имя"] == {"string": 1}
        assert profiles["Департамент"].fields["бюджет"] == {"number": 1}

    def test_non_string_field_keys(self):
        """Non-string dictionary keys (int, tuple, None) are stringified without crashing."""
        snapshot = {
            "TestTable": [
                {"id": "1", "fields": {123: "numeric_key", None: "none_key", (1, 2): "tuple_key"}},
            ]
        }
        profiles = profile_all_tables(snapshot)
        fields = profiles["TestTable"].fields

        assert "123" in fields
        assert "None" in fields
        assert "(1, 2)" in fields

    def test_non_mapping_records_in_table_list_are_skipped(self):
        """Non-dict items in records list (strings, ints, None) are safely skipped."""
        snapshot = {
            "Departments": [
                "not_a_record",
                12345,
                None,
                ["nested_list"],
                {"id": "dep-1", "fields": {"name": "Engineering"}},
            ]
        }
        profiles = profile_all_tables(snapshot)
        dept_prof = profiles["Departments"]

        assert dept_prof.record_count == 5
        assert dept_prof.fields == {"name": {"string": 1}}

    def test_exotic_numeric_types(self):
        """Exotic numeric values (inf, nan, float zero) are classified as 'number'."""
        snapshot = {
            "TestTable": [
                {"id": "1", "fields": {"nan_val": float("nan"), "inf_val": float("inf"), "zero": 0.0}},
            ]
        }
        profiles = profile_all_tables(snapshot)
        fields = profiles["TestTable"].fields

        assert fields["nan_val"] == {"number": 1}
        assert fields["inf_val"] == {"number": 1}
        assert fields["zero"] == {"number": 1}

    def test_empty_snapshot_and_none_table_records(self):
        """Empty snapshot returns empty dict, table with empty list profiles with record_count 0."""
        assert profile_all_tables({}) == {}
        profiles = profile_all_tables({"EmptyTable": []})
        assert profiles["EmptyTable"].record_count == 0
        assert profiles["EmptyTable"].fields == {}


# ===========================================================================
# 5. Secret Leakage & Credential Masking Under Adversarial Conditions
# ===========================================================================

class TestSecretLeakageAdversarial:
    """Strictly verify zero credentials leaked in tracebacks, exceptions, files, or strings."""

    def test_zero_secret_in_exception_traceback_on_transport_failure(self):
        """Traceback from transport failure must not leak API key."""
        def transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
            raise RuntimeError("Network connection dropped")

        client = AirtableClient("base_id", SECRET_TOKEN, transport=transport, max_retries=1, sleep=lambda _: None)

        try:
            client.fetch_table("Departments")
            pytest.fail("Should have raised AirtableError")
        except AirtableError:
            tb = traceback.format_exc()
            assert SECRET_TOKEN not in tb
            assert "SUPER_SENSITIVE" not in tb

    def test_zero_secret_in_exception_string_on_http_401(self):
        """HTTP 401 error message must not include secret token."""
        def transport(url: str, *, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
            return AirtableResponse(401, {"error": {"message": "Unauthorized token pat.XYZ"}})

        client = AirtableClient("base_id", SECRET_TOKEN, transport=transport, max_retries=0)

        try:
            client.fetch_table("Departments")
            pytest.fail("Should have raised AirtableError")
        except AirtableError as exc:
            err_msg = str(exc)
            err_repr = repr(exc)
            assert SECRET_TOKEN not in err_msg
            assert SECRET_TOKEN not in err_repr
            assert "SUPER_SENSITIVE" not in err_msg

    def test_zero_secret_in_written_snapshot_and_profile_json(self, tmp_path: Path):
        """Persisted snapshot file and schema profile JSON have zero trace of credentials."""
        out_file = tmp_path / "persisted_snapshot.json"

        client = AirtableClient(
            "base_id",
            SECRET_TOKEN,
            transport=lambda *a, **k: AirtableResponse(200, {"records": [{"id": "rec-1", "fields": {"data": 1}}]}),
        )
        snapshot = ingest_snapshot(client, tables=("Departments",), output_path=out_file)
        profiles = profile_all_tables(snapshot)

        file_bytes = out_file.read_bytes()
        assert SECRET_TOKEN.encode("utf-8") not in file_bytes
        assert b"SUPER_SENSITIVE" not in file_bytes

        profiles_json = json.dumps({k: v.to_dict() for k, v in profiles.items()})
        assert SECRET_TOKEN not in profiles_json
        assert "SUPER_SENSITIVE" not in profiles_json

    def test_client_repr_and_str_masking_comprehensive(self):
        """Client __repr__ and __str__ never display raw token under any inspection."""
        client = AirtableClient("base_123", SECRET_TOKEN, transport=lambda *a, **k: None)
        r = repr(client)
        s = str(client)

        assert SECRET_TOKEN not in r
        assert SECRET_TOKEN not in s
        assert "***" in r
        assert "***" in s
        assert "base_123" in r
        assert "base_123" in s

    def test_env_var_secret_not_leaked_in_init_errors(self, monkeypatch):
        """Initialization errors do not leak existing env secrets."""
        monkeypatch.setenv("AIRTABLE_API_KEY", SECRET_TOKEN)
        monkeypatch.delenv("AIRTABLE_BASE_ID", raising=False)

        with pytest.raises(AirtableError) as exc_info:
            AirtableClient()

        assert "AIRTABLE_BASE_ID is required" in str(exc_info.value)
        assert SECRET_TOKEN not in str(exc_info.value)

