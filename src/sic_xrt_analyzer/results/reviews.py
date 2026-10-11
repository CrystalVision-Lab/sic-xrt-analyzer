"""Append-only, idempotent individual review histories with explicit fork/conflict states."""

from dataclasses import dataclass, field

from .contracts import LabelAssessment, ReviewEvent, ReviewStatus, ReviewTarget
from .validation import freeze_fields


def prediction_snapshot(project, target_type, target_id):
    if not isinstance(target_type, ReviewTarget):
        raise TypeError("Explicit review target type required")
    try:
        if target_type == ReviewTarget.OBSERVATION:
            observation = next(
                o for o in project.observations if o.observation_id == target_id
            )
            prediction = next(
                p for p in project.predictions if p.observation_id == target_id
            )
            return {
                "prediction_id": prediction.prediction_id,
                "assigned_class": prediction.assigned_class,
                "raw_scores": prediction.raw_scores,
                "displayed_score": prediction.displayed_score,
            }, observation.run_id
        instance = next(
            i for i in project.defect_instances if i.instance_id == target_id
        )
        return {
            "prediction_ids": tuple(
                next(
                    p.prediction_id
                    for p in project.predictions
                    if p.observation_id == link.observation_id
                )
                for link in instance.linked_observations
            ),
            "class_label": instance.class_label,
            "geometry_id": instance.geometry_id,
        }, None
    except StopIteration as exc:
        raise ValueError("Review target or prediction is absent") from exc


@dataclass(frozen=True)
class ReviewState:
    status: ReviewStatus
    conflict: bool
    tips_by_reviewer: dict
    assessment: LabelAssessment = field(default_factory=LabelAssessment)

    def __post_init__(self):
        freeze_fields(self, "tips_by_reviewer")


class ReviewRepository:
    def append(self, project, event: ReviewEvent):
        existing = next(
            (e for e in project.review_events if e.review_id == event.review_id), None
        )
        if existing is not None:
            if existing != event:
                raise ValueError("Duplicate review ID contains a different event")
            return project
        return project.evolve(review_events=project.review_events + (event,))

    def history(self, project, target_type, target_id):
        prediction_snapshot(
            project, target_type, target_id
        )  # Reject absent targets even if they have no events.
        return tuple(
            e
            for e in project.review_events
            if (e.target_type, e.target_id) == (target_type, target_id)
        )

    def current(self, project, target_type, target_id):
        events = self.history(project, target_type, target_id)
        superseded = {parent for e in events for parent in e.parent_review_ids}
        tips = [e for e in events if e.review_id not in superseded]
        by_reviewer = {}
        for event in tips:
            by_reviewer.setdefault(event.reviewer_id, []).append(event.review_id)
        meanings = {
            (e.review_status, e.corrected_class, e.corrected_geometry_reference)
            for e in tips
        }
        conflict = len(meanings) > 1 or any(
            len(ids) > 1 for ids in by_reviewer.values()
        )
        status = (
            ReviewStatus.NEEDS_REVIEW if conflict or not tips else tips[0].review_status
        )
        return ReviewState(status, conflict, by_reviewer)
