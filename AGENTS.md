# Recruitment Intelligence contributor guide

This repository converts read-only Airtable recruitment data into deterministic,
evidence-backed founder decisions. Keep the core pipeline provider-agnostic and
reproducible offline.

## Boundaries

- `src/recruitment_intelligence/domain/` contains shared contracts. Changes here
  require checking all consumers and adding/adjusting contract tests.
- `airtable/` is read-only ingestion and snapshotting.
- `analytics/` is deterministic Python; it must not call an LLM or invent values.
- `quality/` reports data problems and their metric impact.
- `agents/` may interpret validated outputs only; recommendations are advisory.
- `outputs/` renders findings and briefings without adding unsupported claims.

Workers must modify only their assigned paths, use typed inputs/outputs, preserve
unknown fields, and never commit credentials, raw secrets, or unnecessary PII.
Run `python -m compileall src tests` and `python -m pytest -q` before a stable
iteration is committed. Every finding needs evidence and confidence; every
candidate action must require human review.

