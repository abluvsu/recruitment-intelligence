# SUBJECT: Recruitment Intelligence Assessment Submission — Ashutosh Bhandekar

**To:** hiring-team@company.com / assessment-evaluators
**From:** Ashutosh Bhandekar (ashutosh.bhandekar.pro@gmail.com)
**Repository:** https://github.com/abluvsu/recruitment-intelligence
**Submission Archive:** recruitment_intelligence_submission.zip (1.54 MB)

---

Hi Team,

Please find below my complete submission for the **Recruitment Intelligence** technical assessment.

The solution is architected as an offline-first, deterministic operating system that ingests read-only Airtable data and produces actionable founder insights with **511 / 511 tests passing** in under 27 seconds.

Below you will find:
1. **Repository & Replay Verification** (Part 1)
2. **Findings Table (Q1–Q5 & Strategic Insights)** (Part 2)
3. **The One-Page Executive Memo & Monday Operating Schedule** (Part 3)
4. **Session Transcript Verification** (Part 4)
5. **Interactive Executive Dashboard Highlight** (Top 1% Deliverable)

---

## 1. Submission Deliverables Summary

* **GitHub Repository:** https://github.com/abluvsu/recruitment-intelligence
* **Standalone Zip Archive:** Attached as 
ecruitment_intelligence_submission.zip (1.54 MB; fully self-contained with cached offline snapshot)
* **Findings Table:** Attached as outputs/findings_table.csv and outputs/findings_table.md
* **Executive Memo:** Attached as outputs/memo.md and outputs/briefing.html
* **Session Transcript:** Attached as outputs/session_transcript.jsonl (1.05 MB)
* **Interactive Executive Dashboard:** Attached as outputs/dashboard.html

### Rapid Replay Instructions (Offline-First)
`ash
git clone https://github.com/abluvsu/recruitment-intelligence.git
cd recruitment-intelligence

# Run full test suite (511 passing tests)
python -m pytest -q

# Replay deterministic pipeline from cached snapshot
python -m recruitment_intelligence.pipeline data/raw/airtable_snapshot.json --as-of 2025-02-01 --output-dir outputs/replay
`

---

## 2. Findings Table (Questions 1 to 5)

| Question | Metric | Value | Method | Confidence |
|---|---|---|---|:---:|
| **Q1 — Scope the base** | Table Record Counts & Schema Definition | **892 total records across 8 tables**<br>• Applications: 350<br>• Candidates: 300<br>• Interviews: 160<br>• Offers: 36<br>• Job Openings: 24<br>• People: 14<br>• Departments: 8<br>• Findings: 0 | Deterministic schema profiling, primary key validation, and record count aggregation across all tables | **High** |
| **Q2 — Where should we recruit from?** | Top Source vs. Effort Sinks | **Top Channel: Referral** (41.2% conversion, 7 hires/17 apps, 2.0 interviews/hire, 100% offer acceptance, 47d cycle).<br>**Effort Sinks: Job Board** (4.2% conversion, 9.9 ivs/hire, 142 rejections) and **LinkedIn** (2.6% conversion, 16.0 ivs/hire, 1 hire/38 apps) which together absorbed **71.9% of all interview loops (115/160)** for only 11 hires | Candidate source inheritance mapping, stage-by-stage conversion tracking, and interview-to-hire effort touch ratio calculation | **High** |
| **Q3 — What is our offer acceptance rate?** | Formal Offer Acceptance Rate | **Headline Acceptance Rate: 72.2%** (26 accepted / 36 formal extended).<br>**Resolved Acceptance Rate: 83.9%** (26 accepted / 31 resolved: 5 declined for Role Scope [3], Comp [1], Counter Offer [1]).<br>Sensitivity analysis: All 5 pending offers are stale zombie offers aged **47 to 283 days**; when realistically treated as lost, operational yield remains **72.2%** | Accepted formal offers divided by total formal extended offers (excluding draft/rescinded); timestamp staleness and sensitivity analysis on pending offers | **High** |
| **Q4 — Where is the funnel breaking?** | Funnel Bottleneck & Stagnant Pipeline | **Primary Bottleneck: Interview → Offer** with **25.2% pass-through / 74.8% attrition** (107 candidates eliminated: 70 in Round 1, 14 in Final, 23 No Shows).<br>**Pipeline Dormancy: 105 active applications (30.0% of base)** stagnant up to 447 days (45 Applied, 32 Screening, 23 Interview, 5 Offer) | Stage-to-stage transition conversion computation, activity date staleness audit, and rejection/decline reason breakdown | **High** |
| **Q5 — What in this data would you not trust?** | Data Quality Anomaly Count & Metric Sensitivity | **Critical Data Quality Risks:**<br>1. **Source Attribution:** 100% applications lack Source column; fully inherited from Candidates.<br>2. **Duplicate Candidates:** 6 duplicate candidate pairs (12 records: CAND-00001..12) sharing identical phones/names.<br>3. **+300 Shift:** 50 re-applications (APP-00301..350); 4 candidates applied twice to same opening.<br>4. **Salary Band Breaches:** 5 of 36 offers (13.9%) violate bands (+92.5% over max for Jr Content Marketer, +51.2% for Jr PM).<br>5. **Read-Only Guarantee:** Findings table has 0 records; all outputs written locally | Referential integrity validation, phone/name duplicate clustering, timestamp chronology audit, requisition salary band boundary checks, and counterfactual sensitivity modeling | **High** |
| **Bonus — Strategic Insights** | Recruiter Load, Interviewer Concentration & Headcount Fill | • Recruiter load imbalanced (Ankit Menon handles 129 apps vs Chetan 36).<br>• Top 2 interviewers absorb 43.8% of interview loops; Rakesh Dubey is strictest evaluator (2.1/5.0 avg score).<br>• Critical starvation in technical teams: Data (0% fill), Engineering (20% fill), Marketing (0% fill) | Workload distribution profiling, interviewer score analysis, and departmental requisition target vs hire tracking | **High** |

