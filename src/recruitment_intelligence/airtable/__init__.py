"""Read-only Airtable ingestion and snapshot utilities."""

from .client import (
    DEFAULT_RATE_LIMIT_SECONDS,
    AirtableClient,
    AirtableError,
    AirtableResponse,
    SchemaProfile,
    normalize_linked_records,
)
from .ingest import (
    CANONICAL_TABLES,
    ingest_snapshot,
    load_snapshot,
    profile_all_tables,
)

__all__ = [
    "CANONICAL_TABLES",
    "DEFAULT_RATE_LIMIT_SECONDS",
    "AirtableClient",
    "AirtableError",
    "AirtableResponse",
    "SchemaProfile",
    "ingest_snapshot",
    "load_snapshot",
    "normalize_linked_records",
    "profile_all_tables",
]

