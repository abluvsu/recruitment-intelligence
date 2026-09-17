# Subject: Recruitment Intelligence Submission — Ashutosh Bhandekar

Hi Ankit,

Here is my submission for the recruitment intelligence assessment.

I built the pipeline in deterministic Python so it runs offline directly against the Airtable snapshot. There are zero external API calls and zero LLM dependencies in the analytics core. The test suite has 511 passing tests and runs in about 25 seconds.

If you want to view everything online without downloading files:
• Memo & Monday Plan: https://github.com/abluvsu/recruitment-intelligence/blob/master/outputs/memo.md
• Findings Table: https://github.com/abluvsu/recruitment-intelligence/blob/master/outputs/findings_table.md
• GitHub Repo: https://github.com/abluvsu/recruitment-intelligence
• Interactive Dashboard: Open the attached `dashboard.html` in your browser

Here is the breakdown of the 5 questions, the findings table, and what I would tackle on Monday morning.

---

### The 5 Questions (Indian Startup Context)

#### Q1: Scope the Base
The base contains **892 total records** across 8 tables:
- Applications: 350
- Candidates: 300
- Interviews: 160
- Offers: 36
- Job Openings: 24
- People: 14
- Departments: 8
- Findings: 0 (read-only destination)

#### Q2: Where Should We Recruit From?
- **Best Channel: Referrals.** 17 applications gave 7 hires (41.2% conversion). It took only 2.0 interviews per hire, and 100% of candidates who received an offer accepted.
- **Effort Sinks: Job Boards & LinkedIn.** Job boards produced 10 hires from 240 applications (4.2% conversion, 9.9 interviews/hire). LinkedIn produced 1 hire from 38 applications (2.6% conversion, 16.0 interviews/hire).
- Together, Job Boards and LinkedIn burned **71.9% of your team's interview hours** (115 of 160 rounds) to produce just 11 hires.

#### Q3: Offer Acceptance Rate
- **Headline Rate: 72.2%** (26 accepted out of 36 formal extended offers).
- If you only count resolved offers (26 accepted, 5 declined), the rate shows 83.9%.
- But 5 offers are still marked "Pending". In the Indian tech ecosystem where candidates juggle counter-offers during 60–90 day notice periods, an offer sitting for months is not pending—it is dead. These 5 offers have been sitting untouched between 47 and 283 days, locking up ₹82.6 Lakhs in phantom CTC. Treating them as unaccepted keeps the true yield at **72.2%**.

#### Q4: Where is the Funnel Breaking?
- **The primary bottleneck is Interview to Offer.** 74.8% of candidates drop out here (107 people cut: 70 in Round 1, 14 in Final, 23 No-Shows). Only 25.2% make it to an offer.
- **Pipeline backlog:** 105 applications (30% of all applications) are sitting in active stages with zero activity for weeks or months (some up to 447 days).

#### Q5: What in This Data Would You Not Trust?
1. **Broken Source Attribution:** The Applications table has no Source column. All source data is inherited from the Candidates table. If an engineer applied on LinkedIn in 2024 and got referred by a team member this year, the referral gets credited to LinkedIn.
2. **Duplicate Candidates:** 6 pairs of candidate records share identical names and phone numbers with different email IDs.
3. **Re-application Shift:** Applications 301 to 350 are re-applications. 4 candidates applied twice to the exact same opening.
4. **Salary Band Breaches:** 5 of the 36 offers violate approved requisition salary bands. Most notably, a Junior Content Marketer was offered ₹15.4 LPA against an approved band ceiling of ₹8.0 LPA (+92.5%).

---

### Findings Table

| Question | Metric | Value | Method | Confidence |
|---|---|---|---|:---:|
| **Q1 — Scope the Base** | Record Counts & Schema | 892 records across 8 tables (350 apps, 300 candidates, 160 interviews, 36 offers) | Deterministic schema profiling & primary key validation | High |
| **Q2 — Sourcing Efficiency** | Conversion & Interview Burden | Top: Referral (41.2% conv, 2.0 ivs/hire). Sinks: Job Boards (4.2%) & LinkedIn (2.6%) taking 71.9% of interview loops | Source inheritance mapping & interview-to-hire ratio | High |
| **Q3 — Offer Acceptance** | Acceptance Rate | 72.2% headline (26/36). 83.9% resolved (26/31). 5 stale pending offers (₹82.6L CTC) treated as lost | Formal accepted / formal extended offers | High |
| **Q4 — Funnel Bottlenecks** | Stage Drop-off & Stagnation | Bottleneck: Interview to Offer (25.2% pass / 74.8% drop). 105 dormant active applications | Stage transition math & activity staleness audit | High |
| **Q5 — Data Trust Audit** | Anomalies & Integrity Risks | Missing application source; 6 duplicate candidate pairs; 5 salary band breaches; 50 re-applications | Phone/name clustering, band boundary checks | High |
| **Bonus — Workload** | Recruiter & Team Fill | Ankit Menon handles 129 apps. Top 2 interviewers take 43.8% of loops. Data (0%) & Eng (20%) headcount starved | Workload distribution & requisition target tracking | High |

---

### Monday Morning Founder Action Plan

1. **09:00 - 10:00 | Clear the Zombie Offers (Free up ₹82.6L CTC):**
   - Call Ravi Reddy (`APP-00012`, ₹7.9 LPA, 283 days pending) and Kavya Mehta (`APP-00348`, ₹18.6 LPA, 258 days pending). Give them a 24-hour decision deadline or release the budget to hire active candidates.
   - Merge the two conflicting offer records for Mohit Patel (`APP-00033` at ₹12.9 LPA and `APP-00333` at ₹27.8 LPA).
2. **10:00 - 11:30 | Review Out-of-Band Compensation:**
   - Audit Neha Agarwal's offer (`APP-00028`) with Finance. She was offered ₹15.4 LPA against an approved band maximum of ₹8.0 LPA. Verify whether this was an intentional senior leveling exception or a data entry error.
3. **11:30 - 12:30 | Sourcing Re-alignment:**
   - Filter low-intent inbound on Job Boards and LinkedIn to protect engineering time.
   - Launch an internal Employee Referral Bounty (₹25,000 to ₹50,000) to get more pipeline into our 41.2% conversion channel.
4. **14:00 - 15:30 | Interviewer Bandwidth Relief:**
   - Rakesh Dubey and Priya Sharma are handling 43.8% of all technical interviews. Onboard 2–3 shadow interviewers from Engineering to reduce scheduling lag during 60–90 day notice period windows.
5. **15:30 - 16:30 | Pipeline Hygiene Sweep:**
   - Send clean closing emails to the 105 applicants stuck in the pipeline with no updates.

---

### How to Run the Code (Offline Replay)

```bash
git clone https://github.com/abluvsu/recruitment-intelligence.git
cd recruitment-intelligence
python -m pytest -q
python -m recruitment_intelligence.pipeline data/raw/airtable_snapshot.json --as-of 2025-02-01 --output-dir outputs/replay
```

### Attached Files
1. `recruitment_intelligence_submission.zip` (1.55 MB) — Complete runnable codebase & snapshot.
2. `findings_table.csv` — CSV version of the findings table.
3. `memo.md` — One-page executive memo.
4. `session_transcript.jsonl` — Full terminal and session execution log.
5. `dashboard.html` — Interactive visual dashboard. Double-click to open in any web browser.

Happy to walk through the numbers or code anytime.

Best,  
Ashutosh Bhandekar  
ashutosh.bhandekar.pro@gmail.com  
GitHub: https://github.com/abluvsu
