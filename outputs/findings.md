# Recruitment findings

Each item separates observed facts from interpretation and advisory action.

## Compensation Band Violations and Offer Aging (`find-compensation-competitiveness`)

- **Observed fact:** Identified 5 offer(s) violating salary bands and 5 stale pending offer(s) exceeding decision windows. Primary decline reasons: Role Scope (60%), Compensation (20%), Counter Offer (20%).
- **Interpretation:** Salary band overruns pose budget risks; unclosed pending offers inflate apparent pipeline.
- **Recommendation:** Audit out-of-band compensation packages and close stale pending offers as lost.
- **Confidence:** high  
- **Severity:** high
- **Caveat:** None recorded
- **Evidence:** analytics.engine; method: deterministic_python

## Formal Offer Acceptance Rate (`find-offer-acceptance`)

- **Observed fact:** Accepted 26 of 36 formal offers (72.2%).
- **Interpretation:** Measures closing effectiveness. Denominator excludes draft/rescinded offers.
- **Recommendation:** Review unaccepted offers for competitive compensation and candidate objections.
- **Confidence:** high  
- **Severity:** low
- **Caveat:** None recorded
- **Evidence:** analytics.engine; method: deterministic_python

## Time-to-Hire and Funnel Velocity by Source (`find-time-to-hire-velocity`)

- **Observed fact:** Average time-to-hire by source: Agency: 44d, Career Site: 52d, Job Board: 46d, LinkedIn: 49d, Referral: 47d.
- **Interpretation:** Cycle time differences highlight pipeline friction across acquisition channels.
- **Recommendation:** Prioritize recruiting sources with faster cycle times to decrease candidate drop-off.
- **Confidence:** medium  
- **Severity:** low
- **Caveat:** None recorded
- **Evidence:** analytics.engine; method: deterministic_python

## Top Recruiting Source: Referral (`find-top-source`)

- **Observed fact:** Referral produced 7 hire(s) from 17 application(s) (41.2% conversion).
- **Interpretation:** Observed funnel performance. Does not account for external agency placement fees.
- **Recommendation:** Maintain pipeline volume in Referral while evaluating candidate quality.
- **Confidence:** medium  
- **Severity:** low
- **Caveat:** None recorded
- **Evidence:** analytics.engine; method: deterministic_python

## Departmental Headcount Budget & Fill Rate (`find-departmental-headcount-fill-rate`)

- **Observed fact:** Department headcount targets: 8 departments tracked; low-fill departments: DAT (0%), ENG (20%), MKT (0%), POP (33%).
- **Interpretation:** Progress against approved requisition headcount targets across business units.
- **Recommendation:** Align requisition priorities with hiring manager availability in critical under-staffed departments.
- **Confidence:** high  
- **Severity:** medium
- **Caveat:** None recorded
- **Evidence:** analytics.engine; method: deterministic_python

## Funnel Bottleneck: interview_to_offer (`find-funnel-bottleneck`)

- **Observed fact:** Highest stage-to-stage attrition occurs at the 'interview_to_offer' transition.
- **Interpretation:** Stage with greatest drop-off rate between sequential recruitment milestones.
- **Recommendation:** Investigate evaluation criteria and candidate drop-off reasons in interview_to_offer.
- **Confidence:** high  
- **Severity:** medium
- **Caveat:** None recorded
- **Evidence:** analytics.engine; method: deterministic_python

## Recruiter and Interviewer Bandwidth Concentration (`find-recruiter-bandwidth`)

- **Observed fact:** Recruiter load led by Ankit Menon (129 apps). Top 2 interviewers absorbed 43.8% of interview bandwidth. Strictest evaluator identified: Rakesh Dubey.
- **Interpretation:** Workload concentration creates single-point-of-failure risks and scheduling delays.
- **Recommendation:** Rebalance screening load across recruiters and add backup interviewers for overloaded engineers.
- **Confidence:** high  
- **Severity:** medium
- **Caveat:** None recorded
- **Evidence:** analytics.engine; method: deterministic_python

## Data-quality warnings

_No data-quality warnings were reported._
