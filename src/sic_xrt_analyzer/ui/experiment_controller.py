"""Explicit, source-bound experimental geometry import; no detector or inference runs."""
import hashlib
from dataclasses import asdict

from PySide6.QtCore import Property, QObject, Signal, Slot

from .latest_reader import LatestReader


def same_source(source, manifest):
    source.validate_identity()
    if asdict(source.identity) != manifest["source_identity"]:
        raise ValueError("현재 원본 파일·페이지가 실험 번들과 일치하지 않습니다.")
    for key in ("width", "height", "dtype", "bit_depth", "channels", "page_count", "format"):
        if getattr(source.metadata, key) != manifest["source_metadata"][key]:
            raise ValueError("현재 원본 해상도·자료형이 실험 번들과 일치하지 않습니다.")


def present_bundle(folder, project, manifest):
    runs = {r.run_id: r for r in project.analysis_runs}
    observations = {o.observation_id: o for o in project.observations}
    geometries = {g.geometry_id: g for g in project.geometries}
    rows = []
    for number, proposal in enumerate(manifest["proposals"], 1):
        g = geometries[proposal["geometry_id"]]
        mask = geometries[proposal["mask_geometry_id"]]
        if g.source_id != manifest["source_id"] or g.page_index != manifest["source_identity"]["page_index"]:
            raise ValueError("구조의 원본·페이지 참조가 일치하지 않습니다.")
        if g.kind.value not in ("POLYLINE", "BRANCHED_GRAPH"):
            raise ValueError("지원하지 않는 실험 구조 Geometry입니다.")
        points = g.all_points()
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        bounds = [min(xs), min(ys), max(xs)-min(xs), max(ys)-min(ys)]
        nodes = {n.node_id: n for n in g.nodes}
        paths = [list(g.points)] if g.points else [list(e.points) if e.points else
            [(nodes[e.start_node].x, nodes[e.start_node].y), (nodes[e.end_node].x, nodes[e.end_node].y)] for e in g.edges]
        degrees = {n: 0 for n in nodes}
        for edge in g.edges:
            degrees[edge.start_node] += 1
            degrees[edge.end_node] += 1
        links = [link for link in manifest.get("links", []) if link.get("instance_id") == proposal["instance_id"]]
        # TD02 stores links on proposal rows (older empty bundles have none).
        links = proposal.get("links", links)
        links = [{**link, "x": observations[link["observation_id"]].x, "y": observations[link["observation_id"]].y,
                  "class": observations[link["observation_id"]].assigned_class,
                  "raw_scores": list(observations[link["observation_id"]].raw_scores),
                  "model_version": runs[observations[link["observation_id"]].run_id].model_version} for link in links]
        rows.append({"id": proposal["instance_id"], "number": number, "kind": g.kind.value,
            "bounds": bounds, "paths": paths, "nodes": [{"x": n.x, "y": n.y, "degree": degrees[n.node_id]} for n in g.nodes],
            "length": proposal["length_px"], "junctions": proposal["junction_cluster_count"],
            "flags": proposal["flags"], "links": links, "algorithm": manifest["algorithm"],
            "mask": {"path": str((folder/mask.mask_reference).resolve()), "sha256": manifest["assets"][mask.mask_reference],
                     "bounds": list(mask.bbox)}, "sourceId": manifest["source_id"],
            "page": g.page_index, "ambiguous": "AMBIGUOUS" in str(proposal["flags"]) or any(l["link_status"] == "AMBIGUOUS" for l in links)})
    return rows


