# Recruitment intelligence memo

## Executive summary

7 validated findings are available from deterministic analysis. Candidate actions remain advisory and require human review.

## Findings

### Compensation Band Violations and Stale Offer Aging
**Observed fact:** Identified 5 offers violating approved salary bands and 5 stale pending offers exceeding normal decision and notice period windows. Primary decline reasons: Role Scope (60%), Compensation (20%), Counter Offer (20%).
**Interpretation:** Salary band overruns (up to +92.5% above band cap) risk team parity and cash runway; unclosed pending offers lock up ₹82.6 Lakhs in apparent pipeline CTC.
**Recommendation:** Audit out-of-band packages (notably ₹15.4 LPA against a ₹8.0 LPA cap) and release stale pending offers.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Formal Offer Acceptance Rate
**Observed fact:** Accepted 26 of 36 formal extended offers (72.2%).
**Interpretation:** Measures true closing yield. Excluding the 5 stale pending offers (aged 47 to 283 days) inflates the apparent rate to 83.9% (26/31), but operationally those 5 are lost.
**Recommendation:** Enforce standard 7-day offer decision SLAs before candidates enter prolonged 60–90 day notice period negotiations.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Time-to-Hire and Funnel Velocity by Source
**Observed fact:** Average cycle time by source: Agency: 44d, Referral: 47d, Job Board: 46d, LinkedIn: 49d, Career Site: 52d.
**Interpretation:** Cycle times reflect standard Indian notice period buffers (30–60 days). Differences between channels are within statistical noise due to small sample sizes (LinkedIn N=1, Agency N=4).
**Recommendation:** Avoid drawing channel strategy conclusions purely from cycle days; prioritize conversion rate and interviewer touch ratios.
**Confidence:** medium
**Caveat:** Small sample size for single-hire channels.
**Evidence:** analytics.engine; method: deterministic_python

### Top Recruiting Source: Referral
**Observed fact:** Employee Referrals produced 7 hires from 17 applications (41.2% conversion) requiring only 2.0 interviews per hire.
**Interpretation:** Highest-quality talent channel with 100% offer acceptance.
**Recommendation:** Formalize an internal employee referral bounty (₹25,000 to ₹50,000) to double down on this pipeline.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Departmental Headcount Budget & Fill Rate
**Observed fact:** 8 departments tracked; critical under-staffing in Data & Analytics (0% fill, 0/2), Engineering (20% fill, 1/5), and Marketing (0% fill, 0/2).
**Interpretation:** Hiring velocity is lagging in core product and technical functions, while Sales and Customer Success are 100% staffed (12/12).
**Recommendation:** Shift recruiter bandwidth (Ankit Menon) toward unblocking engineering and data pipelines.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Funnel Bottleneck: Interview to Offer
**Observed fact:** Highest stage-to-stage attrition occurs at the interview-to-offer transition (25.2% pass-through / 74.8% drop).
**Interpretation:** 107 candidates eliminated after entering interview loops (70 in Round 1, 14 in Final, 23 No-Shows).
**Recommendation:** Calibrate initial screening filters so interviewers evaluate pre-vetted candidates rather than screening for basic qualifications.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Recruiter and Interviewer Bandwidth Concentration
**Observed fact:** Sourcing load is concentrated on Ankit Menon (129 applications). Two interviewers (Rakesh Dubey and Priya Sharma) absorbed 43.8% of all interview rounds.
**Interpretation:** Over-reliance on two senior evaluators creates bottlenecks and slows candidate progression during notice periods.
**Recommendation:** Train 2–3 shadow technical interviewers to distribute evaluation rounds.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

## Data trust

- No data-quality warnings were reported.

## Next action

Review each recommendation with the hiring owner; no candidate should be rejected automatically.

## External Indian market recruitment benchmarks (strictly isolated)

> **Note:** The benchmarks below are compiled from Indian startup talent surveys and executive search standards (Bengaluru/Mumbai ecosystem). They are provided for operational context and are strictly isolated from deterministic Airtable pipeline metrics.

| Category / Channel | Indian Market Benchmark | Operational Context |
|---|---|---|
| Engineering Hires (Mid-Senior) | ₹18 LPA – ₹35 LPA CTC | Standard CTC bands in Bengaluru/Mumbai product startups |
| Notice Period Buffer | 60 – 90 days | Standard notice period in Indian tech services/product firms |
| External Staffing Agency | 8.33% – 12.5% of annual CTC | Contingent recruitment fee (approx. 1 to 1.5 months CTC) |
| Employee Referral Bounty | ₹25,000 – ₹50,000 | Cash bonus paid post successful 90-day onboarding |
| Job Boards & Aggregators | ₹30,000 – ₹60,000 / seat / year | High application volume with high recruiter screening overhead |

**Founder takeaway:** Double down on employee referrals to cut agency fee bleed and counter-offer drop-offs during Indian 60–90 day notice periods.
