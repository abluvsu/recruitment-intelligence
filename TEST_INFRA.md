# E2E Test Infra: Recruitment Intelligence Founder OS

## Test Philosophy
- Opaque-box, requirement-driven. No dependency on implementation design.
- Strictly offline execution using reproducible synthetic fixtures (`clean_snapshot.json`, `dirty_snapshot.json`, `sparse_snapshot.json`).
- Methodology: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinations + Real-World Workload Testing.

## Feature Inventory & Test Mapping
| # | Feature | Requirement Source | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|-------------------|:------:|:------:|:------:|:------:|
| 1 | Read-Only API Transport & Caching | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | Rate Limiting & Bounded Retries | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 3 | Schema & Volume Profiling (Q1) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 4 | Source Effectiveness & Ranking (Q2)| ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 5 | Offer Acceptance Rate (Q3) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 6 | Funnel Transitions & Aging (Q4) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 7 | Stalled Applications Detection (Q4)| ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 8 | Structured Evidence Attachment | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 9 | Data Quality Integrity Audit (Q5) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 10 | Metric Sensitivity Quantification(Q5)| ORIGINAL_REQUEST §R3| 5 | 5 | ✓ | ✓ |
| 11 | Advisory Candidate Queue (R4) | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 12 | Executive Daily Briefing (R4) | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 13 | Mock Provider & Offline Replay | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 14 | External Cost Appendix | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Test runner: `pytest`
- Invocation: `python -m pytest -q`
- Pass/fail semantics: Exit code 0, 100% passing tests
- Test directory: `tests/`
  - `tests/test_domain.py`: Unit tests for domain contracts, post-init validation, serialization
  - `tests/test_airtable_client.py`: Ingestion client, pagination, retry, rate limit, secret masking
  - `tests/test_airtable_ingest.py`: Snapshot fetcher, multi-table schema profiler (Q1), offline caching
  - `tests/test_analytics.py`: Deterministic metrics (Q2, Q3, Q4), evidence blocks, denominator justification
  - `tests/test_quality.py`: Referential integrity, orphan detection, timestamp checks, sensitivity (Q5)
  - `tests/test_agents.py`: Mock provider, advisory action restrictions, human review enforcement
  - `tests/test_outputs.py`: Executive briefing markdown renderer, cost appendix isolation
  - `tests/test_e2e.py`: End-to-end integration tests across Tiers 1-4

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | High-Growth Seed Startup Surge | Ingestion, Source Ranking (Q2), Offer Acceptance (Q3), Funnel Bottleneck (Q4) | High |
| 2 | Messy ATS Migration Audit | Ingestion, Data Quality Audit (Q5), Orphan Detection, Sensitivity Impact | High |
| 3 | Monday Morning Founder Standup | Daily Executive Briefing (R4), Advisory Candidate Queue, External Cost Appendix | High |
| 4 | Corrupted / Sparse Pipeline Run | Zero-division handling, "Unknown — insufficient evidence", Empty tables | Medium |

## Coverage Thresholds
- Tier 1: ≥5 per feature (Happy-path & isolated feature verification)
- Tier 2: ≥5 per feature (Boundaries, empty inputs, malformed dates, invalid values)
- Tier 3: Pairwise combinations of pipeline components
- Tier 4: ≥4 realistic application scenarios
- Tier 5: Adversarial stress testing (zero leaks, corrupted JSON, boundary stress)
