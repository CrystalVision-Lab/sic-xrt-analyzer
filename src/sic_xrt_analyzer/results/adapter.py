"""Read-only legacy AnalysisResult conversion; never group candidates or create defects."""

from dataclasses import asdict
from pathlib import Path

from sic_xrt_analyzer.analysis.contracts import AnalysisResult, GeometryKind

from .contracts import (
    AnalysisProject,
    AnalysisRunRecord,
    CandidateObservation,
    FileIdentity,
    ImageSourceRecord,
    ModelPrediction,
    ModelProvenance,
)
from .geometry import DefectGeometry, DefectGeometryKind, GeometrySource
from .validation import stable_id


def import_legacy_result(
    project: AnalysisProject,
    result: AnalysisResult,
    *,
    model_manifest=None,
    source_id=None,
):
    if not isinstance(project, AnalysisProject) or not isinstance(
        result, AnalysisResult
    ):
        raise TypeError("Immutable project and legacy result required")
    identity, meta = result.source_identity, result.request.source.metadata
    fingerprint = f"{identity.canonical_path}|{identity.file_size}|{identity.mtime_ns}|{meta.width}|{meta.height}|{meta.dtype}|{meta.bit_depth}|{meta.channels}|{meta.page_count}"
    source_id = source_id or stable_id(project.project_id, "source:" + fingerprint)
    source = next((s for s in project.image_sources if s.source_id == source_id), None)
    if source:
        if (
            source.width,
            source.height,
            source.dtype,
            source.bit_depth,
            source.channels,
            source.page_count,
            source.file_identity,
        ) != (
            meta.width,
            meta.height,
            meta.dtype,
            meta.bit_depth,
            meta.channels,
            meta.page_count,
            FileIdentity(
                identity.canonical_path, identity.file_size, identity.mtime_ns
            ),
        ):
            raise ValueError("Explicit source ID does not match the original snapshot")
    else:
        source = ImageSourceRecord(
            source_id,
            Path(identity.canonical_path).name,
            identity.canonical_path,
            meta.width,
            meta.height,
            meta.dtype,
            meta.bit_depth,
            meta.channels,
            meta.page_count,
            FileIdentity(
                identity.canonical_path, identity.file_size, identity.mtime_ns
            ),
            acquisition_metadata={"format": meta.format},
        )
    run_id = stable_id(project.project_id, "run:" + result.analysis_id)
    provenance_id = stable_id(run_id, "model")
    manifest = dict(model_manifest or {})
    model_hash = result.summary.get("model_sha256")
    if manifest:
        if manifest.get("bundle_id", result.model_id) != result.model_id:
            raise ValueError("Manifest belongs to a different model")
        manifest_hash = manifest.get("model_sha256")
        if (
            model_hash is not None
            and manifest_hash is not None
            and manifest_hash != model_hash
        ):
            raise ValueError("Manifest hash differs from recorded result")
        if (
            manifest_hash is not None
            and len(result.model_version) == 64
            and manifest_hash != result.model_version
        ):
            raise ValueError("Manifest changes the recorded model version")
        model_hash = model_hash or manifest_hash
    provenance = ModelProvenance(
        provenance_id,
        result.model_id,
        result.model_version,
        result.analysis_id,
        model_hash,
        manifest.get("input", {}),
        manifest.get("output", {}),
        manifest.get("training_dataset_version"),
        manifest,
    )
    mode = result.summary.get("point_mode", result.parameters.get("point_mode"))
    run = AnalysisRunRecord(
        run_id,
        project.project_id,
        source_id,
        result.request.page_index,
        result.scope,
        result.roi,
        result.model_id,
        result.model_version,
        model_hash,
        provenance_id,
        mode,
        {
            k: v
            for k, v in result.parameters.items()
            if k
            in (
                "point_mode",
                "proposal_threshold",
                "max_candidates",
                "points",
                "coordinates_sha256",
                "coordinates_path",
                "min_distance",
            )
        },
        {
            k: v
            for k, v in result.parameters.items()
            if k in ("score_threshold", "batch_size")
        },
        result.started_at,
        result.completed_at,
        result.status,
        result.analysis_id,
        asdict(identity),
        result.parameters,
        result.summary,
        result.preprocessing,
        asdict(result.error) if result.error else None,
        result.duration,
        result.contract_version,
    )
    observations, predictions, geometries = [], [], []
    origin = (
        GeometrySource.RULE_BASED
        if mode == "contrast_proposals"
        else GeometrySource.IMPORTED
        if mode == "provided_coordinates"
        else GeometrySource.UNKNOWN
    )
    for detection in result.detections:
        observation_id = stable_id(run_id, "candidate:" + detection.id)
        geometry_id = stable_id(observation_id, "geometry")
        g = detection.geometry
        kind = (
            DefectGeometryKind.MASK_REFERENCE
            if g.kind == GeometryKind.MASK
            else DefectGeometryKind(g.kind.value)
        )
        geometry = DefectGeometry(
            geometry_id,
            source_id,
            result.request.page_index,
            kind,
            origin,
            g.points,
            g.bbox,
            g.mask_reference,
            g.mask_encoding,
        )
        x, y = g.points[0] if g.kind == GeometryKind.POINT else (None, None)
        scores = tuple(detection.metadata.get("scores", ()))
        observation = CandidateObservation(
            observation_id,
            run_id,
            detection.id,
            detection.metadata.get("point_id"),
            x,
            y,
            result.request.page_index,
            detection.class_name,
            scores,
            detection.confidence,
            detection.metadata.get("low_score"),
            mode,
            geometry_id,
            metadata=detection.metadata,
            source_class_id=detection.class_id,
        )
        prediction = ModelPrediction(
            stable_id(observation_id, "prediction"),
            observation_id,
            provenance_id,
            detection.class_name,
            scores,
            detection.confidence,
            tuple(manifest.get("classes", ())) if scores else (),
            manifest.get("output", {}).get("meaning", "UNSPECIFIED"),
        )
        observations.append(observation)
        predictions.append(prediction)
        geometries.append(geometry)
    existing = next((r for r in project.analysis_runs if r.run_id == run_id), None)
    if existing is not None:
        old_obs = tuple(o for o in project.observations if o.run_id == run_id)
        observation_ids = {o.observation_id for o in old_obs}
        geometry_ids = {o.geometry_id for o in old_obs}
        old_predictions = tuple(
            p for p in project.predictions if p.observation_id in observation_ids
        )
        old_geometries = tuple(
            g for g in project.geometries if g.geometry_id in geometry_ids
        )
        if (
            existing != run
            or old_obs != tuple(observations)
            or old_predictions != tuple(predictions)
            or old_geometries != tuple(geometries)
            or provenance not in project.model_provenance
        ):
            raise ValueError(
                "Repeated legacy run ID contains changed results/provenance"
            )
        return project
    return project.evolve(
        image_sources=project.image_sources
        + (() if source in project.image_sources else (source,)),
        analysis_runs=project.analysis_runs + (run,),
        model_provenance=project.model_provenance + (provenance,),
        observations=project.observations + tuple(observations),
        predictions=project.predictions + tuple(predictions),
        geometries=project.geometries + tuple(geometries),
    )
