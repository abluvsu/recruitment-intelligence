# Project: Recruitment Intelligence Founder Operating System

## Architecture
This system converts read-only Airtable recruitment data into an evidence-backed founder operating system answering Q1–Q5 deterministically, generating advisory candidate action queues, diagnosing data quality, and producing daily recruitment briefings.

The system follows a strict Directed Acyclic Graph (DAG) across layer boundaries:
- `src/recruitment_intelligence/domain/`: Root layer with zero dependencies. Defines frozen slotted dataclasses (`Serializable`), enums, operational contracts (`EvidenceReference`, `MetricClaim`, `Finding`, `CandidateRecommendation`, `Briefing`, `AgentRequest`, `AgentResult`).
- `src/recruitment_intelligence/airtable/`: Read-only ingestion, 5 req/s rate-limiting, 100-record pagination, exponential backoff retries, local JSON snapshot caching (`data/raw/airtable_snapshot.json`), link normalization, and programmatic schema profiling across all 8 tables.
- `src/recruitment_intelligence/analytics/`: Pure deterministic Python analytics (no LLM, no invented values). Computes table counts (Q1), source effectiveness & ranking vs effort (Q2), offer acceptance rate with justified denominator (Q3), funnel stage-to-stage conversion, aging, and bottleneck diagnosis (Q4), with strict `MetricClaim` + `EvidenceReference` wrapping.
- `src/recruitment_intelligence/quality/`: Data quality checks (missing FKs, orphans, chronological timestamp paradoxes, unmapped enums) and counterfactual metric sensitivity analysis (Q5).
- `src/recruitment_intelligence/agents/`: Provider-agnostic LLM interface (`MockProvider` default for offline replay, optional `GeminiProvider`), advisory candidate action queue generation restricted to `{review, advance, escalate, request feedback, close current process}` with mandatory `requires_human_review=True`.
- `src/recruitment_intelligence/outputs/`: Rendering executive daily briefing, findings memo, and strictly isolated external cost research appendix.
- `src/recruitment_intelligence/pipeline.py`: Offline end-to-end orchestration runner.

## Code Layout
- `pyproject.toml`: Package configuration, pytest options (`pythonpath = ["src"]`)
- `fixtures/`:
  - `fixtures/clean_snapshot.json`
  - `fixtures/dirty_snapshot.json`
  - `fixtures/sparse_snapshot.json`
- `src/recruitment_intelligence/`:
  - `domain/`: `models.py`, `contracts.py`, `__init__.py`
  - `airtable/`: `client.py`, `ingest.py`, `__init__.py`
  - `analytics/`: `metrics.py`, `engine.py`, `__init__.py`
  - `quality/`: `auditor.py`, `sensitivity.py`, `__init__.py`
  - `agents/`: `provider.py`, `mock_provider.py`, `gemini_provider.py`, `advisory_queue.py`, `__init__.py`
  - `outputs/`: `briefing.py`, `memo.py`, `cost_appendix.py`, `__init__.py`
  - `pipeline.py`: CLI and offline orchestrator entrypoint
