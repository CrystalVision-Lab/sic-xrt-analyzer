"""Atomic metadata-only local storage. Source images and external assets are never copied."""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .serialization import MAX_PROJECT_BYTES, dumps, loads
from .validation import asset_reference


class ProjectStore:
    def load(self, path):
        path = Path(path)
        with path.open("rb") as stream:
            data = stream.read(MAX_PROJECT_BYTES + 1)
        project = loads(data)
        from sic_xrt_analyzer.registration.assets import validate_project_assets
        validate_project_assets(path, project)
        from sic_xrt_analyzer.wafer_map.assets import (
            validate_project_assets as validate_maps,
        )
        validate_maps(path, project)
        from sic_xrt_analyzer.stack3d.assets import validate_project_assets as validate_3d
        validate_3d(path, project)
        return project  # Metadata/assets only; never reads source pixels or runs inference.

    def save(self, path, project, *, expected_revision=None):
        path = Path(path).absolute()
        if path.suffix.lower() != ".json":
            raise ValueError("Project manifests must be JSON files")
        original_paths = {
            Path(s.source_reference).resolve() for s in project.image_sources
        }
        original_paths.update(
            Path(s.file_identity.canonical_path).resolve()
            for s in project.image_sources
        )
        lock_path = path.with_name(path.name + ".lock")
        if path.resolve() in original_paths or lock_path.resolve() in original_paths:
            raise ValueError("Cannot overwrite an original source with a project")
        if path.is_symlink() or lock_path.is_symlink():
            raise ValueError("Project/lock paths cannot be symlinks")
        from sic_xrt_analyzer.registration.assets import validate_project_assets
        validate_project_assets(path, project)
        from sic_xrt_analyzer.wafer_map.assets import (
            validate_project_assets as validate_maps,
        )
        validate_maps(path, project)
        from sic_xrt_analyzer.stack3d.assets import validate_project_assets as validate_3d
        validate_3d(path, project)
        encoded = dumps(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _write_lock(lock_path):
            if path.exists():
                existing = self.load(path)
                if existing.project_id != project.project_id:
                    raise ValueError("Cannot replace a different project")
                if existing == project:
                    if (
                        expected_revision is not None
                        and existing.revision != expected_revision
                    ):
                        raise ValueError("Project revision conflict")
                    return path
                if expected_revision is None or existing.revision != expected_revision:
                    raise ValueError(
                        "Project revision conflict: explicit expected_revision required"
                    )
                if project.revision <= existing.revision:
                    raise ValueError("Cannot overwrite newer project history")
                from sic_xrt_analyzer.wafer_map.assets import chain, check_history
                oldref,newref=check_history(existing,project)
                if oldref and oldref!=newref and oldref not in {ref for ref,_ in chain(path,newref,project)[1:]}:
                    raise ValueError("Cannot rewrite wafer map history")
                from sic_xrt_analyzer.stack3d.assets import check_history as check_3d_history
                check_3d_history(path, existing, project)
                new_sources = {s.source_id: s for s in project.image_sources}
                if any(s.source_id not in new_sources for s in existing.image_sources):
                    raise ValueError("Cannot delete prior image sources")
                for name, key in (
                    ("analysis_runs", "run_id"),
                    ("observations", "observation_id"),
                    ("predictions", "prediction_id"),
                    ("geometries", "geometry_id"),
                    ("review_events", "review_id"),
                    ("model_provenance", "provenance_id"),
                    ("defect_instances", "instance_id"),
                    ("image_relationships", "relationship_id"),
                ):
                    new_rows = {
                        getattr(row, key): row for row in getattr(project, name)
                    }
                    if any(
                        row != new_rows.get(getattr(row, key))
                        for row in getattr(existing, name)
                    ):
                        raise ValueError(f"Cannot delete or rewrite {name} history")
            elif expected_revision is not None:
                raise ValueError("Expected project revision does not exist")
            temporary = None
            try:
                descriptor, temporary = tempfile.mkstemp(
                    prefix="." + path.name + ".", suffix=".tmp", dir=path.parent
                )
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                if self.load(temporary) != project:
                    raise ValueError("Temporary project verification failed")
                os.replace(temporary, path)
                temporary = None
            finally:
                if temporary is not None:
                    Path(temporary).unlink(missing_ok=True)
        return path

    def resolve_asset(self, project_path, reference):
        asset_reference(reference)
        root = Path(project_path).resolve().parent
        candidate = (root / reference).resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("Asset symlink escapes project directory")
        if not candidate.is_file():
            raise FileNotFoundError("Referenced asset is unavailable")
        return candidate  # Caller chooses an explicit safe decoder; this service never executes/loads assets.


@contextmanager
def _write_lock(path):
    # OS locks are released on process exit; the harmless sidecar may remain.
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
