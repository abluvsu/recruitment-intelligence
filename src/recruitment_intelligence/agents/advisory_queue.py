"""Advisory candidate action queue generator.

Produces candidate-level recommendations restricted strictly to advisory terminology:
`review`, `advance`, `escalate`, `request_feedback`, `close`.
Zero automated rejections; all recommendations enforce `requires_human_review=True`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from ..analytics.metrics import (
    Record,
    Tables,
    _as_of,
    _date,
    _id,
    _linked_id,
    _rows,
    _status,
    _text,
    _value,
    stalled_applications,
)
from ..domain import (
    CandidateRecommendation,
    Confidence,
    EvidenceReference,
    RecommendationAction,
)
from ..domain.models import Serializable


# Canonical vocabulary mapping for natural variations
_ACTION_MAP: dict[str, RecommendationAction] = {
    "review": RecommendationAction.REVIEW,
    "inspect": RecommendationAction.REVIEW,
    "human_review": RecommendationAction.REVIEW,
    "advance": RecommendationAction.ADVANCE,
    "next_stage": RecommendationAction.ADVANCE,
    "proceed": RecommendationAction.ADVANCE,
    "escalate": RecommendationAction.ESCALATE,
    "urgent": RecommendationAction.ESCALATE,
    "request_feedback": RecommendationAction.REQUEST_FEEDBACK,
    "request feedback": RecommendationAction.REQUEST_FEEDBACK,
    "feedback": RecommendationAction.REQUEST_FEEDBACK,
    "close": RecommendationAction.CLOSE,
    "close_current_process": RecommendationAction.CLOSE,
    "close current process": RecommendationAction.CLOSE,
    "close_process": RecommendationAction.CLOSE,
    # Non-advisory / terminal actions are explicitly coerced to advisory review
    "reject": RecommendationAction.REVIEW,
    "rejected": RecommendationAction.REVIEW,
    "withdraw": RecommendationAction.REVIEW,
    "withdrawn": RecommendationAction.REVIEW,
}


def normalize_action(action_raw: Any) -> RecommendationAction:
    """Normalize input action string to canonical RecommendationAction."""
    if isinstance(action_raw, RecommendationAction):
        return action_raw
    cleaned = str(action_raw or "").strip().lower().replace("-", "_")
    if cleaned in _ACTION_MAP:
        return _ACTION_MAP[cleaned]
    # Default safe fallback
    return RecommendationAction.REVIEW


@dataclass(frozen=True, slots=True)
class AdvisoryActionQueue(Serializable):
    """Immutable advisory candidate action queue."""
    actions: tuple[CandidateRecommendation, ...]
    total_count: int = 0
    stalled_count: int = 0
    feedback_pending_count: int = 0
    offer_pending_count: int = 0
    close_recommended_count: int = 0

    def actions_by_type(self, action: RecommendationAction | str) -> tuple[CandidateRecommendation, ...]:
        target = normalize_action(action)
        return tuple(a for a in self.actions if a.action == target)


def generate_advisory_actions(
    tables: Tables | Sequence[Record],
    as_of: date | datetime | str | None = None,
    threshold_days: int = 14,
) -> tuple[CandidateRecommendation, ...]:
    """Generate advisory candidate recommendations from snapshot data.

    Evaluates:
    - Stalled active applications (>= threshold_days no update) -> escalate / review
    - Pending interview scorecards -> request_feedback
    - Pending formal offers -> advance / review
    - Terminal applications -> close (advisory, requiring human review)
    """
    apps = _rows(tables, "Applications")
    if not apps:
        return ()

    ref_date = _as_of(as_of)
    actions: list[CandidateRecommendation] = []
    seen_keys: set[tuple[str, str, RecommendationAction]] = set()

    # 1. Stalled applications (>= threshold_days without activity)
    stalled_list = stalled_applications(tables, threshold_days=threshold_days, as_of=ref_date)
    for idx, st in enumerate(stalled_list):
        app_id = str(st.get("application_id") or "").strip() or f"app-stalled-{idx+1}"
        cand_id = str(st.get("candidate_id") or "").strip() or f"cand-for-{app_id}"
        days = st["days_stalled"]
        stage = st["status"]

        if days >= 28:
            act = RecommendationAction.ESCALATE
            rationale = (
                f"Application has stalled in '{stage}' stage for {days} days "
                f"(>= 28 days threshold). Founder or talent lead escalation required."
            )
            conf = Confidence.HIGH
        else:
            act = RecommendationAction.REVIEW
            rationale = (
                f"Application has stalled in '{stage}' stage for {days} days "
                f"(>= {threshold_days} days threshold). Hiring manager review recommended."
            )
            conf = Confidence.HIGH if days >= 21 else Confidence.MEDIUM

        key = (cand_id, app_id, act)
        if key not in seen_keys:
            seen_keys.add(key)
            ev = EvidenceReference(
                source="analytics.stalled_applications",
                table="Applications",
                record_ids=(app_id,),
                method="stalled_application_check",
                caveats=(f"Days stalled: {days}; stage: {stage}",),
            )
            actions.append(
                CandidateRecommendation(
                    candidate_id=cand_id,
                    application_id=app_id,
                    action=act,
                    rationale=rationale,
                    confidence=conf,
                    evidence=(ev,),
                    requires_human_review=True,
                )
            )

    # 2. Completed / scheduled interviews pending feedback
    interviews = _rows(tables, "Interviews") if isinstance(tables, Mapping) else []
    apps_by_id = {_id(a): a for a in apps if _id(a)}
    terminal_statuses = {"hired", "rejected", "withdrawn", "closed", "accepted"}

    for idx, iv in enumerate(interviews):
        iv_id = _id(iv) or f"int-{idx+1}"
        app_id = _text(_value(iv, "application_id", "application"))
        if not app_id or app_id not in apps_by_id:
            continue
        app = apps_by_id[app_id]
        if _status(app) in terminal_statuses:
            continue

        cand_id = _linked_id(_value(app, "candidate_id", "candidate")) or f"cand-for-{app_id}"
        iv_status = _text(_value(iv, "status", "stage")).lower()
        completed_at = _date(_value(iv, "completed_at", "scheduled_at", "date"))

        # Evaluate interview status and scorecard score
        raw_score = _value(iv, "score", "rating")
        score = None
        if raw_score is not None:
            try:
                score = float(raw_score)
            except (ValueError, TypeError):
                score = None

        # If interview is completed or scheduled in the past, evaluate feedback or score
        if iv_status in {"completed", "scheduled", "pending"} and completed_at and completed_at <= ref_date:
            if iv_status == "completed" and score is not None and score >= 4:
                # High-performing candidate: advance immediately
                act = RecommendationAction.ADVANCE
                rationale = (
                    f"Candidate achieved top interview score ({score:g}/5) on {completed_at.isoformat()} "
                    f"in interview {iv_id}. Advance to next stage or extend offer."
                )
                method = "high_score_advance"
            elif iv_status == "completed" and score is not None and score <= 2:
                # Low score: review with hiring manager
                act = RecommendationAction.REVIEW
                rationale = (
                    f"Candidate received below-threshold interview score ({score:g}/5) on {completed_at.isoformat()} "
                    f"in interview {iv_id}. Hiring manager review recommended before proceeding."
                )
                method = "low_score_review"
            else:
                # Scorecard pending or average score (e.g. 3): request feedback
                act = RecommendationAction.REQUEST_FEEDBACK
                rationale = (
                    f"Interview {iv_id} completed or scheduled on {completed_at.isoformat()}; "
                    f"request interviewer scorecard and evaluation."
                )
                method = "interview_feedback_pending"

            key = (cand_id, app_id, act)
            if key not in seen_keys:
                seen_keys.add(key)
                ev = EvidenceReference(
                    source="airtable.interviews",
                    table="Interviews",
                    record_ids=(iv_id,),
                    method=method,
                    caveats=(f"Interview status: {iv_status}; date: {completed_at.isoformat()}; score: {score}",),
                )
                actions.append(
                    CandidateRecommendation(
                        candidate_id=cand_id,
                        application_id=app_id,
                        action=act,
                        rationale=rationale,
                        confidence=Confidence.HIGH,
                        evidence=(ev,),
                        requires_human_review=True,
                    )
                )

    # 3. Pending formal offers requiring follow-up
    offers = _rows(tables, "Offers") if isinstance(tables, Mapping) else []
    for idx, off in enumerate(offers):
        off_id = _id(off) or f"off-{idx+1}"
        app_id = _text(_value(off, "application_id", "application"))
        if not app_id or app_id not in apps_by_id:
            continue
        app = apps_by_id[app_id]
        if _status(app) in terminal_statuses:
            continue

        off_status = _text(_value(off, "status")).lower()
        if off_status in {"pending", "sent", "draft", "extended", "open"}:
            cand_id = _linked_id(_value(off, "candidate_id", "candidate")) or _linked_id(_value(app, "candidate_id", "candidate")) or f"cand-for-{app_id}"
            act = RecommendationAction.ADVANCE
            key = (cand_id, app_id, act)
            if key not in seen_keys:
                seen_keys.add(key)
                ev = EvidenceReference(
                    source="airtable.offers",
                    table="Offers",
                    record_ids=(off_id,),
                    method="pending_offer_follow_up",
                    caveats=(f"Offer status: {off_status}",),
                )
                actions.append(
                    CandidateRecommendation(
                        candidate_id=cand_id,
                        application_id=app_id,
                        action=act,
                        rationale=f"Formal offer {off_id} is in '{off_status}' status. Confirm candidate decision and advance onboarding.",
                        confidence=Confidence.HIGH,
                        evidence=(ev,),
                        requires_human_review=True,
                    )
                )

    # 4. Terminal status applications needing clean process closure
    for idx, app in enumerate(apps):
        app_id = _id(app) or f"app-{idx+1}"
        app_st = _status(app)
        if app_st in {"rejected", "withdrawn"}:
            cand_id = _linked_id(_value(app, "candidate_id", "candidate")) or f"cand-for-{app_id}"
            act = RecommendationAction.CLOSE
            key = (cand_id, app_id, act)
            if key not in seen_keys:
                seen_keys.add(key)
                ev = EvidenceReference(
                    source="airtable.applications",
                    table="Applications",
                    record_ids=(app_id,),
                    method="terminal_process_closure",
                    caveats=(f"Terminal status: {app_st}",),
                )
                actions.append(
                    CandidateRecommendation(
                        candidate_id=cand_id,
                        application_id=app_id,
                        action=act,
                        rationale=f"Application {app_id} marked as '{app_st}'. Close current process in tracking system (human confirmation required).",
                        confidence=Confidence.HIGH,
                        evidence=(ev,),
                        requires_human_review=True,
                    )
                )

    # Deterministic sorting: by action priority, candidate_id, application_id
    action_priority = {
        RecommendationAction.ESCALATE: 0,
        RecommendationAction.REQUEST_FEEDBACK: 1,
        RecommendationAction.ADVANCE: 2,
        RecommendationAction.REVIEW: 3,
        RecommendationAction.CLOSE: 4,
    }
    return tuple(sorted(
        actions,
        key=lambda a: (action_priority.get(a.action, 99), a.action.value, a.candidate_id, str(a.application_id)),
    ))


def build_advisory_queue(
    tables: Tables | Sequence[Record],
    as_of: date | datetime | str | None = None,
    threshold_days: int = 14,
) -> AdvisoryActionQueue:
    """Construct a typed AdvisoryActionQueue instance."""
    actions = generate_advisory_actions(tables, as_of=as_of, threshold_days=threshold_days)
    stalled = sum(1 for a in actions if a.action in (RecommendationAction.ESCALATE, RecommendationAction.REVIEW))
    feedback = sum(1 for a in actions if a.action == RecommendationAction.REQUEST_FEEDBACK)
    offers = sum(1 for a in actions if a.action == RecommendationAction.ADVANCE)
    close = sum(1 for a in actions if a.action == RecommendationAction.CLOSE)
    return AdvisoryActionQueue(
        actions=actions,
        total_count=len(actions),
        stalled_count=stalled,
        feedback_pending_count=feedback,
        offer_pending_count=offers,
        close_recommended_count=close,
    )
