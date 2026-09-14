"""Small, dependency-free, read-only Airtable client.

The client deliberately accepts an injectable transport so all application
logic can be exercised offline.  The default transport uses ``urllib`` and
only performs HTTP GET requests.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


class AirtableError(RuntimeError):
    """An ingestion, transport, or response validation failure."""


@dataclass(frozen=True)
class AirtableResponse:
    """Normalized transport response used by :class:`AirtableClient`."""

    status_code: int
    data: Mapping[str, Any] | None = None
    headers: Mapping[str, str] = field(default_factory=dict)


class Transport(Protocol):
    def __call__(
        self, url: str, *, headers: Mapping[str, str], params: Mapping[str, str]
    ) -> AirtableResponse: ...


DEFAULT_RATE_LIMIT_SECONDS: float = 0.2  # 5 requests per second Airtable constraint


@dataclass(frozen=True)
class SchemaProfile:
    """Observed field/type shape for a table snapshot."""

    table: str
    record_count: int
    fields: Mapping[str, Mapping[str, int]]

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to serializable plain dictionary."""
        return {
            "table": self.table,
            "record_count": self.record_count,
            "fields": {k: dict(v) for k, v in self.fields.items()},
        }


def _default_transport(
    url: str, *, headers: Mapping[str, str], params: Mapping[str, str]
) -> AirtableResponse:
    parts = urlsplit(url)
    safe_path = quote(parts.path, safe="/")
    quoted_url = urlunsplit((parts.scheme, parts.netloc, safe_path, parts.query, parts.fragment))
    query = urlencode(dict(params))
    request = Request(f"{quoted_url}?{query}" if query else quoted_url, headers=dict(headers), method="GET")
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - URL is caller-configured
            raw = response.read()
            data = json.loads(raw.decode("utf-8"))
            return AirtableResponse(response.status, data, dict(response.headers.items()))
    except HTTPError as exc:
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            data = None
        return AirtableResponse(exc.code, data, dict(exc.headers.items()))
    except (URLError, TimeoutError, OSError) as exc:
        raise AirtableError("Airtable transport failed") from exc