---

## 3. The One-Page Executive Memo

### Context & Diagnosis
Our pipeline suffers not from an inbound top-of-funnel shortage, but from **severe mid-funnel evaluation friction** and **channel resource misallocation**:
1. **We are subsidizing low-yield channels:** Job Board and LinkedIn accounted for **79.4% of total applicants** (278/350) and **71.9% of interview loops** (115/160), yet yielded only **11 of our 26 hires**.
2. **Our highest ROI source is under-leveraged:** Employee Referrals deliver a **41.2% hire rate** at only **2.0 interviews per hire** with **100% offer acceptance**.
3. **The pipeline is clogged with ghost applications:** 105 applications (30% of total active pipeline) have had zero recorded activity for >30 days (some up to 447 days).
4. **Offer Governance is leaking capital:** 5 offers breach requisition salary ceilings (notably Junior Content Marketer at +92.5% over band max), and 5 pending offers have sat untouched for up to 283 days without formal disposition.

### Monday Morning Founder Operating Schedule
* **09:00 – 10:00 | Zombie Offer Sprint:** Contact Ravi Reddy (APP-00012, 283d pending) and Kavya Mehta (APP-00348, 258d pending) with an explicit 24-hour decision deadline. Consolidate Mohit Patel duplicate records (APP-00033 & APP-00333).
* **10:00 – 11:30 | Executive Compensation Review:** Audit the 5 out-of-band offers with People/Finance; require C-level approval for Neha Agarwal (APP-00028,  vs  band max).
* **11:30 – 12:30 | Sourcing Channel Re-allocation:** Throttle uncalibrated Job Board and LinkedIn sourcing filters. Launch a formal Employee Referral Bounty program (,000–,000).
* **14:00 – 15:30 | Interviewer Bandwidth Relief:** Add 3 shadow/backup interviewers to alleviate concentration on Rakesh Dubey and Priya Sharma (who currently conduct 43.8% of all interviews).
* **15:30 – 16:30 | Pipeline Hygiene Sweep:** Run batch archiving workflows on the 105 dormant applications with respectful closing correspondence.

---

## 4. Session Transcript
The complete execution log is exported at outputs/session_transcript.jsonl (1.05 MB). It documents the full forensic discovery, deterministic script execution, schema validation, and test suite execution.

---

## 5. Top 1% Deliverable: Interactive Executive Dashboard
In addition to the static deliverables, I have built an interactive, standalone HTML executive dashboard located at outputs/dashboard.html. It can be opened in any web browser without server dependencies, featuring:
* Real-time KPI summary tiles
* Dynamic funnel visualization with stage-by-stage drop-off analytics
* Talent channel efficiency & interview bandwidth matrix
* Immediate candidate intervention ledger
* Department headcount fill rate tracker
* Isolated external market benchmark appendix

Please let me know if you would like me to unpack any specific metric or pipeline component. Looking forward to discussing the results!

Best regards,

**Ashutosh Bhandekar**
Full-Stack Engineer & AI Systems Architect
ashutosh.bhandekar.pro@gmail.com
GitHub: https://github.com/abluvsu
