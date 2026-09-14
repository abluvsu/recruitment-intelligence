"""Adversarial stress-testing for Milestone M2.

Rigorous stress-testing of:
1. Downstream consumption across clean, dirty, and sparse offline fixtures.
2. Zero unhandled exceptions and zero ZeroDivisionError across quality and analytics.
3. Verification of all 7 quality check types on dirty snapshot with exact issue breakdown.
4. Rate limiting timing under synthetic clocks enforcing 5 req/s constraint.
5. Non-destructive link normalization preserving unknown raw keys and nested objects.
6. Extreme edge cases, malformed snapshots, corruptions, and secret redaction.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping
import pytest

from recruitment_intelligence.airtable.client import (
    DEFAULT_RATE_LIMIT_SECONDS,
    AirtableClient,
    AirtableError,
    AirtableResponse,
    normalize_linked_records,
)
from recruitment_intelligence.airtable.ingest import (
    CANONICAL_TABLES,
    load_snapshot,
    profile_all_tables,
)
from recruitment_intelligence.analytics.metrics import (
    aging,
    funnel_transitions,
    offer_acceptance_rate,
    sensitivity_analysis,
    source_department_segmentation,
    source_effectiveness,
    stalled_applications,
    table_counts,
)
from recruitment_intelligence.quality.checks import (
    affected_metrics,
    chronology_errors,
    duplicate_records,
    invalid_dates,
    missing_values,
    orphan_links,
    quality_confidence,
    run_quality_checks,
    source_taxonomy_issues,
    status_inconsistencies,
)


# ---------------------------------------------------------------------------
# Helpers & Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
CLEAN_PATH = FIXTURES_DIR / "clean_snapshot.json"
DIRTY_PATH = FIXTURES_DIR / "dirty_snapshot.json"
SPARSE_PATH = FIXTURES_DIR / "sparse_snapshot.json"


@pytest.fixture
def clean_snapshot() -> dict[str, list[dict[str, Any]]]:
    return load_snapshot(CLEAN_PATH)


@pytest.fixture
def dirty_snapshot() -> dict[str, list[dict[str, Any]]]:
    return load_snapshot(DIRTY_PATH)


@pytest.fixture
def sparse_snapshot() -> dict[str, list[dict[str, Any]]]:
    return load_snapshot(SPARSE_PATH)


# ---------------------------------------------------------------------------
# 1. Clean Snapshot Downstream Consumption
# ---------------------------------------------------------------------------

class TestCleanSnapshotDownstream:
    """Stress tests on clean_snapshot.json."""

    def test_canonical_table_coverage(self, clean_snapshot: dict[str, list[dict[str, Any]]]) -> None:
        """Verify all 8 canonical tables are present with expected minimum counts."""
        assert set(CANONICAL_TABLES).issubset(set(clean_snapshot.keys()))
        profiles = profile_all_tables(clean_snapshot)
        assert len(profiles) >= 8
        total_records = sum(p.record_count for p in profiles.values())
        assert total_records == 39
        assert profiles["Departments"].record_count == 3
        assert profiles["People"].record_count == 4
        assert profiles["Job Openings"].record_count == 3
        assert profiles["Candidates"].record_count == 8
        assert profiles["Applications"].record_count == 10
        assert profiles["Interviews"].record_count == 6
        assert profiles["Offers"].record_count == 3
        assert profiles["Findings"].record_count == 2

    def test_quality_checks_zero_issues(self, clean_snapshot: dict[str, list[dict[str, Any]]]) -> None:
        """Clean snapshot must have 0 issues and high confidence across all checks."""
        report = run_quality_checks(clean_snapshot)
        assert report["issues"] == []
        assert report["confidence"] == "high"
        assert report["summary"]["issue_count"] == 0
        assert report["summary"]["by_check"] == {}

        # Test each individual check function directly
        assert missing_values(clean_snapshot) == []
        assert duplicate_records(clean_snapshot) == []
        assert orphan_links(clean_snapshot) == []
        assert invalid_dates(clean_snapshot) == []
        assert chronology_errors(clean_snapshot) == []
        assert status_inconsistencies(clean_snapshot) == []
        assert source_taxonomy_issues(clean_snapshot) == []

    def test_analytics_metrics_clean_execution(self, clean_snapshot: dict[str, list[dict[str, Any]]]) -> None:
        """Verify deterministic outputs on all analytics functions without exceptions."""
        counts = table_counts(clean_snapshot)
        assert len(counts) == 8
        assert sum(counts.values()) == 39

        sources = source_effectiveness(clean_snapshot)
        assert set(sources.keys()) == {"Agency", "Careers page", "Job board", "Referral"}
        for name, metrics in sources.items():
            assert metrics["applications"] > 0
            assert 0.0 <= metrics["hire_conversion_rate"] <= 1.0
            assert 0.0 <= metrics["offer_to_hire_rate"] <= 1.0
            assert isinstance(metrics["role_mix"], dict)

        oar = offer_acceptance_rate(clean_snapshot)
        assert oar["offers"] == 3
        assert oar["accepted"] == 2
        assert oar["rate"] == pytest.approx(2 / 3)

        transitions = funnel_transitions(clean_snapshot)
        assert sum(transitions.values()) == 10
        assert transitions["hired"] >= 1

        stalled = stalled_applications(clean_snapshot, threshold_days=14, as_of="2025-02-15")
        assert len(stalled) >= 1
        assert any(item["application_id"] == "app-003" for item in stalled)

        app_ages = aging(clean_snapshot, as_of="2025-02-15")
        assert len(app_ages) == 10
        for item in app_ages:
            assert item["age_days"] >= 0

        segmentation = source_department_segmentation(clean_snapshot)
        assert set(segmentation.keys()) == {"Agency", "Careers page", "Job board", "Referral"}

        sens = sensitivity_analysis(clean_snapshot, {"exclude_app1": ["app-001"]})
        assert "baseline" in sens
        assert "exclude_app1" in sens["scenarios"]


# ---------------------------------------------------------------------------
# 2. Dirty Snapshot Downstream Consumption & Exact Issue Verification
# ---------------------------------------------------------------------------

class TestDirtySnapshotDownstream:
    """Stress tests on dirty_snapshot.json."""

    def test_dirty_snapshot_all_7_quality_checks_triggered(
        self, dirty_snapshot: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Verify dirty snapshot triggers all 7 check types with low confidence."""
        report = run_quality_checks(dirty_snapshot)
        assert report["confidence"] == "low"
        assert len(report["issues"]) == 22

        by_check = report["summary"]["by_check"]
        expected_checks = {
            "chronology_error": 3,
            "duplicate_record": 1,
            "invalid_date": 3,
            "missing_value": 5,
            "orphan_link": 6,
            "source_taxonomy": 1,
            "status_inconsistency": 3,
        }
        assert by_check == expected_checks

        # Verify each individual check function matches the count exactly
        assert len(missing_values(dirty_snapshot)) == 5
        assert len(duplicate_records(dirty_snapshot)) == 1
        assert len(orphan_links(dirty_snapshot)) == 6
        assert len(invalid_dates(dirty_snapshot)) == 3
        assert len(chronology_errors(dirty_snapshot)) == 3
        assert len(status_inconsistencies(dirty_snapshot)) == 3
        assert len(source_taxonomy_issues(dirty_snapshot)) == 1

    def test_dirty_snapshot_issue_structure(
        self, dirty_snapshot: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Every issue must have valid keys, non-empty affected records, and impact."""
        report = run_quality_checks(dirty_snapshot)
        for issue in report["issues"]:
            assert issue["check"] in {
                "chronology_error",
                "duplicate_record",
                "invalid_date",
                "missing_value",
                "orphan_link",
                "source_taxonomy",
                "status_inconsistency",
            }
            assert issue["severity"] in {"low", "medium", "high", "critical"}
            assert issue["confidence"] in {"low", "medium", "high"}
            assert len(issue["affected_records"]) > 0
            assert len(issue["metric_impact"]) > 0
            assert isinstance(issue["message"], str) and len(issue["message"]) > 5

        # Verify affected_metrics aggregation
        impacts = affected_metrics(report["issues"])
        assert len(impacts) == 7
        for check, metrics in impacts.items():
            assert len(metrics) > 0

    def test_dirty_snapshot_analytics_resilience(
        self, dirty_snapshot: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Analytics functions must process dirty data without throwing exceptions."""
        counts = table_counts(dirty_snapshot)
        assert len(counts) == 8

        sources = source_effectiveness(dirty_snapshot)
        assert isinstance(sources, dict)
        for name, metrics in sources.items():
            assert 0.0 <= metrics["hire_conversion_rate"] <= 1.0
            assert 0.0 <= metrics["offer_to_hire_rate"] <= 1.0

        oar = offer_acceptance_rate(dirty_snapshot)
        assert isinstance(oar["rate"], float)
        assert 0.0 <= oar["rate"] <= 1.0

        transitions = funnel_transitions(dirty_snapshot)
        assert isinstance(transitions, dict)

        stalled = stalled_applications(dirty_snapshot, threshold_days=14, as_of="2025-02-15")
        assert isinstance(stalled, list)

        app_ages = aging(dirty_snapshot, as_of="2025-02-15")
        assert isinstance(app_ages, list)
        for item in app_ages:
            assert item["age_days"] >= 0

        segmentation = source_department_segmentation(dirty_snapshot)
        assert isinstance(segmentation, dict)

        sens = sensitivity_analysis(dirty_snapshot, {"drop_orphans": ["cand-dirty-orphan-person"]})
        assert "baseline" in sens
        assert "drop_orphans" in sens["scenarios"]


# ---------------------------------------------------------------------------
# 3. Sparse Snapshot Boundary & Zero-Division Safety
# ---------------------------------------------------------------------------

class TestSparseSnapshotBoundary:
    """Stress tests on sparse_snapshot.json and empty dict structures."""

    def test_sparse_snapshot_profiling(
        self, sparse_snapshot: dict[str, list[dict[str, Any]]]
    ) -> None:
        profiles = profile_all_tables(sparse_snapshot)
        assert len(profiles) == 8
        for table, prof in profiles.items():
            assert prof.record_count == 0
            assert prof.fields == {}

    def test_sparse_snapshot_quality_confidence(
        self, sparse_snapshot: dict[str, list[dict[str, Any]]]
    ) -> None:
        report = run_quality_checks(sparse_snapshot)
        assert report["issues"] == []
        assert report["confidence"] == "insufficient"
        assert report["summary"]["total_records"] == 0
        assert report["summary"]["issue_count"] == 0

    def test_sparse_snapshot_analytics_zero_division(
        self, sparse_snapshot: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Every analytics function must return safe defaults with zero division."""
        counts = table_counts(sparse_snapshot)
        assert all(count == 0 for count in counts.values())

        sources = source_effectiveness(sparse_snapshot)
        assert sources == {}

        oar = offer_acceptance_rate(sparse_snapshot)
        assert oar["accepted"] == 0
        assert oar["offers"] == 0
        assert oar["rate"] == 0.0
        assert oar["confidence"] == "low"

        assert funnel_transitions(sparse_snapshot) == {}
        assert stalled_applications(sparse_snapshot) == []
        assert aging(sparse_snapshot) == []
        assert source_department_segmentation(sparse_snapshot) == {}

        sens = sensitivity_analysis(sparse_snapshot)
        assert sens == {"baseline": {}, "scenarios": {}}

    def test_completely_empty_dict_resilience(self) -> None:
        """Functions must tolerate {} root dictionary without crashing."""
        empty: dict[str, list[dict[str, Any]]] = {}
        assert profile_all_tables(empty) == {}
        assert table_counts(empty) == {}
        assert source_effectiveness(empty) == {}
        assert offer_acceptance_rate(empty)["rate"] == 0.0
        assert funnel_transitions(empty) == {}
        assert stalled_applications(empty) == []
        assert aging(empty) == []
        assert source_department_segmentation(empty) == {}
        assert sensitivity_analysis(empty) == {"baseline": {}, "scenarios": {}}

        report = run_quality_checks(empty)
        assert report["issues"] == []
        assert report["confidence"] == "insufficient"


# ---------------------------------------------------------------------------
# 4. Rate Limiting Cadence under Synthetic Clocks (5 req/s)
# ---------------------------------------------------------------------------

class TestRateLimitingCadence:
    """Rigorous timing checks for AirtableClient rate-limiting under synthetic clocks."""

    def test_synthetic_clock_5_requests_per_second_cadence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ensure consecutive rapid requests enforce rate_limit_seconds sleep interval."""
        simulated_time = [1000.0]
        sleep_durations: list[float] = []

        def mock_monotonic() -> float:
            return simulated_time[0]

        def mock_sleep(seconds: float) -> None:
            sleep_durations.append(seconds)
            simulated_time[0] += seconds

        monkeypatch.setattr("time.monotonic", mock_monotonic)

        # 5 req/s -> 0.2s interval
        rate_limit = DEFAULT_RATE_LIMIT_SECONDS
        assert rate_limit == 0.2

        client = AirtableClient(
            base_id="appTestBase",
            api_key="patTestKey",
            rate_limit_seconds=rate_limit,
            sleep=mock_sleep,
            transport=lambda url, headers, params: AirtableResponse(200, {"records": []}),
        )

        # Fire 6 consecutive requests rapidly
        for _ in range(6):
            client.fetch_table("TestTable", use_cache=False)

        # Request 1: last_request=0.0 -> elapsed=1000.0 > 0.2 -> no sleep
        # Requests 2 to 6: elapsed=0.0 -> sleeps 0.2s each
        assert len(sleep_durations) == 5
        for duration in sleep_durations:
            assert pytest.approx(duration, abs=1e-6) == 0.2
        assert pytest.approx(simulated_time[0], abs=1e-6) == 1001.0

    def test_synthetic_clock_no_sleep_when_sufficiently_spaced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When requests arrive after the rate-limit window, sleep is not invoked."""
        simulated_time = [500.0]
        sleep_durations: list[float] = []

        def mock_monotonic() -> float:
            return simulated_time[0]

        def mock_sleep(seconds: float) -> None:
            sleep_durations.append(seconds)
            simulated_time[0] += seconds

        monkeypatch.setattr("time.monotonic", mock_monotonic)

        client = AirtableClient(
            base_id="appTestBase",
            api_key="patTestKey",
            rate_limit_seconds=0.2,
            sleep=mock_sleep,
            transport=lambda url, headers, params: AirtableResponse(200, {"records": []}),
        )

        # Request 1
        client.fetch_table("TestTable", use_cache=False)
        # Advance simulated time by 0.5s (> 0.2s)
        simulated_time[0] += 0.5
        # Request 2
        client.fetch_table("TestTable", use_cache=False)
        # Advance simulated time by 0.3s (> 0.2s)
        simulated_time[0] += 0.3
        # Request 3
        client.fetch_table("TestTable", use_cache=False)

        assert sleep_durations == []

    def test_synthetic_clock_partial_sleep_interval(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If 0.05s has elapsed, client must sleep exactly remaining 0.15s."""
        simulated_time = [100.0]
        sleep_durations: list[float] = []

        def mock_monotonic() -> float:
            return simulated_time[0]

        def mock_sleep(seconds: float) -> None:
            sleep_durations.append(seconds)
            simulated_time[0] += seconds

        monkeypatch.setattr("time.monotonic", mock_monotonic)

        client = AirtableClient(
            base_id="appTestBase",
            api_key="patTestKey",
            rate_limit_seconds=0.2,
            sleep=mock_sleep,
            transport=lambda url, headers, params: AirtableResponse(200, {"records": []}),
        )

        # Request 1
        client.fetch_table("TestTable", use_cache=False)
        # 0.05s passes before request 2
        simulated_time[0] += 0.05
        client.fetch_table("TestTable", use_cache=False)

        assert len(sleep_durations) == 1
        assert pytest.approx(sleep_durations[0], abs=1e-6) == 0.15


# ---------------------------------------------------------------------------
# 5. Link Normalization Non-Destructive Invariants
# ---------------------------------------------------------------------------

class TestLinkNormalizationAdversarial:
    """Stress testing of normalize_linked_records."""

    def test_input_deep_immutability(self) -> None:
        """Original records mapping and nested structures must not be modified."""
        raw = [
            {
                "id": "rec_01",
                "custom_envelope_key": "do_not_touch",
                "createdTime": "2025-01-01T00:00:00.000Z",
                "fields": {
                    "department": [{"id": "dep_1", "name": "Eng", "extra": {"k": "v"}}],
                    "candidate": [{"id": "cand_1"}],
                    "string_field": "hello",
                    "tags": ["alpha", "beta"],
                    "scores": [1, 2, 3],
                    "empty_list": [],
                    "nested_map": {"x": 10},
                    "none_field": None,
                },
            }
        ]
        snapshot_before = copy.deepcopy(raw)
        result = normalize_linked_records(raw)

        # Must not mutate original input
        assert raw == snapshot_before

        # Must return normalized record
        rec = result[0]
        assert rec["id"] == "rec_01"
        assert rec["custom_envelope_key"] == "do_not_touch"
        assert rec["createdTime"] == "2025-01-01T00:00:00.000Z"

        f = rec["fields"]
        assert f["department"] == ["dep_1"]
        assert f["department__records"] == [{"id": "dep_1", "name": "Eng", "extra": {"k": "v"}}]
        assert f["candidate"] == ["cand_1"]
        assert f["candidate__records"] == [{"id": "cand_1"}]
        assert f["string_field"] == "hello"
        assert f["tags"] == ["alpha", "beta"]
        assert f["scores"] == [1, 2, 3]
        assert f["empty_list"] == []
        assert f["nested_map"] == {"x": 10}
        assert f["none_field"] is None

    def test_mixed_and_invalid_link_arrays_not_corrupted(self) -> None:
        """Arrays that do not strictly match [{"id": "str"}, ...] must be left untouched."""
        raw = [
            {
                "id": "rec_02",
                "fields": {
                    "invalid_links_mixed": [{"id": "dep_1"}, "not_a_mapping"],
                    "invalid_links_no_id": [{"name": "no id"}],
                    "invalid_links_int_id": [{"id": 12345}],
                    "invalid_links_none_id": [{"id": None}],
                },
            }
        ]
        result = normalize_linked_records(raw)
        f = result[0]["fields"]
        assert f["invalid_links_mixed"] == [{"id": "dep_1"}, "not_a_mapping"]
        assert "invalid_links_mixed__records" not in f

        assert f["invalid_links_no_id"] == [{"name": "no id"}]
        assert "invalid_links_no_id__records" not in f

        assert f["invalid_links_int_id"] == [{"id": 12345}]
        assert "invalid_links_int_id__records" not in f

        assert f["invalid_links_none_id"] == [{"id": None}]
        assert "invalid_links_none_id__records" not in f

    def test_flat_records_and_non_mapping_fields(self) -> None:
        """Records with flat structures or missing/invalid 'fields' must pass through."""
        raw = [
            {"id": "flat_1", "name": "Alice", "role": "Eng"},
            {"id": "flat_2", "fields": None},
            {"id": "flat_3", "fields": "not_a_dict"},
        ]
        result = normalize_linked_records(raw)
        assert len(result) == 3
        assert result[0] == {"id": "flat_1", "name": "Alice", "role": "Eng"}
        assert result[1] == {"id": "flat_2", "fields": None}
        assert result[2] == {"id": "flat_3", "fields": "not_a_dict"}


# ---------------------------------------------------------------------------
# 6. Malformed Snapshots & Error Handling
# ---------------------------------------------------------------------------

class TestSnapshotValidationAdversarial:
    """Stress testing load_snapshot and profile_all_tables error boundaries."""

    def test_load_snapshot_non_existent_file(self, tmp_path: Path) -> None:
        with pytest.raises(AirtableError, match="Snapshot file not found"):
            load_snapshot(tmp_path / "non_existent.json")

    def test_load_snapshot_invalid_json(self, tmp_path: Path) -> None:
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{ unquoted_key: 123, }", encoding="utf-8")
        with pytest.raises(AirtableError, match="Invalid JSON"):
            load_snapshot(bad_json)

    def test_load_snapshot_root_not_mapping(self, tmp_path: Path) -> None:
        bad_root = tmp_path / "bad_root.json"
        bad_root.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(AirtableError, match="root must be a mapping"):
            load_snapshot(bad_root)

    def test_load_snapshot_table_not_list(self, tmp_path: Path) -> None:
        bad_table = tmp_path / "bad_table.json"
        bad_table.write_text(json.dumps({"Departments": "not_a_list"}), encoding="utf-8")
        with pytest.raises(AirtableError, match="records for table 'Departments' must be a list"):
            load_snapshot(bad_table)

    def test_profile_all_tables_tolerates_corrupted_rows(self) -> None:
        """profile_all_tables gracefully skips non-mapping entries in table row lists."""
        corrupted = {
            "Departments": [
                {"id": "dep-1", "fields": {"name": "Eng"}},
                "corrupted_row_string",
                None,
                12345,
                {"id": "dep-2", "name": "FlatSales"},
            ]
        }
        profiles = profile_all_tables(corrupted)
        prof = profiles["Departments"]
        assert prof.record_count == 5
        assert "name" in prof.fields
        assert prof.fields["name"]["string"] == 2


# ---------------------------------------------------------------------------
# 7. Secret Redaction Adversarial Hardening
# ---------------------------------------------------------------------------

class TestSecretRedactionAdversarial:
    """Verify secrets are strictly forbidden from leaking in string reprs and errors."""

    def test_api_key_never_leaks_in_repr_or_str(self) -> None:
        super_secret = "pat.SECRET_TOKEN_VERY_CONFIDENTIAL_123456789"
        client = AirtableClient(base_id="appTestBase", api_key=super_secret)

        rep = repr(client)
        st = str(client)

        assert super_secret not in rep
        assert super_secret not in st
        assert "api_key='***'" in rep
        assert "api_key='***'" in st

    def test_api_key_never_leaks_in_exceptions(self) -> None:
        super_secret = "pat.SECRET_TOKEN_VERY_CONFIDENTIAL_123456789"

        def failing_transport(url: str, headers: Mapping[str, str], params: Mapping[str, str]) -> AirtableResponse:
            raise RuntimeError(f"Simulated network blowup with headers: {headers}")

        client = AirtableClient(
            base_id="appTestBase",
            api_key=super_secret,
            transport=failing_transport,
            max_retries=1,
            sleep=lambda s: None,
        )

        with pytest.raises(AirtableError) as exc_info:
            client.fetch_table("TestTable", use_cache=False)

        # The message of AirtableError must not contain the secret
        assert super_secret not in str(exc_info.value)
