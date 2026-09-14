# Original User Request

## Initial Request — 2026-09-13T16:54:24Z

<USER_REQUEST>
Transform read-only Airtable recruitment data into an evidence-backed founder operating system for hiring, answering five core executive questions deterministically, generating advisory candidate action queues, diagnosing data quality, and producing daily recruitment briefings.

Working directory: d:/myoperator
Integrity mode: development

## Requirements

### R1. Read-Only Snapshot Ingestion & Schema Profiling (Q1)
- Connect to Airtable using `AIRTABLE_API_KEY` (or `AIRTABLE_TOKEN`) and `AIRTABLE_BASE_ID` from the environment.
- Enforce read-only access (zero writes/mutations to Airtable).
- Respect Airtable API constraints (maximum 5 requests/sec, pagination with up to 100 records per list request).
- Cache all ingested data into a local snapshot (e.g. `data/raw/airtable_snapshot.json`) so subsequent runs and tests execute offline without repeated network calls.
- Programmatically profile and output exact record counts and schema definitions for all 8 tables: Departments, People, Job Openings, Candidates, Applications, Interviews, Offers, and Findings.

### R2. Deterministic Analytics Engine (Q2, Q3, Q4)
Pure deterministic Python engine (no LLM in the calculation loop):
- **Recruiting Source Effectiveness (Q2):** Rank sources by ultimate hire conversion vs. pipeline effort consumed. Identify top-performing sources and sources that consume candidate/interview volume without producing hires.
- **Offer Acceptance Rate (Q3):** Compute offer acceptance rate with clear numerator (accepted offers) and explicit explanation/justification of the denominator (total formal offers extended, excluding rescinded/draft if distinct).
- **Hiring Funnel Diagnosis (Q4):** Calculate stage-to-stage pass-through conversion and duration/aging. Pinpoint the broken or bottleneck funnel stage and identify stalled applications requiring immediate review.
- **Strict Evidence Attachment:** Every calculated metric must attach structured evidence: metric name, value, numerator/denominator where applicable, source table, filters/groupings, record count, caveats, and confidence bucket (`high`, `medium`, `low`). If evidence is insufficient, return `Unknown — insufficient evidence`.

### R3. Data Quality & Metric Sensitivity Audit (Q5)
- Automated data quality checks reporting missing foreign keys, orphaned records, conflicting timestamps, and unmapped enum values across the 8 tables.
- Quantify data quality anomalies and explain the sensitivity/impact of these anomalies on source ranking and funnel metrics.

### R4. Advisory Candidate Action Queue & Executive Briefing
- Positioned as a founder hiring operating system.
- Candidate-level action recommendations using professional advisory terms: `review`, `advance`, `escalate`, `request feedback`, or `close current process` (no autonomous rejection language). All candidate actions require human review.
- Executive daily briefing synthesizing validated metrics into clear executive takeaways, prioritized action items, and data quality caveats.
- Optional external cost research kept strictly in a separate labeled appendix without altering Airtable-derived baseline metrics.
- Provider-agnostic LLM interface with a mock provider by default for offline execution, and an optional Gemini provider adapter.

## Acceptance Criteria

### Verification & Test Suite
- [ ] `python -m compileall src tests` succeeds with zero compilation or syntax errors.
- [ ] `python -m pytest -q` passes all test suites covering domain contracts, ingestion rate-limiting/pagination, deterministic analytics, quality checks, and briefing generation.
- [ ] System runs end-to-end completely offline from a local snapshot using the mock provider without network dependencies.

### Objective Question Coverage & Objective Guardrails
- [ ] Deterministic outputs directly answer all 5 core questions (Q1–Q5).
- [ ] Every primary metric includes a complete evidence block (metric, value, numerator/denominator, source table, record count, caveats, confidence).
- [ ] Metrics with missing or corrupted backing data return `Unknown — insufficient evidence`.
- [ ] Candidate action suggestions contain only advisory vocabulary (`review`, `advance`, `escalate`, `request feedback`, `close current process`) with zero automated rejections.
- [ ] No API keys, credentials, or raw secrets are logged, printed, or committed to version control.
</USER_REQUEST>
