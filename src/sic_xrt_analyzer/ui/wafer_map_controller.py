"""Local placement drafts, async publication, source-safe viewer navigation."""

import copy
import math
from threading import Event
from uuid import uuid4

import numpy as np
from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from sic_xrt_analyzer.analysis.contracts import utc_now
from sic_xrt_analyzer.results.persistence import ProjectStore
from sic_xrt_analyzer.results.sources import verify_content_hash
from sic_xrt_analyzer.wafer_map import assets
from sic_xrt_analyzer.wafer_map.mapping import (
    calibration,
    compose,
    footprint,
    inverse,
    layout,
    points,
)
from sic_xrt_analyzer.wafer_map.scene import Scene

from .latest_reader import LatestReader


class WaferMapController(QObject):
    changed = Signal()
    workspaceRequested = Signal(int)

    def __init__(self, bridge):
        super().__init__(bridge)
        self.bridge = bridge
        self.projects = bridge.project_controller
        self.reader = LatestReader(self)
        self.reader.ready.connect(self._ready)
        self.scene = Scene()
        self.token = Event()
        self.callback = None
        self.project = None
        self.asset = None
        self.saved = None
        self.ref = None
        self.frame = {}
        self.error = ""
        self.message = "프로젝트 JPG를 선택하여 임시 배치하세요."
        self.busy = False
        self.job = ""
        self.dirty = False
        self.selected = ""
        self.selected_target = None
        self.pending_target = None
        self.centre = [0.0, 0.0]
        self.zoom = 1.0
        self.width = 800.0
        self.height = 550.0
        self.revision = 0
        self.undo_stack = []
        self.history = []
        self.active = False
        self.moving = False
        self.focus_row = None
        self.focus_timer = QTimer(self)
        self.focus_timer.setSingleShot(True)
        self.focus_timer.timeout.connect(self._focus_target)
        self.projects.changed.connect(self._project_changed)
        self.bridge.imageOpened.connect(self._image_opened)

    def resetProject(self):
        self.focus_timer.stop()
        self.focus_row = None
        self.cancel()
        self.project = None
        self.asset = self.saved = None
        self.ref = None
        self.selected = ""
        self.selected_target = None
        self.pending_target = None
        self.frame = {}
        self.undo_stack = []
        self.history = []
        self.dirty = False
        self.scene = Scene()
        self.bridge.provider.wafer_images = {}

    def _project_changed(self):
        p = self.projects.project
        if p is self.project:
            return
        if self.callback and self.callback[0] is not p:
            self.cancel()
        first = self.project is None or not p or p.project_id != self.project.project_id
        self.project = p
        if not p:
            self.resetProject()
            self.changed.emit()
            return
        ref = assets.active_reference(p)
        if first or ref != self.ref:
            self.ref = ref
            try:
                self.history = assets.chain(self.projects.path, ref, p) if ref else []
                self.asset = copy.deepcopy(
                    self.history[0][1] if self.history else assets.blank(p)
                )
                self.saved = copy.deepcopy(self.asset)
                self.dirty = False
                self.undo_stack = []
                self.frame = {}
                self.selected_target = None
            except (OSError, ValueError, KeyError) as e:
                self.error = str(e)
                self.asset = None
        if self.asset:
            for s in p.image_sources:
                if (
                    s.acquisition_metadata.get("format") == "JPEG"
                    and s.source_id not in self.asset["runs"]
                ):
                    runs = [
                        r
                        for r in p.analysis_runs
                        if r.source_id == s.source_id
                        and r.run_status.value == "COMPLETED"
                    ]
                    self.asset["runs"][s.source_id] = runs[-1].run_id if runs else ""
            if self.selected not in {s.source_id for s in p.image_sources}:
                self.selected = ""
            if self.active:
                self.requestFrame(self.width, self.height)
        self.changed.emit()

    def _start(self, job, work, callback):
        self.token.set()
        self.reader.invalidate()
        self.token = Event()
        token = self.token
        self.callback = (self.projects.project, callback)
        self.busy = True
        self.job = job
        self.error = ""
        self.reader.submit(lambda: work(token.is_set))
        self.changed.emit()

    def _ready(self, value, error):
        callback = self.callback
        self.callback = None
        self.busy = False
        self.job = ""
        if not callback or callback[0] is not self.projects.project:
            return
        if error:
            self.error = error
        else:
            try:
                callback[1](value)
            except (ValueError, OSError, KeyError) as e:
                self.error = str(e)
        self.changed.emit()

    @Slot()
    def cancel(self):
        self.token.set()
        self.reader.invalidate()
        self.callback = None
        self.busy = False
        self.job = ""
        self.changed.emit()

    @Slot(bool)
    def activate(self, value):
        self.active = value
        if value:
            self._project_changed()
            self.requestFrame(self.width, self.height)
        elif self.job == "render":
            self.cancel()

    @Slot(float, float)
    def requestFrame(self, width, height):
        if self.job == "save" or not self.asset or not self.project or not self.active:
            return
        self.width = max(1, min(3840, width))
        self.height = max(1, min(2160, height))
        p = self.project
        a = copy.deepcopy(self.asset)
        centre = list(self.centre)
        zoom = self.zoom
        w, h = self.width, self.height

        scene = self.scene

        def work(cancelled):
            return scene.render(p, a, centre, zoom, w, h, cancelled)

        def publish(frame):
            self.frame = frame
            self.bridge.provider.wafer_images = frame.pop("images")
            self.revision += 1
            if frame["errors"]:
                self.message = " · ".join(frame["errors"])

        self._start("render", work, publish)

    def _edit(self):
        if self.job == "save":
            raise ValueError("배치 저장 중입니다")
        self.undo_stack.append(copy.deepcopy(self.asset))
        self.undo_stack = self.undo_stack[-32:]
        self.dirty = True

    def _changed(self):
        self.selected_target = None
        self.changed.emit()
        self.requestFrame(self.width, self.height)

    @Slot(str)
    def select(self, sid):
        if self.project and any(s.source_id == sid for s in self.project.image_sources):
            self.selected = sid
            self.selected_target = None
            self.changed.emit()

    @Slot(str)
    def selectGroup(self, gid):
        if self.asset and gid in {g["id"] for g in self.asset["groups"]}:
            self._edit()
            self.asset["selected_group"] = gid
            self._changed()
            self.fit()

    @Slot(str, str, str, str, str, str, str, str, str, str)
    def addGroup(
        self,
        label,
        mode,
        wafer,
        coordinate,
        unit,
        origin,
        axes,
        evidence,
        geometry_text,
        reviewer,
    ):
        if not self.asset:
            return
        try:
            geo = None
            if geometry_text.strip():
                vals = [float(x) for x in geometry_text.replace(",", " ").split()]
                if len(vals) != 3:
                    raise ValueError("외곽은 중심 X Y 반경 3개 값입니다")
                geo = {
                    "centre": vals[:2],
                    "radius": vals[2],
                    "evidence": evidence,
                    "reviewer": reviewer,
                }
            g = {
                "id": str(uuid4()),
                "label": label.strip(),
                "mode": mode,
                "wafer_id": wafer.strip() if mode == "PHYSICAL" else None,
                "coordinate_system": coordinate.strip()
                if mode == "PHYSICAL"
                else "RELATIVE_LAYOUT",
                "unit": unit if mode == "PHYSICAL" else None,
                "origin": origin.strip() or "사용자 상대 원점",
                "axes": axes if mode == "PHYSICAL" else "X_RIGHT_Y_DOWN",
                "evidence": evidence.strip(),
                "geometry": geo,
            }
            test = copy.deepcopy(self.asset)
            test["groups"].append(g)
            test["selected_group"] = g["id"]
            test["revision"] = max(1, test["revision"])
            assets.validate(test, self.project)
            self._edit()
            self.asset["groups"].append(g)
            self.asset["selected_group"] = g["id"]
            self._changed()
        except (ValueError, KeyError) as e:
            self.error = str(e)
            self.changed.emit()

    def selectedPlacement(self):
        return (
            next(
                (
                    p
                    for p in self.asset["placements"]
                    if p["source_id"] == self.selected
                ),
                None,
            )
            if self.asset
            else None
        )

    @Slot(float, float, float, float, float)
    def place(self, x, y, rotation, sx, sy):
        if not self.asset:
            return
        try:
            s = next(
                s for s in self.project.image_sources if s.source_id == self.selected
            )
            if s.acquisition_metadata.get("format") != "JPEG":
                raise ValueError(
                    "TIFF는 스택·3D 원본이며 지도 JPG 배치에 사용하지 않습니다"
                )
            group = next(
                g
                for g in self.asset["groups"]
                if g["id"] == self.asset["selected_group"]
            )
            m = layout(x, y, rotation, sx, sy, group["axes"])
            self._edit()
            old = self.selectedPlacement()
            self.asset["placements"] = [
                p for p in self.asset["placements"] if p["source_id"] != s.source_id
            ]
            self.asset["placements"].append(
                {
                    "placement_id": str(uuid4()),
                    "source_id": s.source_id,
                    "source_sha256": s.content_hash.value
                    if s.content_hash
                    else "0" * 64,
                    "size": [s.width, s.height],
                    "group_id": group["id"],
                    "matrix": m,
                    "status": "UNVERIFIED",
                    "evidence": {
                        "origin": "manual_layout",
                        "previous_placement_id": old["placement_id"] if old else None,
                    },
                    "created_at": utc_now().isoformat(),
                    "editor": "",
                }
            )
            self._changed()
        except (ValueError, StopIteration) as e:
            self.error = str(e)
            self.changed.emit()

    @Slot()
    def beginMove(self):
        if self.selectedPlacement() and self.job != "save":
            self._edit()
            self.moving = True

    @Slot()
    def endMove(self):
        self.moving = False

    @Slot(float, float)
    def move(self, dx, dy):
        p = self.selectedPlacement()
        if not p or self.job == "save":
            return
        if not self.moving:
            self._edit()
        p["matrix"][0][2] = float(p["matrix"][0][2] + dx / self.zoom)
        p["matrix"][1][2] = float(
            p["matrix"][1][2] + dy * self.yDirection() / self.zoom
        )
        p["status"] = "UNVERIFIED"
        p["evidence"] = {"origin": "manual_drag"}
        p["placement_id"] = str(uuid4())
        p["created_at"] = utc_now().isoformat()
        self.dirty = True
        self._changed()

    @Slot()
    def resetPlacement(self):
        if not self.asset or not self.selected or self.job == "save":
            return
        self._edit()
        self.asset["placements"] = [
            p for p in self.asset["placements"] if p["source_id"] != self.selected
        ]
        previous = next(
            (
                p
                for p in (self.saved or {}).get("placements", [])
                if p["source_id"] == self.selected
            ),
            None,
        )
        if previous:
            self.asset["placements"].append(copy.deepcopy(previous))
        self._changed()

    @Slot()
    def unplace(self):
        if self.selectedPlacement():
            self._edit()
            self.asset["placements"] = [
                p for p in self.asset["placements"] if p["source_id"] != self.selected
            ]
            self._changed()

    @Slot()
    def undo(self):
        if self.undo_stack and self.job != "save":
            self.asset = self.undo_stack.pop()
            self.dirty = self.asset != self.saved
            self._changed()

    @Slot()
    def discard(self):
        if self.saved and self.job != "save":
            self.asset = copy.deepcopy(self.saved)
            self.undo_stack = []
            self.dirty = False
            self._changed()

    @Slot(str, str, str, float)
    def verifyPlacement(self, source, reviewer, landmarks, tolerance):
        p = self.selectedPlacement()
        if not p:
            return
        try:
            pairs = []
            for line in landmarks.strip().splitlines():
                v = [float(x) for x in line.replace(",", " ").split()]
                if len(v) != 4:
                    raise ValueError("각 기준점은 이미지 X Y 지도 X Y 4개 값입니다")
                pairs.append({"image": v[:2], "map": v[2:]})
            g = next(g for g in self.asset["groups"] if g["id"] == p["group_id"])
            e = {
                "source": source.strip(),
                "reviewer": reviewer.strip(),
                "pixel_spacing": np.linalg.norm(
                    np.asarray(p["matrix"])[:2, :2], axis=0
                ).tolist(),
                "landmarks": pairs,
                "tolerance": tolerance,
                "registration_reference": None,
                "same_target_evidence": "",
            }
            calibration(p["matrix"], p["size"], g, e)
            self._edit()
            p = self.selectedPlacement()
            p["status"] = "VERIFIED"
            p["evidence"] = e
            p["editor"] = reviewer.strip()
            p["placement_id"] = str(uuid4())
            p["created_at"] = utc_now().isoformat()
            self._changed()
        except (ValueError, KeyError) as e:
            self.error = str(e)
            self.changed.emit()

    @Slot(str, str)
    def composeRegistration(self, reference, same_target):
        try:
            from sic_xrt_analyzer.registration import assets as registrations

            r = registrations.read(self.projects.path, reference, self.project)
            target = next(
                p for p in self.asset["placements"] if p["source_id"] == r["target_id"]
            )
            group = next(
                g for g in self.asset["groups"] if g["id"] == target["group_id"]
            )
            s = next(
                s for s in self.project.image_sources if s.source_id == r["source_id"]
            )
            t = next(
                s for s in self.project.image_sources if s.source_id == r["target_id"]
            )
            m = compose(r, target, group, s, t, same_target)
            self._edit()
            self.selected = s.source_id
            self.asset["selected_group"] = group["id"]
            self.asset["placements"] = [
                p for p in self.asset["placements"] if p["source_id"] != s.source_id
            ]
            self.asset["placements"].append(
                {
                    "placement_id": str(uuid4()),
                    "source_id": s.source_id,
                    "source_sha256": s.content_hash.value,
                    "size": [s.width, s.height],
                    "group_id": group["id"],
                    "matrix": m,
                    "status": "UNVERIFIED",
                    "evidence": {
                        "registration_reference": reference,
                        "same_target_evidence": same_target,
                        "target_placement_id": target["placement_id"],
                    },
                    "created_at": utc_now().isoformat(),
                    "editor": "",
                }
            )
            self.message = "합성 제안 · 원본 기준점 독립 검증 전 UNVERIFIED"
            self._changed()
        except (ValueError, OSError, StopIteration, KeyError) as e:
            self.error = str(e)
            self.changed.emit()

    @Slot(str, str)
    def setRun(self, sid, rid):
        if self.asset and (
            not rid
            or any(
                r.run_id == rid
                and r.source_id == sid
                and r.run_status.value == "COMPLETED"
                for r in self.project.analysis_runs
            )
        ):
            self._edit()
            self.asset["runs"][sid] = rid
            self._changed()

    @Slot(str, bool)
    def setLayer(self, layer, value):
        if self.asset and layer in assets.LAYERS:
            self._edit()
            self.asset["layers"][layer] = value
            self._changed()

    @Slot(str)
    def restoreHistory(self, reference):
        if reference in {r for r, _ in self.history}:
            self._edit()
            self.asset = copy.deepcopy(
                next(a for r, a in self.history if r == reference)
            )
            self.dirty = True
            self._changed()

    @Slot(str)
    def save(self, editor):
        if not self.project or not self.asset or self.job == "save":
            return
        if not self.projects.path:
            self.error = "프로젝트를 먼저 디스크에 저장하세요"
            self.changed.emit()
            return
        if self.projects.busy or self.projects._analysis_busy():
            self.error = "다른 작업을 완료한 뒤 저장하세요"
            self.changed.emit()
            return
        if not editor.strip():
            self.error = "배치 편집자 식별값을 입력하세요"
            self.changed.emit()
            return
        p = self.project
        a = copy.deepcopy(self.asset)
        path = self.projects.path
        ref = self.ref
        expected = (
            self.projects.saved_snapshot.revision
            if self.projects.saved_snapshot
            else None
        )
        next_revision = self.saved["revision"] + 1 if ref else 1
        if not any(
            s.acquisition_metadata.get("format") == "JPEG" for s in p.image_sources
        ):
            self.error = "배치 자산을 연결할 프로젝트 JPG가 필요합니다"
            self.changed.emit()
            return

        def work(cancelled):
            verified = {}
            for place in a["placements"]:
                if cancelled():
                    raise InterruptedError("배치 저장 취소")
                s = next(
                    s for s in p.image_sources if s.source_id == place["source_id"]
                )
                v = verify_content_hash(s, cancelled=cancelled)
                verified[s.source_id] = v
                place["source_sha256"] = v.content_hash.value
            q = p.evolve(
                image_sources=tuple(
                    verified.get(s.source_id, s) for s in p.image_sources
                )
            )
            a.update(
                revision_id=str(uuid4()),
                revision=next_revision,
                parent_reference=ref,
                created_at=utc_now().isoformat(),
                editor=editor.strip(),
            )
            assets.validate(a, q)
            if cancelled():
                raise InterruptedError("배치 저장 취소")
            q = assets.append(q, a, path)
            ProjectStore().save(path, q, expected_revision=expected)
            return q, a, assets.reference(a)

        def publish(value):
            q, a, newref = value
            self.asset = copy.deepcopy(a)
            self.saved = copy.deepcopy(a)
            self.ref = newref
            self.dirty = False
            self.undo_stack = []
            self.projects.project = self.projects.saved_snapshot = q
            self.projects.dirty = False
            self.projects.changed.emit()
            self.history = assets.chain(path, newref, q)
            self.message = "배치 revision 저장 완료"
            self.requestFrame(self.width, self.height)

        self._start("save", work, publish)

    @Slot()
    def fit(self):
        if not self.asset:
            return
        bounds = [
            xy
            for p in self.asset["placements"]
            if p["group_id"] == self.asset["selected_group"]
            for xy in footprint(p["matrix"], *p["size"])
        ]
        if bounds:
            v = np.asarray(bounds)
            lo = v.min(0)
            hi = v.max(0)
            self.centre = ((lo + hi) / 2).tolist()
            self.zoom = max(
                1e-6,
                min(
                    1e6,
                    min(
                        self.width / (hi[0] - lo[0] + 1e-8),
                        self.height / (hi[1] - lo[1] + 1e-8),
                    )
                    * 0.85,
                ),
            )
        else:
            self.centre = [0.0, 0.0]
            self.zoom = 1.0
        self.requestFrame(self.width, self.height)

    def yDirection(self):
        group = next(
            (
                g
                for g in (self.asset or {}).get("groups", [])
                if g["id"] == self.asset["selected_group"]
            ),
            {},
        )
        return -1 if group.get("axes") == "X_RIGHT_Y_UP" else 1

    @Slot(float, float)
    def pan(self, dx, dy):
        self.centre = (
            np.asarray(self.centre)
            - np.asarray([dx, dy * self.yDirection()]) / self.zoom
        ).tolist()
        self.requestFrame(self.width, self.height)

    @Slot(float, float, float)
    def zoomAt(self, factor, x, y):
        if not math.isfinite(factor) or factor <= 0:
            return
        old = self.zoom
        self.zoom = max(1e-6, min(1e6, old * factor))
        offset = (
            np.asarray([x, y]) - np.asarray([self.width, self.height]) / 2
        ) * np.asarray([1, self.yDirection()])
        anchor = np.asarray(self.centre) + offset / old
        self.centre = (anchor - offset / self.zoom).tolist()
        self.requestFrame(self.width, self.height)

    @Slot(float, float, result=bool)
    def hit(self, x, y):
        xy = np.asarray([x, y])
        for row in reversed(self.frame.get("paths", [])):
            if any(
                np.min(np.linalg.norm(np.asarray(p) - xy, axis=1)) <= 7
                for p in row["paths"]
            ):
                self.selected = row["source_id"]
                self.selected_target = row
                self.changed.emit()
                return True
        for t in reversed(self.frame.get("tiles", [])):
            p = points(inverse(t["matrix"]), [[x, y]])[0]
            if -0.5 <= p[0] < t["width"] - 0.5 and -0.5 <= p[1] < t["height"] - 0.5:
                self.selected = t["source_id"]
                self.selected_target = None
                self.changed.emit()
                return True
        return False

    @Slot(bool)
    def openSelected(self, result):
        if not self.selected:
            return
        if self.bridge.review_controller.pending:
            self.error = "작성 중인 검수를 먼저 기록하거나 취소하세요"
            self.changed.emit()
            return
        rid = self.asset["runs"].get(self.selected, "") if result else ""
        row = self.selected_target if result else None
        if row:
            rid = row["run_id"] or rid
        self.pending_target = (self.project.project_id, self.selected, rid, row)
        self.projects.selectSource(self.selected, rid)
        self.workspaceRequested.emit(0)

    def _image_opened(self, result):
        pending = self.pending_target
        if not pending:
            return
        self.pending_target = None
        if (
            not result.get("ok")
            or not self.project
            or pending[:3]
            != (
                self.project.project_id,
                self.projects.selected_source,
                self.projects.selected_run,
            )
        ):
            return
        row = pending[3]
        if row:
            self.focus_row = row
            self.focus_timer.start(0)

    def _focus_target(self):
        row = self.focus_row
        self.focus_row = None
        if (
            not row
            or not self.project
            or self.projects.selected_source != row["source_id"]
            or (row["run_id"] and self.projects.selected_run != row["run_id"])
        ):
            return
        self.bridge.review_controller.enter()
        self.bridge.review_controller.select(row["target_type"], row["target_id"])

    @Slot(str)
    def compare(self, other):
        if not self.project or not self.selected or other == self.selected:
            return
        from sic_xrt_analyzer.registration import assets as registrations

        rel = next(
            (
                r
                for r in reversed(self.project.image_relationships)
                if {r.source_image_id, r.target_image_id} == {self.selected, other}
                and r.transform_reference
                and r.transform_reference.startswith(registrations.PREFIX)
            ),
            None,
        )
        c = self.bridge.registration_controller
        if rel:
            c.selectAttempt(rel.registration_id)
        else:
            c.select(self.selected, other)
        self.workspaceRequested.emit(2)

    @Property("QVariantMap", notify=changed)
    def state(self):
        if not self.asset or not self.project:
            return {
                "available": False,
                "busy": self.busy,
                "error": self.error,
                "tiles": [],
                "paths": [],
                "groups": [],
                "sources": [],
                "runs": [],
                "layers": {},
                "summary": {},
                "history": [],
                "placement": {},
                "target": {},
                "registrations": [],
                "params": [0, 0, 0, 0.025, 0.025],
            }
        placed = {p["source_id"]: p for p in self.asset["placements"]}
        sources = []
        for s in self.project.image_sources:
            sources.append(
                {
                    "id": s.source_id,
                    "name": s.display_name,
                    "format": s.acquisition_metadata.get("format", "UNKNOWN"),
                    "width": s.width,
                    "height": s.height,
                    "pages": s.page_count,
                    "run_count": sum(
                        r.source_id == s.source_id for r in self.project.analysis_runs
                    ),
                    "placed": s.source_id in placed,
                    "group_id": placed[s.source_id]["group_id"]
                    if s.source_id in placed
                    else "",
                    "status": placed[s.source_id]["status"]
                    if s.source_id in placed
                    else "UNPLACED",
                }
            )
        p = self.selectedPlacement()
        g = next(
            g for g in self.asset["groups"] if g["id"] == self.asset["selected_group"]
        )
        params = [0.0, 0.0, 0.0, 0.025, 0.025]
        if p:
            m = np.asarray(p["matrix"])
            params = [
                float(m[0, 2]),
                float(m[1, 2]),
                math.degrees(math.atan2(m[1, 0], m[0, 0])),
                float(np.linalg.norm(m[:2, 0])),
                float(np.linalg.norm(m[:2, 1])),
            ]
        return {
            "available": True,
            "busy": self.busy,
            "job": self.job,
            "error": self.error,
            "message": self.message,
            "dirty": self.dirty,
            "selected": self.selected,
            "target": {
                k: v for k, v in (self.selected_target or {}).items() if k != "paths"
            },
            "sources": sources,
            "groups": self.asset["groups"],
            "group_id": g["id"],
            "mode": g["mode"],
            "unit": g["unit"] or "relative",
            "group": g,
            "placement": p or {},
            "params": params,
            "runs": [
                {"id": r.run_id, "label": r.scope.value + " · " + r.run_id[:8]}
                for r in self.project.analysis_runs
                if r.source_id == self.selected and r.run_status.value == "COMPLETED"
            ],
            "run_id": self.asset["runs"].get(self.selected, ""),
            "layers": self.asset["layers"],
            "tiles": self.frame.get("tiles", []),
            "paths": self.frame.get("paths", []),
            "summary": self.frame.get("summary", {}),
            "review_summary": self.frame.get("review_summary", {}),
            "omitted": self.frame.get("omitted_display_points", 0),
            "outline": self.frame.get("outline"),
            "metrics": self.frame.get("metrics", {}),
            "history": [
                {
                    "ref": ref,
                    "label": str(a["revision"])
                    + " · "
                    + a["editor"]
                    + " · "
                    + a["created_at"],
                }
                for ref, a in self.history
            ],
            "revision": self.revision,
            "zoom": self.zoom,
            "centre": self.centre,
            "registrations": [
                {
                    "ref": r.transform_reference,
                    "label": r.registration_id[:8]
                    + " · "
                    + r.verification_status.value,
                }
                for r in self.project.image_relationships
                if r.transform_reference
                and r.transform_reference.startswith("assets/registrations/")
                and r.source_image_id == self.selected
            ],
        }

    def shutdown(self):
        self.focus_timer.stop()
        self.focus_row = None
        self.cancel()
        self.reader.shutdown()
        self.scene.clear()