- `tests/`:
  - `test_domain.py`
  - `test_airtable_client.py`
  - `test_airtable_ingest.py`
  - `test_analytics.py`
  - `test_quality.py`
  - `test_agents.py`
  - `test_outputs.py`
  - `test_e2e.py`

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Read-Only API Transport | HTTP client performing only GET requests against Airtable endpoints; zero writes/mutations | M2 | Survey / R1 |
| 2 | Rate Limiting & Throttling | Enforces max 5 req/s limit (`rate_limit_seconds` tracking) | M2 | Survey / R1 |
| 3 | Bounded Exponential Retries | Retries on 429/5xx with backoff `min(2^attempt, 30)` and `Retry-After` parsing | M2 | Survey / R1 |
| 4 | Cursor-Based Pagination | Loops over list responses using `offset` until all records retrieved (up to 100/page) | M2 | Survey / R1 |
| 5 | Snapshot Caching & Replay | Caches raw/normalized data to local JSON file (`data/raw/airtable_snapshot.json`) for offline replay | M2 | Survey / R1 |
| 6 | Linked-Record Normalization | Converts Airtable linked record objects to ID lists while preserving raw objects in `<field>__records` | M2 | Survey / R1 |
| 7 | Schema & Volume Profiler (Q1) | Analyzes all 8 tables to produce exact record counts and field type breakdown | M2 | Survey / R1 / Q1 |
| 8 | Multi-Table Snapshot Runner | Orchestrates fetching or loading all 8 tables into unified snapshot dict | M2 | Survey / R1 |
| 9 | Domain Contract Validation | Strict validation for required fields, ISO-8601 dates, non-negative fractions | M1 | Survey / R1 |
| 10 | Immutable Dataclass Serialization | Slotted frozen dataclasses with `.to_dict()` and `.to_json()` methods | M1 | Survey / R1 |
| 11 | Table Row Counts (Q1) | Returns deterministic count of records for each table in snapshot | M3 | Survey / R2 / Q1 |
| 12 | Recruiting Source Effectiveness (Q2) | Aggregates volume, interviews, offers, hires by source; computes conversion and role mix | M3 | Survey / R2 / Q2 |
| 13 | Source Ranking vs Pipeline Effort (Q2) | Ranks sources by ultimate hire conversion vs pipeline effort consumed; identifies sinks | M3 | Survey / R2 / Q2 |
| 14 | Offer Acceptance Rate (Q3) | Computes accepted offers / total formal offers with explicit denominator justification | M3 | Survey / R2 / Q3 |
| 15 | Funnel Stage-to-Stage Conversion (Q4) | Computes transition pass-through conversion percentages between sequential stages | M3 | Survey / R2 / Q4 |
| 16 | Application Aging & Bottleneck Diagnosis (Q4) | Calculates elapsed days, identifies bottleneck stage with highest attrition/duration | M3 | Survey / R2 / Q4 |
| 17 | Stalled Applications Detection (Q4) | Identifies active, non-terminal applications with no update for >=14 days | M3 | Survey / R2 / Q4 |
| 18 | Structured Evidence Attachment | Enforces every calculated metric attaches structured `MetricClaim` with `EvidenceReference` | M3 | Survey / R2 |
| 19 | Insufficient Evidence Fallback | Standardized fallback returning `Unknown — insufficient evidence` when backing data is absent | M3 | Survey / R2 |
| 20 | Foreign Key & Link Integrity Audit (Q5) | Verifies linked record foreign keys point to valid entity IDs across all 8 tables | M4 | Survey / R3 / Q5 |
| 21 | Orphaned Record Detection (Q5) | Identifies child records whose parent entity is missing or unreferenced | M4 | Survey / R3 / Q5 |
| 22 | Timestamp Contradiction Audit (Q5) | Flags chronological impossibilities (`applied > closed`, `interview completed before scheduled`) | M4 | Survey / R3 / Q5 |
| 23 | Unmapped Enum Value Detection (Q5) | Audits status, stage, and channel fields against canonical vocabularies | M4 | Survey / R3 / Q5 |
| 24 | Metric Sensitivity Quantification (Q5) | Quantifies delta in source rankings and conversion rates under counterfactual anomaly exclusions | M4 | Survey / R3 / Q5 |
| 25 | Advisory Candidate Action Queue | Recommends candidate actions restricted to `{review, advance, escalate, request feedback, close}` | M5 | Survey / R4 |
| 26 | Mandatory Human Review Enforcement | Enforces `requires_human_review=True` on all candidate recommendations | M5 | Survey / R4 |
| 27 | Provider-Agnostic LLM Interface | Abstraction layer decoupling business logic from concrete LLM APIs (`AgentRequest` -> `AgentResult`) | M5 | Survey / R4 |
| 28 | Default Offline Mock Provider | Deterministic, template-based mock LLM provider running 100% offline | M5 | Survey / R4 |
| 29 | Daily Executive Briefing Generator | Synthesizes validated metrics into executive takeaways, urgent items, caveats | M5 | Survey / R4 |
| 30 | Isolated External Cost Research Appendix | Separate section with external cost benchmarks without altering Airtable baseline metrics | M5 | Survey / R4 |
| 31 | Credential & Secret Redaction | Ensures API keys/tokens are never logged, printed, leaked in errors, or committed | M1-M6 | Survey / Security |
| 32 | End-to-End Test Suite Pass (Tiers 1-4) | Comprehensive opaque-box test suite verifying all 5 questions and offline replay | M6 | Survey / Verification |
| 33 | Adversarial Coverage Hardening (Tier 5) | White-box stress-testing, corrupt snapshots, and boundary validation | M6 | Survey / Verification |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Domain Validation & Test Baseline | Test baseline ergonomics (`pyproject.toml` pythonpath) & comprehensive domain contract validation tests (`test_domain.py`) | none | DONE |
| M2 | Read-Only Ingestion & Schema Profiling (Q1) | 8-table snapshot runner, offline fixtures (`clean_snapshot.json`, `dirty_snapshot.json`, `sparse_snapshot.json`), programmatic schema profiler (Q1) | M1 | DONE |
| M3 | Deterministic Analytics Engine (Q2, Q3, Q4) | Pure Python analytics engine returning `MetricClaim` + `EvidenceReference`, source ranking vs effort (Q2), offer acceptance with denominator justification (Q3), funnel stage conversion, aging, bottlenecks, stalled detection (Q4), and insufficient evidence fallbacks | M1, M2 | DONE |
| M4 | Data Quality Audit & Sensitivity Analysis (Q5) | FK integrity, orphan detection, timestamp paradoxes, unmapped enums, and counterfactual sensitivity quantification (Q5) | M1, M2, M3 | DONE |
| M5 | Provider-Agnostic Agents, Advisory Action Queue & Executive Briefing | Provider interface, offline MockProvider, optional Gemini adapter, candidate advisory action queue with strictly restricted vocabulary & human review, executive daily briefing, external cost appendix | M1, M3, M4 | DONE |
| M6 | E2E Test Suite Pass & Adversarial Coverage Hardening | Full offline pipeline execution, 100% pass across Tiers 1-4, followed by Tier 5 adversarial stress testing | M1-M5 | DONE |