class ExperimentController(QObject):
    changed = Signal()
    focusRequested = Signal(float, float, float, float)

    def __init__(self, research):
        super().__init__(research)
        self.research, self.bridge = research, research.bridge
        self.preview = self.preview_error = ""
        self.preview_revision = 0
        self.preview_reader = LatestReader(self)
        self.preview_reader.ready.connect(self._preview_ready)
        self.mask_readers = []
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.source = None
        self.project = self.manifest = None
        self.rows = []
        self.folder = self.error = self.selected_id = ""
        self.loading = False

    def bind_source(self, source):
        identity = source.identity if source else None
        if identity != (self.source.identity if self.source else None):
            self.unload()
        self.source = source

    @Slot(str)
    def load(self, url):
        from .research_controller import local_path
        self.cancel()
        if self.source is None or self.bridge.stack_viewer.initial_loading or self.bridge.stack_viewer.busy:
            self.error = "원본 TIFF/JPG를 먼저 여세요."
            self.changed.emit()
            return
        source, folder = self.source, local_path(url).resolve()
        self.loading, self.error = True, ""
        self.changed.emit()
        def read():
            from sic_xrt_analyzer.results.bpd_experiment import load_experiment_bundle
            project, manifest = load_experiment_bundle(folder)
            same_source(source, manifest)
            # Verify the original ROI bytes as well as exact path/stat/header/page.
            roi = manifest["roi"]
            pixels = source.read_region(roi["x"], roi["y"], roi["width"], roi["height"])
            if hashlib.sha256(pixels.tobytes()).hexdigest() != manifest["roi_sha256"]:
                raise ValueError("원본 ROI 픽셀 해시가 실험 번들과 일치하지 않습니다.")
            record = next(s for s in project.image_sources if s.source_id == manifest["source_id"])
            if record.content_hash:
                with open(source.path, "rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != record.content_hash.value:
                        raise ValueError("원본 전체 파일 SHA가 프로젝트와 일치하지 않습니다.")
            rows = present_bundle(folder, project, manifest)
            source.validate_identity()
            return source.identity, folder, project, manifest, rows
        self.reader.submit(read)

    def _ready(self, payload, error):
        self.loading = False
        if error:
            self.error = "실험 영역을 불러오지 못했습니다: " + error
        elif self.source and payload[0] == self.source.identity:
            try:
                same_source(self.source, payload[3])
            except ValueError as exc:
                self.error = str(exc)
            else:
                # Commit only a fully validated snapshot; failed import preserves prior selection.
                self.clear_selection()
                self.folder, self.project, self.manifest, self.rows = str(payload[1]), payload[2], payload[3], payload[4]
                self.error = ""
        self.research.changed.emit()
        self.changed.emit()

    @Slot()
    def cancel(self):
        self.reader.invalidate()
        self.loading = False
        self.changed.emit()

    def clear_selection(self):
        self.selected_id = ""
        self.preview = self.preview_error = ""
        self.preview_reader.invalidate()
        if self.research.selection_kind == "DEFECT_INSTANCE":
            self.research.selection_kind = ""
            self.research.changed.emit()

    @Slot()
    def unload(self):
        self.cancel()
        self.clear_selection()
        self.project = self.manifest = None
        self.rows = []
        self.folder = self.error = ""
        self.bridge.provider.experiment_image = self.bridge.provider.experiment_image.__class__()
        self.research.changed.emit()
        self.changed.emit()

    def related(self, candidate):
        result = self.bridge.pipeline.result
        if not candidate or result is None:
            return []
        return [row for row in self.rows if any(
            link["source_candidate_id"] == candidate["id"] and link["x"] == candidate["x"]
            and link["y"] == candidate["y"] and link["class"] == candidate["type"]
            and link["raw_scores"] == candidate["scores"] and link["model_version"] == result.model_version
            for link in row["links"])]

    @Slot(str)
    def select(self, ident):
        row = next((r for r in self.rows if r["id"] == ident), None)
        if row is None or self.source is None:
            return
        try:
            same_source(self.source, self.manifest)
        except ValueError as exc:
            self.unload()
            self.error = str(exc)
            self.changed.emit()
            return
        self.research._clear_selection()
        self.research.selection_kind, self.selected_id = "DEFECT_INSTANCE", ident
        self.research.changed.emit()
        self.changed.emit()
        self.focusRequested.emit(*row["bounds"])
        source, ident = self.source, row["id"]
        low, high = self.bridge.stack_viewer.window or (0, 65535)
        self.preview = self.preview_error = ""
        def read():
            from sic_xrt_analyzer.imaging.tiff_stack import render_samples
            source.validate_identity()
            x, y, w, h = row["bounds"]
            x, y = max(0, int(x)-8), max(0, int(y)-8)
            w = min(source.metadata.width-x, max(16, int(w)+17))
            h = min(source.metadata.height-y, max(16, int(h)+17))
            pixels = source.read_region(x, y, w, h)
            image = render_samples(pixels, source, low, high, False).image
            source.validate_identity()
            return ident, image
        self.preview_reader.submit(read)
        self.changed.emit()

    def _preview_ready(self, payload, error):
        if not self.selected_id:
            return
        if error:
            self.preview_error = error
        elif payload[0] == self.selected_id:
            self.bridge.provider.experiment_image = payload[1]
            self.preview_revision += 1
            self.preview = f"image://tiff/experiment?revision={self.preview_revision}"
        self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def state(self):
        selected = next((r for r in self.rows if r["id"] == self.selected_id), {}) if self.research.selection_kind == "DEFECT_INSTANCE" else {}
        return {"loading": self.loading, "error": self.error, "folder": self.folder,
                "rows": self.rows, "total": len(self.rows), "selected": selected,
                "preview": self.preview, "previewError": self.preview_error,
                "status": "자동 구조 제안 · 실제 정확도 미검증",
                "algorithm": self.manifest["algorithm"] if self.manifest else ""}
