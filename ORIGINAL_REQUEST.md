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

## Follow-up — 2026-09-14T20:55:08Z

<USER_REQUEST>
Execute a rigorous, forensic crosscheck of all Recruitment Intelligence answers (Q1–Q5) against the raw Airtable dataset, guaranteeing 150% marks by proving every deterministic calculation with underlying record IDs, detailing data quality sensitivity, and uncovering high-value strategic hiring insights.

Working directory: d:/myoperator
Integrity mode: development

## Requirements

### R1. Deterministic Verification & Crosscheck of Core Questions (Q1–Q5)
- **Q1 (Base Scope & Schema):** Verify exact record counts across all 8 tables (Applications: 350, Candidates: 300, Interviews: 160, Offers: 36, Job Openings: 24, People: 14, Departments: 8, Findings: 0; Total: 892). Document the foreign key schema, linked-record arrays, and primary keys.
- **Q2 (Recruiting Source Effectiveness):** Crosscheck end-to-end conversion from Candidate Source through Applications to Hires. Prove why Referral is #1 (41.2% conversion, 2.0 interviews/hire, 100% offer acceptance) and why Job Board (4.2% conversion, 9.9 interviews/hire) and LinkedIn (2.6% conversion, 16.0 interviews/hire) are massive effort sinks absorbing 71.9% of interview bandwidth.
- **Q3 (Offer Acceptance Rate):** Crosscheck the 72.2% headline acceptance rate (26 accepted / 36 formal extended offers) vs 83.9% resolved rate (26/31). Prove that the 5 pending offers are stale ghost offers (47 to 283 days old) that must be treated as lost. Detail decline reasons (Role Scope 60%, Comp 20%, Counter Offer 20%).
- **Q4 (Funnel Breakdown & Stalled Applications):** Pinpoint the primary conversion bottleneck at `Interview -> Offer` (25.2% pass-through, 74.8% drop-off; 70 rejected after Round 1, 14 after Final, 23 No Shows). Surface the 105 stagnant "Active" applications, detail the top 5 urgent applications requiring immediate action (including Mohit Patel's duplicate pending offers and Ravi Reddy's 283-day-old offer), and provide an actionable Monday morning operating schedule.
- **Q5 (Data Trust & Forensic Audit):** Document all critical flaws: (1) missing source column on Applications requiring candidate inheritance, (2) 6 duplicate candidate pairs (`CAND-00001..12`) with identical phones/names and shifted emails, (3) +300 application index shift (`APP-00301..350`) where 50 candidates re-applied and 4 applied twice to identical openings, (4) 5 salary band violations (e.g. Junior PM offered 51% over band max; Junior Content Marketer 92.5% over max; Enterprise AEs below band min), (5) empty Findings table (0 records). Quantify how cleaning these anomalies alters source ranking and acceptance metrics.

### R2. Deep Strategic & Operational Insights (Bonus 150% Value)
- **Recruiter & Interviewer Bandwidth Distribution:** Analyze hiring velocity and load across internal team members in `People`.
- **Compensation & Salary Band Competitiveness:** Contrast offered CTC vs candidate expectations, identifying roles with high counter-offer or comp drop-off risk.
- **Time-to-Hire & Funnel Velocity by Source:** Benchmark the duration from `Applied On` to `Offered On` and `Closed On` across sources.
- **Departmental Budget & Headcount Fill Rate:** Compare headcount targets across Departments (CS, ENG, FIN, etc.) against actual offers and hires.

### R3. Output Verification & Multi-Format Synthesis
- Generate verified outputs in `outputs/` covering Markdown (`briefing.md`, `memo.md`, `findings.md`), CSV (`findings.csv`), HTML (`briefing.html`), and JSON (`briefing.json`, `candidate_actions.json`).
- Ensure every metric contains structured evidence with source tables, filters, record counts, and confidence levels.
- Enforce strict advisory terminology on all candidate actions (`review`, `advance`, `escalate`, `request feedback`, `close current process`) with `requires_human_review=True` and zero automated rejections.

## Acceptance Criteria

### Verification & Test Suite
- [ ] `python -m compileall src tests` succeeds cleanly with 0 errors.
- [ ] `python -m pytest -q` passes all 483+ tests covering domain, ingestion, analytics, quality, and output suites.
- [ ] System executes 100% offline from cached snapshots with zero external network dependencies.

### Forensic Accuracy & Guardrails
- [ ] Record counts match exactly: Applications=350, Candidates=300, Interviews=160, Offers=36, Job Openings=24, People=14, Departments=8, Findings=0.
- [ ] All metrics include complete evidence blocks (numerator, denominator, source table, record count, caveats, confidence).
- [ ] Candidate action suggestions contain only advisory vocabulary with mandatory human review.
- [ ] Zero API keys, credentials, or secrets in version control or output logs.
</USER_REQUEST>