## Interface Contracts
### `domain` ↔ `airtable` / `analytics` / `quality` / `agents` / `outputs`
- `Serializable`: Base mixin providing `to_dict()` and `to_json()`.
- `AirtableRecord`: `record_id: str, fields: Mapping[str, Any], created_time: str | None, attributes: Mapping[str, Any]`
- Entities: `Department`, `Person`, `JobOpening`, `Candidate`, `Application`, `Interview`, `Offer`.
- Operational contracts:
  - `EvidenceReference(source: str, table: str, record_ids: tuple[str, ...], query: str | None, caveats: tuple[str, ...])`
  - `MetricClaim(metric: str, value: Any, confidence: Confidence, numerator: float | None, denominator: float | None, unit: str | None, evidence: tuple[EvidenceReference, ...], caveats: tuple[str, ...])`
  - `Finding(finding_id: str, category: str, title: str, description: str, severity: Severity, confidence: Confidence, evidence: tuple[EvidenceReference, ...], affected_records: tuple[str, ...], recommendations: tuple[str, ...])`
  - `CandidateRecommendation(candidate_id: str, application_id: str, action: RecommendationAction, rationale: str, confidence: Confidence, evidence: tuple[EvidenceReference, ...], requires_human_review: bool = True)`
  - `Briefing(briefing_id: str, generated_at: str, period_start: str, period_end: str, executive_summary: str, metrics: tuple[MetricClaim, ...], findings: tuple[Finding, ...], candidate_actions: tuple[CandidateRecommendation, ...], quality_warnings: tuple[Finding, ...], cost_appendix: str | None)`
  - `AgentRequest(prompt: str, context: Mapping[str, Any], provider: str = "mock")`
  - `AgentResult(status: AgentStatus, message: str, claims: tuple[MetricClaim, ...], recommendations: tuple[CandidateRecommendation, ...])`
