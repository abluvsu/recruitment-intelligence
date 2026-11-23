# Recruitment intelligence memo

## Executive summary

7 validated finding(s) are available. Candidate actions remain advisory and require human review.

## Findings

### Compensation Band Violations and Offer Aging
**Observed fact:** Identified 5 offer(s) violating salary bands and 5 stale pending offer(s) exceeding decision windows. Primary decline reasons: Role Scope (60%), Compensation (20%), Counter Offer (20%).
**Interpretation:** Salary band overruns pose budget risks; unclosed pending offers inflate apparent pipeline.
**Recommendation:** Audit out-of-band compensation packages and close stale pending offers as lost.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Formal Offer Acceptance Rate
**Observed fact:** Accepted 26 of 36 formal offers (72.2%).
**Interpretation:** Measures closing effectiveness. Denominator excludes draft/rescinded offers.
**Recommendation:** Review unaccepted offers for competitive compensation and candidate objections.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Time-to-Hire and Funnel Velocity by Source
**Observed fact:** Average time-to-hire by source: Agency: 44d, Career Site: 52d, Job Board: 46d, LinkedIn: 49d, Referral: 47d.
**Interpretation:** Cycle time differences highlight pipeline friction across acquisition channels.
**Recommendation:** Prioritize recruiting sources with faster cycle times to decrease candidate drop-off.
**Confidence:** medium
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Top Recruiting Source: Referral
**Observed fact:** Referral produced 7 hire(s) from 17 application(s) (41.2% conversion).
**Interpretation:** Observed funnel performance. Does not account for external agency placement fees.
**Recommendation:** Maintain pipeline volume in Referral while evaluating candidate quality.
**Confidence:** medium
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Departmental Headcount Budget & Fill Rate
**Observed fact:** Department headcount targets: 8 departments tracked; low-fill departments: DAT (0%), ENG (20%), MKT (0%), POP (33%).
**Interpretation:** Progress against approved requisition headcount targets across business units.
**Recommendation:** Align requisition priorities with hiring manager availability in critical under-staffed departments.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Funnel Bottleneck: interview_to_offer
**Observed fact:** Highest stage-to-stage attrition occurs at the 'interview_to_offer' transition.
**Interpretation:** Stage with greatest drop-off rate between sequential recruitment milestones.
**Recommendation:** Investigate evaluation criteria and candidate drop-off reasons in interview_to_offer.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

### Recruiter and Interviewer Bandwidth Concentration
**Observed fact:** Recruiter load led by Ankit Menon (129 apps). Top 2 interviewers absorbed 43.8% of interview bandwidth. Strictest evaluator identified: Rakesh Dubey.
**Interpretation:** Workload concentration creates single-point-of-failure risks and scheduling delays.
**Recommendation:** Rebalance screening load across recruiters and add backup interviewers for overloaded engineers.
**Confidence:** high
**Caveat:** None recorded
**Evidence:** analytics.engine; method: deterministic_python

## Data trust

- No data-quality warnings were reported.

## Next action

Review each recommendation with the hiring owner; no candidate should be rejected automatically.

## External cost research appendix (strictly isolated)

### External Recruitment Cost Research (Strictly Isolated)

> **Note:** The benchmarks below are compiled from external industry surveys (SHRM, LinkedIn Talent Solutions) and are provided solely as context for founder planning. They are NOT derived from Airtable data and do NOT modify any baseline funnel or conversion metrics.

| Category / Channel | Industry Benchmark Range | Operational Context |
|---|---|---|
| Software Engineering | $4,500 - $6,000 (SHRM Benchmark) | Blended cost including sourcing, time-to-hire, and tooling |
| Sales & Go-to-Market | $3,800 - $5,200 | High volume screening with lower assessment overhead |
| Leadership / Executive | $14,000 - $22,000 | Retained search partner fee structure |
| External Recruiting Agency | 20% - 25% of first-year base salary | Contingent search fee on placed candidates |
| Job Boards & Aggregators | $300 - $600 per recruiter seat | Fixed monthly subscription cost |
| Employee Referral Bonus | $2,000 - $5,000 for technical roles | Cash bonus paid after 90 days retention |

**Founder takeaway:** Prioritize employee referrals and high-conversion inbound channels to minimize agency fee exposure while monitoring pipeline effort yield.
