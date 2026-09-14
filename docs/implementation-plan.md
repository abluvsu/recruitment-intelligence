# Implementation plan

## Definition of done

The clean-environment run installs the package, passes all tests and compile
checks, replays an offline snapshot, and emits reproducible findings, memo, and
briefing. Every claim has an evidence reference, confidence, and caveat where
appropriate; no secrets or unsupported metrics appear in outputs.

## Iterations

0. Audit the repository and resolve cross-module contracts (this document).
1. Freeze typed domain contracts and validation.
2. Implement read-only Airtable pagination, retries, throttling, caching, and
   schema profiling.
3. Normalize Airtable tables and linked records into canonical entities.
4. Add deterministic funnel, source, offer, aging, stalled-application, and
   sensitivity metrics.
5. Add quality checks with affected records and metric impact.
6. Render findings and one-page memo with explicit fact/interpretation/action
   sections.
7. Add provider-agnostic specialist agents and a mock provider.
8. Generate the daily founder briefing and candidate action queue.
9. Add a separately labelled external cost appendix.
10. Re-run from a clean environment and audit evidence, secrets, and PII.

Each iteration follows: specify → assign → implement → test → critique → fix →
regression test → compare → commit. No worker may expand its assigned scope.

