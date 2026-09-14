from __future__ import annotations

import json
from pathlib import Path

import recruitment_intelligence.pipeline as pipeline


def test_load_live_snapshot_reads_dotenv_without_exposing_credentials(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    def fake_ingest(client, **kwargs):
        captured["client"] = client
        captured.update(kwargs)
        return {"Applications": [{"id": "app-1"}]}

    (tmp_path / ".env").write_text(
        "AIRTABLE_API_KEY=pat_test_secret\n"
        "AIRTABLE_BASE_ID=app_test_base\n"
        "AIRTABLE_TABLES=Applications,Offers\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AIRTABLE_API_KEY", raising=False)
    monkeypatch.delenv("AIRTABLE_BASE_ID", raising=False)
    monkeypatch.setattr(pipeline, "AirtableClient", FakeClient)
    monkeypatch.setattr(pipeline, "ingest_snapshot", fake_ingest)

    snapshot = pipeline.load_live_snapshot(output_path=tmp_path / "snapshot.json")

    assert snapshot == {"Applications": [{"id": "app-1"}]}
    assert captured["tables"] == ("Applications", "Offers")
    assert captured["output_path"] == tmp_path / "snapshot.json"
    assert captured["use_cache"] is False


def test_run_pipeline_live_uses_fetched_snapshot_and_writes_artifacts(monkeypatch, tmp_path: Path):
    fixture = json.loads(Path("fixtures/clean_snapshot.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(pipeline, "load_live_snapshot", lambda **kwargs: fixture)

    result = pipeline.run_pipeline(
        live=True,
        as_of="2025-02-01",
        include_cost_appendix=False,
        output_dir=tmp_path / "outputs",
    )

    assert result["briefing"].generated_at == "2025-02-01T00:00:00+00:00"
    assert (tmp_path / "outputs" / "briefing.json").is_file()
    assert (tmp_path / "outputs" / "findings.json").is_file()