def _safe_table_name(table: str) -> str:
    # Keep paths deterministic and avoid path traversal from user-provided names.
    return hashlib.sha256(table.encode("utf-8")).hexdigest()[:20]


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def normalize_linked_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return copies with Airtable linked-record values represented by IDs.

    Airtable links are commonly arrays of ``{"id": "rec..."}`` objects.  The
    IDs are stable and useful to downstream normalization; any additional
    object keys are retained in ``<field>__records`` so unknown data is not lost.
    Non-link values are copied unchanged.
    """

    normalized: list[dict[str, Any]] = []
    for record in records:
        result = dict(record)
        fields = record.get("fields")
        if not isinstance(fields, Mapping):
            normalized.append(result)
            continue
        out_fields = dict(fields)
        for name, value in fields.items():
            if not isinstance(value, list) or not value or not all(
                isinstance(item, Mapping) and isinstance(item.get("id"), str) for item in value
            ):
                continue
            out_fields[name] = [item["id"] for item in value]
            out_fields[f"{name}__records"] = [dict(item) for item in value]
        result["fields"] = out_fields
        normalized.append(result)
    return normalized


class AirtableClient:
    """Read-only Airtable API client with retries and local snapshot replay."""

    def __init__(
        self,
        base_id: str | None = None,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.airtable.com/v0",
        transport: Transport | None = None,
        cache_dir: str | os.PathLike[str] | None = None,
        max_retries: int = 3,
        rate_limit_seconds: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_id = base_id or os.getenv("AIRTABLE_BASE_ID")
        self.api_key = api_key or os.getenv("AIRTABLE_API_KEY")
        if not self.base_id:
            raise AirtableError("AIRTABLE_BASE_ID is required")
        if not self.api_key:
            raise AirtableError("AIRTABLE_API_KEY is required")
        self.base_url = base_url.rstrip("/")
        self.transport = transport or _default_transport
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.max_retries = max(0, max_retries)
        self.rate_limit_seconds = max(0.0, rate_limit_seconds)
        self._sleep = sleep
        self._last_request = 0.0

    def __repr__(self) -> str:
        return f"AirtableClient(base_id={self.base_id!r}, api_key='***', base_url={self.base_url!r})"

    def __str__(self) -> str:
        return f"AirtableClient(base_id={self.base_id!r}, api_key='***')"

    @property
    def _headers(self) -> Mapping[str, str]:
        # Never expose the token in exceptions or logs; callers only receive this mapping.
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def fetch_table(
        self,
        table: str,
        *,
        params: Mapping[str, str] | None = None,
        use_cache: bool = True,
        normalize_links: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch all records for ``table``, following Airtable offsets."""
        cache_path = self._cache_path(table, params)
        if use_cache and cache_path and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                records = payload["records"]
                if not isinstance(records, list):
                    raise ValueError
                return normalize_linked_records(records) if normalize_links else records
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                raise AirtableError("Invalid Airtable snapshot cache") from exc

        records: list[dict[str, Any]] = []
        offset: str | None = None
        query = dict(params or {})
        while True:
            if offset:
                query["offset"] = offset
            payload = self._request(f"{self.base_url}/{self.base_id}/{table}", query)
            page = payload.get("records")
            if not isinstance(page, list) or not all(isinstance(item, Mapping) for item in page):
                raise AirtableError("Malformed Airtable response: records must be a list")
            records.extend(dict(item) for item in page)
            offset_value = payload.get("offset")
            if not offset_value:
                break
            if not isinstance(offset_value, str):
                raise AirtableError("Malformed Airtable response: offset must be a string")
            offset = offset_value

        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({"table": table, "records": records}, sort_keys=True, indent=2),
                encoding="utf-8",
            )
        return normalize_linked_records(records) if normalize_links else records

    def profile_schema(self, table: str, *, records: Iterable[Mapping[str, Any]] | None = None) -> SchemaProfile:
        rows = list(records) if records is not None else self.fetch_table(table)
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
                fields.setdefault(str(key), {})[kind] = fields.setdefault(str(key), {}).get(kind, 0) + 1
        return SchemaProfile(table=table, record_count=len(rows), fields=fields)

    def _cache_path(self, table: str, params: Mapping[str, str] | None) -> Path | None:
        if self.cache_dir is None:
            return None
        suffix = hashlib.sha256(json.dumps(dict(params or {}), sort_keys=True).encode()).hexdigest()[:12]
        return self.cache_dir / f"{_safe_table_name(table)}-{suffix}.json"

    def _request(self, url: str, params: Mapping[str, str]) -> Mapping[str, Any]:
        for attempt in range(self.max_retries + 1):
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.rate_limit_seconds:
                self._sleep(self.rate_limit_seconds - elapsed)
            self._last_request = time.monotonic()
            try:
                response = self.transport(url, headers=self._headers, params=params)
            except Exception as exc:  # transport implementations may use varied exceptions
                if attempt >= self.max_retries:
                    raise AirtableError("Airtable request failed after retries") from exc
                self._sleep(min(2**attempt, 30))
                continue
            if response.status_code == 200:
                if not isinstance(response.data, Mapping):
                    raise AirtableError("Malformed Airtable response: JSON object required")
                return response.data
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt >= self.max_retries:
                raise AirtableError(f"Airtable request failed with status {response.status_code}")
            retry_after = response.headers.get("Retry-After") if response.headers else None
            try:
                delay = max(0.0, float(retry_after)) if retry_after is not None else min(2**attempt, 30)
            except (TypeError, ValueError):
                delay = min(2**attempt, 30)
            self._sleep(delay)
        raise AirtableError("Airtable request failed")
