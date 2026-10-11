"""Immutable project schema 1.0.0; predictions, instances and individual reviews are separate."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum

from sic_xrt_analyzer.analysis.contracts import (
    AnalysisScope,
    AnalysisState,
    Region,
    utc_now,
)

from .geometry import DefectGeometry, DefectGeometryKind
from .validation import (
    SCHEMA_VERSION,
    digest,
    freeze_fields,
    integer,
    new_id,
    number,
    text,
    timestamp,
    unique,
)


class VerificationStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"


class ImageRole(str, Enum):
    BEFORE_ANNEALING = "BEFORE_ANNEALING"
    AFTER_ANNEALING = "AFTER_ANNEALING"
    REFERENCE = "REFERENCE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FileIdentity:
    canonical_path: str
    file_size: int
    mtime_ns: int

    def __post_init__(self):
        text(self.canonical_path, "canonical path")
        integer(self.file_size, "file size")
        integer(self.mtime_ns, "mtime")


@dataclass(frozen=True)
class VerifiedContentHash:
    value: str
    verified_at: datetime
    source_reference: str
    file_size: int
    mtime_ns: int
    algorithm: str = "sha256"

    def __post_init__(self):
        digest(self.value)
        timestamp(self.verified_at)
        text(self.source_reference)
        integer(self.file_size, "hash file size")
        integer(self.mtime_ns, "hash mtime")
        if self.algorithm != "sha256":
            raise ValueError("Unsupported content hash algorithm")


@dataclass(frozen=True)
class SpatialCalibration:
    spatial_axis_type: str = "UNKNOWN"
    acquisition_order: tuple[int, ...] = ()
    pixel_spacing_x: float | None = None
    pixel_spacing_y: float | None = None
    spacing_z: float | None = None
    unit: str | None = None
    orientation: str | None = None
    calibration_source: str | None = None
    calibration_status: VerificationStatus = VerificationStatus.UNKNOWN

    def __post_init__(self):
        text(self.spatial_axis_type)
        object.__setattr__(self, "acquisition_order", tuple(self.acquisition_order))
        for index in self.acquisition_order:
            integer(index, "acquisition order")
        for value in (self.pixel_spacing_x, self.pixel_spacing_y, self.spacing_z):
            if value is not None:
                number(value, "spacing", 0)
                if value == 0:
                    raise ValueError("Spacing must be positive")
        if not isinstance(self.calibration_status, VerificationStatus):
            raise TypeError("Explicit calibration status required")
        if self.spacing_z is not None and self.spatial_axis_type == "UNKNOWN":
            raise ValueError("Unknown stack axis cannot assert Z spacing")
        if (
            self.calibration_status == VerificationStatus.VERIFIED
            and not self.calibration_source
        ):
            raise ValueError("Verified calibration requires its source")
        for value in (self.unit, self.orientation, self.calibration_source):
            text(value, optional=True)


@dataclass(frozen=True)
class WaferPlacement:
    wafer_id: str | None = None
    tile_position: tuple[float, float] | None = None
    alignment_reference: str | None = None
    coordinate_system: str = "UNKNOWN"
    calibration_status: VerificationStatus = VerificationStatus.UNKNOWN

    def __post_init__(self):
        text(self.wafer_id, optional=True)
        text(self.alignment_reference, optional=True)
        text(self.coordinate_system)
        if self.tile_position is not None:
            object.__setattr__(self, "tile_position", tuple(self.tile_position))
            if len(self.tile_position) != 2:
                raise ValueError("Tile position requires two coordinates")
            for value in self.tile_position:
                number(value, "tile position")
        if not isinstance(self.calibration_status, VerificationStatus):
            raise TypeError("Explicit wafer calibration required")
        if self.calibration_status == VerificationStatus.VERIFIED and (
            not self.wafer_id
            or self.tile_position is None
            or self.coordinate_system == "UNKNOWN"
        ):
            raise ValueError(
                "Verified wafer placement requires a known coordinate system and position"
            )


@dataclass(frozen=True)
class ImageSourceRecord:
    source_id: str
    display_name: str
    source_reference: str
    width: int
    height: int
    dtype: str
    bit_depth: int
    channels: int
    page_count: int
    file_identity: FileIdentity
    acquisition_metadata: Mapping = field(default_factory=dict)
    content_hash: VerifiedContentHash | None = None
    role: ImageRole = ImageRole.UNKNOWN
    calibration: SpatialCalibration = field(default_factory=SpatialCalibration)
    wafer_placement: WaferPlacement = field(default_factory=WaferPlacement)

    def __post_init__(self):
        for value in (
            self.source_id,
            self.display_name,
            self.source_reference,
            self.dtype,
        ):
            text(value)
        for name in ("width", "height", "bit_depth", "channels", "page_count"):
            integer(getattr(self, name), name, 1)
        if not isinstance(self.file_identity, FileIdentity) or not isinstance(
            self.role, ImageRole
        ):
            raise TypeError("Typed source identity and role required")
        if not isinstance(self.calibration, SpatialCalibration) or not isinstance(
            self.wafer_placement, WaferPlacement
        ):
            raise TypeError("Typed calibration/placement required")
        if self.calibration.acquisition_order and (
            len(self.calibration.acquisition_order) != self.page_count
            or len(set(self.calibration.acquisition_order)) != self.page_count
        ):
            raise ValueError(
                "Acquisition order must explicitly identify every page once"
            )
        if self.content_hash is not None:
            h = self.content_hash
            if not isinstance(h, VerifiedContentHash) or (
                h.source_reference,
                h.file_size,
                h.mtime_ns,
            ) != (
                self.source_reference,
                self.file_identity.file_size,
                self.file_identity.mtime_ns,
            ):
                raise ValueError(
                    "Content hash verification snapshot must match source identity"
                )
        freeze_fields(self, "acquisition_metadata")


@dataclass(frozen=True)
class ModelProvenance:
    provenance_id: str
    model_id: str
    model_version: str
    inference_run_id: str
    model_hash: str | None = None
    input_contract: Mapping = field(default_factory=dict)
    output_contract: Mapping = field(default_factory=dict)
    training_dataset_version: str | None = None
    manifest_snapshot: Mapping = field(default_factory=dict)

    def __post_init__(self):
        for value in (
            self.provenance_id,
            self.model_id,
            self.model_version,
            self.inference_run_id,
        ):
            text(value)
        if self.model_hash is not None:
            digest(self.model_hash)
        text(self.training_dataset_version, optional=True)
        freeze_fields(self, "input_contract", "output_contract", "manifest_snapshot")


@dataclass(frozen=True)
class AnalysisRunRecord:
    run_id: str
    project_id: str
    source_id: str
    page_index: int
    scope: AnalysisScope
    analysis_roi: Region | None
    model_id: str
    model_version: str
    model_hash: str | None
    provenance_id: str
    candidate_method: str | None
    candidate_parameters: Mapping
    classification_parameters: Mapping
    started_at: datetime
    completed_at: datetime | None
    run_status: AnalysisState
    result_id: str | None
    source_identity: Mapping
    parameters: Mapping = field(default_factory=dict)
    summary: Mapping = field(default_factory=dict)
    preprocessing: Mapping = field(default_factory=dict)
    error: Mapping | None = None
    duration: float | None = None
    legacy_contract_version: str | None = None

    def __post_init__(self):
        for value in (
            self.run_id,
            self.project_id,
            self.source_id,
            self.model_id,
            self.model_version,
            self.provenance_id,
        ):
            text(value)
        text(self.result_id, optional=True)
        text(self.candidate_method, optional=True)
        text(self.legacy_contract_version, optional=True)
        integer(self.page_index, "run page")
        timestamp(self.started_at)
        if self.completed_at is not None:
            timestamp(self.completed_at)
            if self.completed_at < self.started_at:
                raise ValueError("Completion precedes start")
        if not isinstance(self.scope, AnalysisScope) or not isinstance(
            self.run_status, AnalysisState
        ):
            raise TypeError("Explicit analysis scope/status required")
        if (self.scope == AnalysisScope.ROI) != (self.analysis_roi is not None):
            raise ValueError("ROI scope and region mismatch")
        if self.analysis_roi is not None and not isinstance(self.analysis_roi, Region):
            raise ValueError("Typed original-pixel region required")
        if self.model_hash is not None:
            digest(self.model_hash)
        if self.duration is not None:
            number(self.duration, "duration", 0)
        if self.error is not None:
            freeze_fields(self, "error")
        freeze_fields(
            self,
            "candidate_parameters",
            "classification_parameters",
            "source_identity",
            "parameters",
            "summary",
            "preprocessing",
        )


@dataclass(frozen=True)
class CandidateObservation:
    observation_id: str
    run_id: str
    source_candidate_id: str
    point_id: str | None
    x: float | None
    y: float | None
    page_index: int
    assigned_class: str | None
    raw_scores: tuple[float, ...]
    displayed_score: float | None
    low_score: bool | None
    proposal_method: str | None
    geometry_id: str
    observation_status: str = "UNREVIEWED"
    metadata: Mapping = field(default_factory=dict)
    source_class_id: str | int | None = None

    def __post_init__(self):
        for value in (
            self.observation_id,
            self.run_id,
            self.source_candidate_id,
            self.geometry_id,
            self.observation_status,
        ):
            text(value)
        for value in (self.point_id, self.assigned_class, self.proposal_method):
            text(value, optional=True)
        integer(self.page_index, "observation page")
        if (self.x is None) != (self.y is None):
            raise ValueError("Both point coordinates must be present or absent")
        if self.x is not None:
            number(self.x, "x")
            number(self.y, "y")
        if self.displayed_score is not None:
            number(self.displayed_score, "display score", 0, 1)
        if self.low_score is not None and type(self.low_score) is not bool:
            raise ValueError("low_score must be bool or absent")
        if self.source_class_id is not None and type(self.source_class_id) not in (
            str,
            int,
        ):
            raise ValueError("Original class ID must be a string/integer or absent")
        object.__setattr__(self, "raw_scores", tuple(self.raw_scores))
        for score in self.raw_scores:
            number(score, "raw score")
        freeze_fields(self, "metadata")


@dataclass(frozen=True)
class ModelPrediction:
    prediction_id: str
    observation_id: str
    provenance_id: str
    assigned_class: str | None
    raw_scores: tuple[float, ...]
    displayed_score: float | None
    score_labels: tuple[str, ...] = ()
    score_meaning: str = "UNSPECIFIED"

    def __post_init__(self):
        for value in (
            self.prediction_id,
            self.observation_id,
            self.provenance_id,
            self.score_meaning,
        ):
            text(value)
        text(self.assigned_class, optional=True)
        object.__setattr__(self, "raw_scores", tuple(self.raw_scores))
        object.__setattr__(self, "score_labels", tuple(self.score_labels))
        for score in self.raw_scores:
            number(score, "raw score")
        if self.score_labels and (
            len(self.score_labels) != len(self.raw_scores)
            or len(set(self.score_labels)) != len(self.score_labels)
        ):
            raise ValueError("Score labels must identify every score once")
        for label in self.score_labels:
            text(label)
        if self.displayed_score is not None:
            number(self.displayed_score, "display score", 0, 1)


class LinkStatus(str, Enum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class ObservationLink:
    observation_id: str
    status: LinkStatus = LinkStatus.PROPOSED

    def __post_init__(self):
        text(self.observation_id)
        if not isinstance(self.status, LinkStatus):
            raise TypeError("Explicit observation link status required")


@dataclass(frozen=True)
class LabelAssessment:
    adjudicated_label: str | None = None
    ground_truth_eligible: bool = False
    adjudication_reference: str | None = None
    adjudicator_ids: tuple[str, ...] = ()
    adjudicated_at: datetime | None = None

    def __post_init__(self):
        object.__setattr__(self, "adjudicator_ids", tuple(self.adjudicator_ids))
        if type(self.ground_truth_eligible) is not bool:
            raise ValueError("Eligibility is explicit")
        if self.adjudicated_label is None:
            if (
                self.ground_truth_eligible
                or self.adjudication_reference
                or self.adjudicator_ids
                or self.adjudicated_at is not None
            ):
                raise ValueError(
                    "Individual reviews do not imply adjudication/ground truth"
                )
        else:
            text(self.adjudicated_label)
            text(self.adjudication_reference)
            timestamp(self.adjudicated_at)
            if not self.adjudicator_ids:
                raise ValueError("External adjudication requires responsible reviewers")
            for reviewer in self.adjudicator_ids:
                text(reviewer)


@dataclass(frozen=True)
class DefectInstance:
    instance_id: str
    source_id: str
    geometry_id: str
    linked_observations: tuple[ObservationLink, ...] = ()
    class_label: str | None = None
    instance_status: str = "PROPOSED"
    revision: int = 1
    assessment: LabelAssessment = field(default_factory=LabelAssessment)

    def __post_init__(self):
        for value in (
            self.instance_id,
            self.source_id,
            self.geometry_id,
            self.instance_status,
        ):
            text(value)
        text(self.class_label, optional=True)
        integer(self.revision, "instance revision", 1)
        object.__setattr__(self, "linked_observations", tuple(self.linked_observations))
        if any(
            not isinstance(link, ObservationLink) for link in self.linked_observations
        ) or not isinstance(self.assessment, LabelAssessment):
            raise ValueError("Typed instance links and assessment required")
        unique(self.linked_observations, "observation_id")


class ReviewStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"
    UNCERTAIN = "UNCERTAIN"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ReviewTarget(str, Enum):
    OBSERVATION = "OBSERVATION"
    DEFECT_INSTANCE = "DEFECT_INSTANCE"


@dataclass(frozen=True)
class ReviewEvent:
    review_id: str
    target_type: ReviewTarget
    target_id: str
    reviewer_id: str
    review_status: ReviewStatus
    original_prediction: Mapping
    created_at: datetime
    revision: int
    source_run_id: str | None = None
    corrected_class: str | None = None
    corrected_geometry_reference: str | None = None
    comment: str = ""
    parent_review_ids: tuple[str, ...] = ()

    def __post_init__(self):
        for value in (self.review_id, self.target_id, self.reviewer_id):
            text(value)
        if not isinstance(self.target_type, ReviewTarget) or not isinstance(
            self.review_status, ReviewStatus
        ):
            raise TypeError("Explicit review target/status required")
        integer(self.revision, "review revision", 1)
        timestamp(self.created_at)
        if not isinstance(self.comment, str):
            raise TypeError("Review comment must be text")
        for value in (
            self.source_run_id,
            self.corrected_class,
            self.corrected_geometry_reference,
        ):
            text(value, optional=True)
        object.__setattr__(self, "parent_review_ids", tuple(self.parent_review_ids))
        if len(set(self.parent_review_ids)) != len(self.parent_review_ids):
            raise ValueError("Duplicate review parents")
        for value in self.parent_review_ids:
            text(value)
        corrected = (
            self.corrected_class is not None
            or self.corrected_geometry_reference is not None
        )
        if (self.review_status == ReviewStatus.CORRECTED) != corrected:
            raise ValueError(
                "CORRECTED requires explicit class/geometry; other statuses cannot change them"
            )
        freeze_fields(self, "original_prediction")


@dataclass(frozen=True)
class ImageRelationship:
    relationship_id: str
    source_image_id: str
    target_image_id: str
    source_role: ImageRole = ImageRole.UNKNOWN
    target_role: ImageRole = ImageRole.UNKNOWN
    registration_id: str | None = None
    transform_reference: str | None = None
    match_quality: float | None = None
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN

    def __post_init__(self):
        for value in (self.relationship_id, self.source_image_id, self.target_image_id):
            text(value)
        if self.source_image_id == self.target_image_id:
            raise ValueError("Relationship requires distinct images")
        if (
            not isinstance(self.source_role, ImageRole)
            or not isinstance(self.target_role, ImageRole)
            or not isinstance(self.verification_status, VerificationStatus)
        ):
            raise TypeError("Explicit relationship roles/status required")
        text(self.registration_id, optional=True)
        if self.transform_reference is not None:
            from .validation import asset_reference

            asset_reference(self.transform_reference)
        if self.match_quality is not None:
            number(self.match_quality, "match quality")
        if self.verification_status == VerificationStatus.VERIFIED and (
            not self.registration_id or not self.transform_reference
        ):
            raise ValueError("Verified registration requires ID/transform")


@dataclass(frozen=True)
class AnalysisProject:
    project_name: str
    project_id: str = field(default_factory=new_id)
    schema_version: str = SCHEMA_VERSION
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    revision: int = 1
    image_sources: tuple[ImageSourceRecord, ...] = ()
    analysis_runs: tuple[AnalysisRunRecord, ...] = ()
    observations: tuple[CandidateObservation, ...] = ()
    predictions: tuple[ModelPrediction, ...] = ()
    defect_instances: tuple[DefectInstance, ...] = ()
    geometries: tuple[DefectGeometry, ...] = ()
    review_events: tuple[ReviewEvent, ...] = ()
    image_relationships: tuple[ImageRelationship, ...] = ()
    model_provenance: tuple[ModelProvenance, ...] = ()

    def __post_init__(self):
        text(self.project_name)
        text(self.project_id)
        integer(self.revision, "project revision", 1)
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported project schema: {self.schema_version}")
        timestamp(self.created_at)
        timestamp(self.updated_at)
        if self.updated_at < self.created_at:
            raise ValueError("Project update precedes creation")
        tables = {}
        specs = [
            ("image_sources", ImageSourceRecord, "source_id"),
            ("analysis_runs", AnalysisRunRecord, "run_id"),
            ("observations", CandidateObservation, "observation_id"),
            ("predictions", ModelPrediction, "prediction_id"),
            ("defect_instances", DefectInstance, "instance_id"),
            ("geometries", DefectGeometry, "geometry_id"),
            ("review_events", ReviewEvent, "review_id"),
            ("image_relationships", ImageRelationship, "relationship_id"),
            ("model_provenance", ModelProvenance, "provenance_id"),
        ]
        all_ids = {self.project_id}
        for name, cls, key in specs:
            rows = tuple(getattr(self, name))
            object.__setattr__(self, name, rows)
            if any(not isinstance(row, cls) for row in rows):
                raise ValueError(f"{name} requires typed records")
            table = unique(rows, key)
            if all_ids & table.keys():
                raise ValueError(
                    "Persistent entity IDs must also be unique across tables"
                )
            all_ids.update(table)
            tables[name] = table
        sources, runs, obs, preds, geoms, prov = (
            tables[n]
            for n in (
                "image_sources",
                "analysis_runs",
                "observations",
                "predictions",
                "geometries",
                "model_provenance",
            )
        )
        for geometry in self.geometries:
            if geometry.source_id not in sources:
                raise ValueError("Geometry references absent source")
            geometry.validate_source(sources[geometry.source_id])
        for run in self.analysis_runs:
            if (
                run.project_id != self.project_id
                or run.source_id not in sources
                or run.provenance_id not in prov
            ):
                raise ValueError("Run project/source/model reference mismatch")
            source, model = sources[run.source_id], prov[run.provenance_id]
            if run.page_index >= source.page_count or (
                run.model_id,
                run.model_version,
                run.model_hash,
                run.result_id,
            ) != (
                model.model_id,
                model.model_version,
                model.model_hash,
                model.inference_run_id,
            ):
                raise ValueError("Run page/model provenance mismatch")
            snapshot = run.source_identity
            for key in (
                "canonical_path",
                "file_size",
                "mtime_ns",
                "page_index",
                "width",
                "height",
            ):
                if key not in snapshot:
                    raise ValueError("Run lacks its original source identity snapshot")
            text(snapshot["canonical_path"])
            for key in ("file_size", "mtime_ns", "page_index", "width", "height"):
                integer(snapshot[key], "original " + key)
            if (
                snapshot["width"],
                snapshot["height"],
                snapshot["page_index"],
                snapshot["file_size"],
            ) != (
                source.width,
                source.height,
                run.page_index,
                source.file_identity.file_size,
            ):
                raise ValueError("Run original identity dimensions/page/size mismatch")
            if run.analysis_roi:
                r = run.analysis_roi
                for name in ("x", "y", "width", "height"):
                    integer(
                        getattr(r, name),
                        "ROI " + name,
                        1 if name in ("width", "height") else 0,
                    )
                if r.x + r.width > source.width or r.y + r.height > source.height:
                    raise ValueError("Analysis ROI outside original source")
        candidate_keys = set()
        for observation in self.observations:
            if observation.run_id not in runs or observation.geometry_id not in geoms:
                raise ValueError("Observation run/geometry reference absent")
            run, geometry = runs[observation.run_id], geoms[observation.geometry_id]
            if (geometry.source_id, geometry.page_index, observation.page_index) != (
                run.source_id,
                run.page_index,
                run.page_index,
            ):
                raise ValueError("Observation source/page mismatch")
            point = (
                geometry.points[0]
                if geometry.kind == DefectGeometryKind.POINT
                else (None, None)
            )
            if (observation.x, observation.y) != point:
                raise ValueError("Observation coordinates do not match its geometry")
            key = (observation.run_id, observation.source_candidate_id)
            if key in candidate_keys:
                raise ValueError("Duplicate candidate in same run")
            candidate_keys.add(key)
        predicted = set()
        for prediction in self.predictions:
            if prediction.observation_id not in obs:
                raise ValueError("Prediction references absent observation")
            o = obs[prediction.observation_id]
            if (
                prediction.observation_id in predicted
                or prediction.provenance_id != runs[o.run_id].provenance_id
                or (
                    prediction.assigned_class,
                    prediction.raw_scores,
                    prediction.displayed_score,
                )
                != (o.assigned_class, o.raw_scores, o.displayed_score)
            ):
                raise ValueError(
                    "Prediction duplicates or changes original observation scores/class"
                )
            predicted.add(prediction.observation_id)
        if predicted != set(obs):
            raise ValueError("Every observation requires its recorded model prediction")
        for instance in self.defect_instances:
            if (
                instance.source_id not in sources
                or instance.geometry_id not in geoms
                or geoms[instance.geometry_id].source_id != instance.source_id
            ):
                raise ValueError("Instance source/geometry mismatch")
            for link in instance.linked_observations:
                if (
                    link.observation_id not in obs
                    or runs[obs[link.observation_id].run_id].source_id
                    != instance.source_id
                ):
                    raise ValueError(
                        "Instance links an absent/different-image observation"
                    )
        for relationship in self.image_relationships:
            if (
                relationship.source_image_id not in sources
                or relationship.target_image_id not in sources
            ):
                raise ValueError("Relationship references absent image")
        prediction_by_observation = {p.observation_id: p for p in preds.values()}
        seen_reviews = {}
        for event in self.review_events:
            target = (
                obs.get(event.target_id)
                if event.target_type == ReviewTarget.OBSERVATION
                else tables["defect_instances"].get(event.target_id)
            )
            if target is None:
                raise ValueError("Review target absent")
            source_id = (
                runs[target.run_id].source_id
                if event.target_type == ReviewTarget.OBSERVATION
                else target.source_id
            )
            if event.source_run_id is not None and (
                event.source_run_id not in runs
                or runs[event.source_run_id].source_id != source_id
            ):
                raise ValueError("Review run/source mismatch")
            if event.target_type == ReviewTarget.OBSERVATION:
                prediction = prediction_by_observation[target.observation_id]
                expected = {
                    "prediction_id": prediction.prediction_id,
                    "assigned_class": prediction.assigned_class,
                    "raw_scores": prediction.raw_scores,
                    "displayed_score": prediction.displayed_score,
                }
                if (
                    event.source_run_id != target.run_id
                    or dict(event.original_prediction) != expected
                ):
                    raise ValueError(
                        "Review must preserve the original prediction snapshot"
                    )
            if event.target_type == ReviewTarget.DEFECT_INSTANCE:
                expected = {
                    "prediction_ids": tuple(
                        prediction_by_observation[link.observation_id].prediction_id
                        for link in target.linked_observations
                    ),
                    "class_label": target.class_label,
                    "geometry_id": target.geometry_id,
                }
                if dict(event.original_prediction) != expected:
                    raise ValueError(
                        "Defect review must preserve its original linked prediction/shape references"
                    )
            if event.corrected_geometry_reference:
                geometry = geoms.get(event.corrected_geometry_reference)
                original_geometry = geoms[target.geometry_id]
                if geometry is None or (geometry.source_id, geometry.page_index) != (
                    source_id,
                    original_geometry.page_index,
                ):
                    raise ValueError(
                        "Corrected geometry/source/page reference mismatch"
                    )
            parents = []
            for parent_id in event.parent_review_ids:
                parent = seen_reviews.get(parent_id)
                if parent is None or (
                    parent.target_type,
                    parent.target_id,
                    parent.reviewer_id,
                ) != (event.target_type, event.target_id, event.reviewer_id):
                    raise ValueError(
                        "Review parent must exist earlier for the same reviewer/target"
                    )
                parents.append(parent)
            if event.revision != (
                max(p.revision for p in parents) + 1 if parents else 1
            ):
                raise ValueError("Review revision must follow its declared parents")
            seen_reviews[event.review_id] = event

    def evolve(self, **changes):
        if any(
            key in changes
            for key in (
                "project_id",
                "created_at",
                "schema_version",
                "revision",
                "updated_at",
            )
        ):
            raise ValueError("Project identity/version/revision are managed")
        return replace(
            self, **changes, revision=self.revision + 1, updated_at=utc_now()
        )
