from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from recruitment_intelligence.airtable import AirtableClient, AirtableError, AirtableResponse, normalize_linked_records


def test_pagination_and_link_normalization():
    calls: list[dict[str, str]] = []

    def transport(url, *, headers, params):
        calls.append(dict(params))
        if len(calls) == 1:
            return AirtableResponse(200, {"records": [{"id": "r1", "fields": {"source": [{"id": "r2"}]}}], "offset": "next"})
        return AirtableResponse(200, {"records": [{"id": "r3", "fields": {"source": []}}]})

    client = AirtableClient("base", "secret-token", transport=transport)
    rows = client.fetch_table("Applications")
    assert [r["id"] for r in rows] == ["r1", "r3"]
    assert rows[0]["fields"]["source"] == ["r2"]
    assert rows[0]["fields"]["source__records"] == [{"id": "r2"}]
    assert calls == [{}, {"offset": "next"}]


def test_retry_after_429_and_server_error_without_leaking_secret():
    responses = [AirtableResponse(429, {}, {"Retry-After": "0.25"}), AirtableResponse(500), AirtableResponse(200, {"records": []})]
    delays: list[float] = []

    def transport(url, *, headers, params):
        assert "secret-token" in headers["Authorization"]
        return responses.pop(0)

    client = AirtableClient("base", "secret-token", transport=transport, sleep=delays.append)
    assert client.fetch_table("T") == []
    assert delays[:2] == [0.25, 2]


def test_network_failure_is_bounded():
    attempts = 0

    def transport(url, *, headers, params):
        nonlocal attempts
        attempts += 1
        raise OSError("secret-token should not escape")

    client = AirtableClient("base", "secret-token", transport=transport, max_retries=2, sleep=lambda _: None)
    with pytest.raises(AirtableError, match="request failed"):
        client.fetch_table("T")
    assert attempts == 3


def test_snapshot_cache_replay():
    tmp_path = Path(".airtable-test-cache")
    shutil.rmtree(tmp_path, ignore_errors=True)
    calls = 0

    def transport(url, *, headers, params):
        nonlocal calls
        calls += 1
        return AirtableResponse(200, {"records": [{"id": "r1", "fields": {"x": 1}}]})

    client = AirtableClient("base", "secret-token", transport=transport, cache_dir=tmp_path)
    assert client.fetch_table("T") == client.fetch_table("T")
    assert calls == 1
    assert list(tmp_path.glob("*.json"))
    assert "secret-token" not in list(tmp_path.glob("*.json"))[0].read_text()
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_profile_schema_and_malformed_response():
    client = AirtableClient("base", "key", transport=lambda *args, **kwargs: AirtableResponse(200, {"records": "bad"}))
    with pytest.raises(AirtableError, match="records must be a list"):
        client.fetch_table("T")

    profile = client.profile_schema("T", records=[{"fields": {"name": "A", "score": 1}}, {"fields": {"name": None, "score": 2}}])
    assert profile.record_count == 2
    assert profile.fields["name"] == {"string": 1, "null": 1}
    assert profile.fields["score"] == {"number": 2}


def test_env_credentials_and_normalizer_preserves_unknown_fields(monkeypatch):
    monkeypatch.setenv("AIRTABLE_BASE_ID", "base")
    monkeypatch.setenv("AIRTABLE_API_KEY", "key")
    client = AirtableClient(transport=lambda *args, **kwargs: AirtableResponse(200, {"records": []}))
    assert client.base_id == "base"
    row = normalize_linked_records([{"id": "r", "unknown": 3, "fields": {"person": [{"id": "p", "name": "X"}]}}])[0]
    assert row["unknown"] == 3
    assert row["fields"]["person"] == ["p"]
    assert row["fields"]["person__records"] == [{"id": "p", "name": "X"}]


def test_missing_credentials_fail(monkeypatch):
    monkeypatch.delenv("AIRTABLE_BASE_ID", raising=False)
    monkeypatch.delenv("AIRTABLE_API_KEY", raising=False)
    with pytest.raises(AirtableError, match="BASE_ID"):
        AirtableClient()


def test_client_repr_and_str_mask_secret():
    client = AirtableClient("base_123", "super-secret-pat-key", transport=lambda *args, **kwargs: None)
    assert "super-secret" not in repr(client)
    assert "***" in repr(client)
    assert "super-secret" not in str(client)
    assert "***" in str(client)


def test_schema_profile_to_dict_and_flat_record_profiling():
    client = AirtableClient("base", "key", transport=lambda *args, **kwargs: None)
    profile = client.profile_schema("T", records=[{"id": "rec1", "title": "Eng", "headcount": 5}])
    assert profile.record_count == 1
    assert profile.fields["title"] == {"string": 1}
    assert profile.fields["headcount"] == {"number": 1}

    as_dict = profile.to_dict()
    assert as_dict == {
        "table": "T",
        "record_count": 1,
        "fields": {"title": {"string": 1}, "headcount": {"number": 1}},
    }

