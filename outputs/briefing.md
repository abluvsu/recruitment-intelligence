# Daily recruitment briefing — daily

Generated: 2026-09-02T00:00:00+00:00 | Confidence: high

## What changed

- Profiled 892 records across 8 recruitment tables.
- Leading source: 'Referral' ranked top by hire conversion yield.
- Offer acceptance rate stands at 72.2%.
- Primary hiring funnel bottleneck identified at 'interview_to_offer'.

## Urgent items

- 103 active application(s) stalled for >= 14 days requiring prompt founder/hiring manager review.
- Compensation review: Neha Agarwal (Junior Content Marketer) offered 92.5% over salary band. Founder sign-off required.
- Compensation review: Elena Okonkwo (Junior Product Manager) offered 51.2% over salary band. Founder sign-off required.
- Stale offer follow-up: Ravi Reddy has pending offer aged 283 days. Treat as lost and close current process.
- Stale offer follow-up: Kavya Mehta has pending offer aged 246 days. Treat as lost and close current process.
- Stale offer follow-up: Mohit Patel has pending offer aged 240 days. Treat as lost and close current process.
- Stale offer follow-up: Mohit Patel has pending offer aged 97 days. Treat as lost and close current process.

## Findings


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


## Candidate action queue

- `rec1MXRwKBzPq18Yt` — **escalate**: Application has stalled in 'active' stage for 126 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec1hmfaOaXLyFOKD` — **escalate**: Application has stalled in 'active' stage for 77 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec1rUS9I2sq4lMK3` — **escalate**: Application has stalled in 'active' stage for 90 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec237RCQVkYLkBfS` — **escalate**: Application has stalled in 'active' stage for 275 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec2ONYxod19b5MWR` — **escalate**: Application has stalled in 'active' stage for 138 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec2ONYxod19b5MWR` — **escalate**: Application has stalled in 'active' stage for 258 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec2uTauvS9mr7DPc` — **escalate**: Application has stalled in 'active' stage for 92 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec3XDakOUBHrEijf` — **escalate**: Application has stalled in 'active' stage for 184 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec54VD0UV9ZEHw4U` — **escalate**: Application has stalled in 'active' stage for 51 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec6Q4llgClwMeBls` — **escalate**: Application has stalled in 'active' stage for 119 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec72dpIfAnE7qnCI` — **escalate**: Application has stalled in 'active' stage for 393 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec7LQdOjD29mZIdc` — **escalate**: Application has stalled in 'active' stage for 128 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec7LQdOjD29mZIdc` — **escalate**: Application has stalled in 'active' stage for 281 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec9bkxf5lcSGetmr` — **escalate**: Application has stalled in 'active' stage for 103 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recAAtq6dIcja1jsy` — **escalate**: Application has stalled in 'active' stage for 51 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recBzmWUWsUOclWSH` — **escalate**: Application has stalled in 'active' stage for 228 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recCyEWJbGJCuIaLg` — **escalate**: Application has stalled in 'active' stage for 241 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recDNgeKgf93DshUc` — **escalate**: Application has stalled in 'active' stage for 135 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recDs7CtmAKTV1vRs` — **escalate**: Application has stalled in 'active' stage for 74 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recDwVrPzt0mwNFzJ` — **escalate**: Application has stalled in 'active' stage for 433 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recFdYGpVDqAtXU0A` — **escalate**: Application has stalled in 'active' stage for 30 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recFkFascZIALtjEl` — **escalate**: Application has stalled in 'active' stage for 111 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recFkGqYstNwhS0Iy` — **escalate**: Application has stalled in 'active' stage for 77 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recIFRJdGRgkB6nbR` — **escalate**: Application has stalled in 'active' stage for 348 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recItbuThKAeHuOiP` — **escalate**: Application has stalled in 'active' stage for 30 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recJmDaQHQ0VqOjpO` — **escalate**: Application has stalled in 'active' stage for 308 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recKUadMZumnK58a2` — **escalate**: Application has stalled in 'active' stage for 58 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recKW7BwqjUgQ7YvV` — **escalate**: Application has stalled in 'active' stage for 68 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recKW7BwqjUgQ7YvV` — **escalate**: Application has stalled in 'active' stage for 350 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recKit5ecqU6Wmgmy` — **escalate**: Application has stalled in 'active' stage for 134 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recLTECqvLMERq8PX` — **escalate**: Application has stalled in 'active' stage for 196 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recLkeHWkCbyT9XcL` — **escalate**: Application has stalled in 'active' stage for 369 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recLn18g6JoYtO7uC` — **escalate**: Application has stalled in 'active' stage for 51 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recLoow4LXl1usogr` — **escalate**: Application has stalled in 'active' stage for 63 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recM7Ad1ywQXylydt` — **escalate**: Application has stalled in 'active' stage for 332 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recNLkCeSgdACsG06` — **escalate**: Application has stalled in 'active' stage for 154 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recOdgIbzuuPG3yv4` — **escalate**: Application has stalled in 'active' stage for 366 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recR4q1SmeiFqWnZc` — **escalate**: Application has stalled in 'active' stage for 97 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recREs9MqeSQ3DOK4` — **escalate**: Application has stalled in 'active' stage for 438 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recREzdrV50ao6yFW` — **escalate**: Application has stalled in 'active' stage for 66 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recRrEe0LfVZLfqqL` — **escalate**: Application has stalled in 'active' stage for 90 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recSKzUUzzULI0ou9` — **escalate**: Application has stalled in 'active' stage for 84 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recT8iJ7j9ltJflMP` — **escalate**: Application has stalled in 'active' stage for 83 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recVOWq79fEjiyf1Q` — **escalate**: Application has stalled in 'active' stage for 292 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recVTB1g4dVUe3uBO` — **escalate**: Application has stalled in 'active' stage for 66 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recVhynlKLvxOuWDJ` — **escalate**: Application has stalled in 'active' stage for 243 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recW5TQBakWDekr5W` — **escalate**: Application has stalled in 'active' stage for 130 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recWBz108AEJmThBK` — **escalate**: Application has stalled in 'active' stage for 198 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recWLnYnY4LrDePSG` — **escalate**: Application has stalled in 'active' stage for 93 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recWukvHASXrtjxjp` — **escalate**: Application has stalled in 'active' stage for 394 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recX3t49GeOU34d3O` — **escalate**: Application has stalled in 'active' stage for 286 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recXfiScAT3LVt6UV` — **escalate**: Application has stalled in 'active' stage for 129 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recY8XDekrU1Y32yP` — **escalate**: Application has stalled in 'active' stage for 115 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recYcPG1H6xhxjnd2` — **escalate**: Application has stalled in 'active' stage for 417 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recZIYJSmpBESo5jN` — **escalate**: Application has stalled in 'active' stage for 65 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recZol1q6YlB5MTev` — **escalate**: Application has stalled in 'active' stage for 117 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recakUmq8lUxJZOVg` — **escalate**: Application has stalled in 'active' stage for 50 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recbrRiiFOdBQf0ia` — **escalate**: Application has stalled in 'active' stage for 117 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `reccCtIoC5b0ym9FR` — **escalate**: Application has stalled in 'active' stage for 95 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `reccG7l7T1jxMc09b` — **escalate**: Application has stalled in 'active' stage for 117 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recdSDRKuipEb9P5p` — **escalate**: Application has stalled in 'active' stage for 99 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recdrrZsX6yBujWhx` — **escalate**: Application has stalled in 'active' stage for 32 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recez11FrlEk40JGJ` — **escalate**: Application has stalled in 'active' stage for 96 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recf767ZGvqcOzqlh` — **escalate**: Application has stalled in 'active' stage for 78 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recfQ6uLOZzpD7LRi` — **escalate**: Application has stalled in 'active' stage for 122 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recgeHIWdCdNU9w8z` — **escalate**: Application has stalled in 'active' stage for 112 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recgm6WsXDE6kai3o` — **escalate**: Application has stalled in 'active' stage for 75 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recgymUno5WByyfpw` — **escalate**: Application has stalled in 'active' stage for 61 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rechkEOP8SO6YAZwP` — **escalate**: Application has stalled in 'active' stage for 285 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rechkEOP8SO6YAZwP` — **escalate**: Application has stalled in 'active' stage for 51 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recjC9B0npOYnl6Fv` — **escalate**: Application has stalled in 'active' stage for 94 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recjiFf10TJC2GtFq` — **escalate**: Application has stalled in 'active' stage for 279 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recjosACysnRAz9kx` — **escalate**: Application has stalled in 'active' stage for 309 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `reckPFZqMRfntniP1` — **escalate**: Application has stalled in 'active' stage for 81 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `reckRKmre14sVycHD` — **escalate**: Application has stalled in 'active' stage for 80 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `reckvLPj8fnNRs3zo` — **escalate**: Application has stalled in 'active' stage for 54 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recnG4bunlXa5I0s2` — **escalate**: Application has stalled in 'active' stage for 74 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recnNSWq7W8QFkW06` — **escalate**: Application has stalled in 'active' stage for 84 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recnRKcf7Or1GcPEF` — **escalate**: Application has stalled in 'active' stage for 171 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recnyPtt3ifnZaIze` — **escalate**: Application has stalled in 'active' stage for 107 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recotonO4AWBKAuCE` — **escalate**: Application has stalled in 'active' stage for 34 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recpJXQzXLiVWnJHU` — **escalate**: Application has stalled in 'active' stage for 51 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recpJXQzXLiVWnJHU` — **escalate**: Application has stalled in 'active' stage for 134 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recpNVUxMNB2X0iiP` — **escalate**: Application has stalled in 'active' stage for 48 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recqECSuGzLxb0F5P` — **escalate**: Application has stalled in 'active' stage for 81 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recqK4UMVxaWYFRl1` — **escalate**: Application has stalled in 'active' stage for 82 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recqgXajW64OTDVp6` — **escalate**: Application has stalled in 'active' stage for 296 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recqgXajW64OTDVp6` — **escalate**: Application has stalled in 'active' stage for 373 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recrED1f8ADm6KRum` — **escalate**: Application has stalled in 'active' stage for 206 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recs076MlIqStP9FQ` — **escalate**: Application has stalled in 'active' stage for 131 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recsDmCI1I7xyCQve` — **escalate**: Application has stalled in 'active' stage for 40 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rectlS6DtLoFtEXbl` — **escalate**: Application has stalled in 'active' stage for 214 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rectlS6DtLoFtEXbl` — **escalate**: Application has stalled in 'active' stage for 140 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recuQQS15Jo3xrSFK` — **escalate**: Application has stalled in 'active' stage for 187 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `recwyGsLXtChYZFuy` — **escalate**: Application has stalled in 'active' stage for 90 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `reczd1OR5mG7CBIyt` — **escalate**: Application has stalled in 'active' stage for 255 days (>= 28 days threshold). Founder or talent lead escalation required. (human review required; confidence: high)
- `rec237RCQVkYLkBfS` — **advance**: Formal offer recdo5OPtRshen2iA is in 'pending' status. Confirm candidate decision and advance onboarding. (human review required; confidence: high)
- `rec7LQdOjD29mZIdc` — **advance**: Formal offer recWTalm9YjLpK1cI is in 'pending' status. Confirm candidate decision and advance onboarding. (human review required; confidence: high)
- `rec7LQdOjD29mZIdc` — **advance**: Formal offer rec2TF9eKlSg9xQg6 is in 'pending' status. Confirm candidate decision and advance onboarding. (human review required; confidence: high)
- `recJmDaQHQ0VqOjpO` — **advance**: Formal offer recs1Jiwz7YshxyIL is in 'pending' status. Confirm candidate decision and advance onboarding. (human review required; confidence: high)
- `recSKzUUzzULI0ou9` — **advance**: Formal offer recoO05BwhJFXxkoc is in 'pending' status. Confirm candidate decision and advance onboarding. (human review required; confidence: high)
- `rec3NCtlr82rF9BeT` — **review**: Application has stalled in 'active' stage for 23 days (>= 14 days threshold). Hiring manager review recommended. (human review required; confidence: high)
- `rec7fQTBfnulCrHov` — **review**: Application has stalled in 'active' stage for 16 days (>= 14 days threshold). Hiring manager review recommended. (human review required; confidence: medium)
- `recDAS27PGHKYk5Np` — **review**: Application has stalled in 'active' stage for 26 days (>= 14 days threshold). Hiring manager review recommended. (human review required; confidence: high)
- `recVhynlKLvxOuWDJ` — **review**: Application has stalled in 'active' stage for 16 days (>= 14 days threshold). Hiring manager review recommended. (human review required; confidence: medium)
- `recayha9Fwa1ucbaP` — **review**: Application has stalled in 'active' stage for 20 days (>= 14 days threshold). Hiring manager review recommended. (human review required; confidence: medium)
- `recxtoFya1C52rPvU` — **review**: Application has stalled in 'active' stage for 15 days (>= 14 days threshold). Hiring manager review recommended. (human review required; confidence: medium)
- `recy7HAMx3AZIHj8D` — **review**: Application has stalled in 'active' stage for 15 days (>= 14 days threshold). Hiring manager review recommended. (human review required; confidence: medium)

## Next actions

- Review prioritized advisory candidate action queue with hiring owners (no automated rejections).
- Triage 103 stalled application(s) to unblock candidates or close stale processes.
- Address drop-off attrition at the 'interview_to_offer' transition.
- Monday 09:00: Triage critical offer discrepancies (duplicate offers and salary band overruns).
- Monday 10:00: Rebalance screening workloads from overloaded recruiters (Ankit, Nadia) to Chetan.
- Monday 11:30: Interviewer burnout mitigation: redistribute technical screens from top 2 interviewers.
- Monday 14:00: Funnel bottleneck intervention on Interview -> Offer transition drop-offs.
- Monday 15:30: Realign headcount targets with department leads for under-hired departments.

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
