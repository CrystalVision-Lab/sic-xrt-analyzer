"""SHA-addressed local TIFF sessions and append-only manual track event revisions."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sic_xrt_analyzer.analysis.contracts import utc_now

PREFIX = "assets/stack-3d/"
KEY = "stack_3d_session_reference"
MAX_BYTES = 8 * 1024**2
MAX_HISTORY = 128
SESSION = "xrt_stack_3d_session/v1"  # legacy, still loaded
SESSION_V2 = "xrt_stack_3d_session/v2"  # v1 + page_track_review reference
TRACK = "xrt_stack_track/v1"
REVIEW_KEY = "page_track_review"


def finite(values):
    import math

    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("Nonfinite coordinates")


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError("3D text field invalid")


def timestamp(value):
    if datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("3D timestamp needs timezone")


def source(project, sid, sha):
    s = next((s for s in project.image_sources if s.source_id == sid), None)
    if (
        not s
        or s.acquisition_metadata.get("format") != "TIFF"
        or s.dtype != "uint16"
        or s.channels != 1
        or not s.content_hash
        or s.content_hash.value != sha
    ):
        raise ValueError("3D TIFF Source ID / SHA / dtype mismatch")
    return s


def active_points(track):
    points = {}
    paused = False
    for event in track["events"]:
        action = event["action"]
        if action == "UPSERT":
            points[event["page_index"]] = event
        elif action == "REMOVE":
            points.pop(event["page_index"], None)
        elif action == "PAUSE":
            paused = True
        elif action == "RESUME":
            paused = False
    return points, paused


def new_track(s, name, reviewer, project_id):
    text(name)
    text(reviewer)
    return {
        "schema": TRACK,
        "project_id": project_id,
        "source_id": s.source_id,
        "source_sha256": s.content_hash.value,
        "track_id": str(uuid4()),
        "name": name,
        "creator": reviewer,
        "created_at": utc_now().isoformat(),
        "revision": 0,
        "events": [],
    }


def event(track, action, page, geometry, reviewer, status="PROPOSED"):
    text(reviewer)
    e = {
        "revision": len(track["events"]) + 1,
        "action": action,
        "page_index": page,
        "geometry": geometry,
        "reviewer": reviewer,
        "status": status,
        "method": "MANUAL",
        "created_at": utc_now().isoformat(),
    }
    track["events"].append(e)
    track["revision"] = len(track["events"])
    return e


def validate_track(t, project):
    if (
        set(t)
        != {
            "schema",
            "project_id",
            "source_id",
            "source_sha256",
            "track_id",
            "name",
            "creator",
            "created_at",
            "revision",
            "events",
        }
        or t["schema"] != TRACK
    ):
        raise ValueError("Unsupported Track schema")
    if t["project_id"] != project.project_id:
        raise ValueError("Different project Track")
    s = source(project, t["source_id"], t["source_sha256"])
    text(t["track_id"])
    text(t["name"])
    text(t["creator"])
    timestamp(t["created_at"])
    if (
        not isinstance(t["events"], list)
        or len(t["events"]) > 2048
        or type(t["revision"]) is not int
        or t["revision"] != len(t["events"])
    ):
        raise ValueError("Track event budget / revision")
    previous = t["created_at"]
    for n, e in enumerate(t["events"], 1):
        if (
            set(e)
            != {
                "revision",
                "action",
                "page_index",
                "geometry",
                "reviewer",
                "status",
                "method",
                "created_at",
            }
            or type(e["revision"]) is not int
            or e["revision"] != n
        ):
            raise ValueError("Track event fields / revision")
        text(e["reviewer"])
        timestamp(e["created_at"])
        if datetime.fromisoformat(e["created_at"]) < datetime.fromisoformat(previous):
            raise ValueError("Track timestamp order")
        previous = e["created_at"]
        if e["method"] != "MANUAL" or e["status"] not in (
            "PROPOSED",
            "REVIEWED",
            "UNCERTAIN",
        ):
            raise ValueError("Track is manual observation, not a confirmed defect")
        if e["action"] not in ("UPSERT", "REMOVE", "PAUSE", "RESUME"):
            raise ValueError("Track action")
        page = e["page_index"]
        if e["action"] in ("UPSERT", "REMOVE"):
            if type(page) is not int or not 0 <= page < s.page_count:
                raise ValueError("Track page out of Source")
        elif page is not None:
            raise ValueError("Pause/resume has no observed page")
        g = e["geometry"]
        if e["action"] == "UPSERT":
            if set(g) != {"type", "coordinates"} or g["type"] not in (
                "POINT",
                "RECTANGLE",
            ):
                raise ValueError("Only explicit point/rectangle Track geometry")
            coords = g["coordinates"]
            finite(coords)
            if g["type"] == "POINT":
                if (
                    len(coords) != 2
                    or not 0 <= coords[0] < s.width
                    or not 0 <= coords[1] < s.height
                ):
                    raise ValueError("Track point outside Source")
            elif (
                len(coords) != 4
                or coords[0] < 0
                or coords[1] < 0
                or min(coords[2:]) <= 0
                or coords[0] + coords[2] > s.width
                or coords[1] + coords[3] > s.height
            ):
                raise ValueError("Track rectangle outside Source")
        elif g is not None:
            raise ValueError("Non-observation geometry forbidden")
    return t


SESSION_KEYS = {
    "schema",
    "project_id",
    "source_id",
    "source_sha256",
    "stack_page_count",
    "original_shape",
    "dtype",
    "byte_order",
    "selection",
    "coordinate_mode",
    "calibration",
    "settings",
    "tracks",
    "revision",
    "session_id",
    "revision_id",
    "parent_reference",
    "created_at",
    "editor_id",
}


def validate_session(a, project):
    if not (
        (a.get("schema") == SESSION and set(a) == SESSION_KEYS)
        or (a.get("schema") == SESSION_V2 and set(a) == SESSION_KEYS | {REVIEW_KEY})
    ):
        raise ValueError("Unsupported session schema")
    if a.get(REVIEW_KEY) is not None:
        reference(a[REVIEW_KEY])
    if a["project_id"] != project.project_id:
        raise ValueError("Different project session")
    s = source(project, a["source_id"], a["source_sha256"])
    if (
        a["stack_page_count"] != s.page_count
        or a["original_shape"] != [s.page_count, s.height, s.width]
        or a["dtype"] != "uint16"
        or a["byte_order"] not in ("<", ">")
    ):
        raise ValueError("Session original metadata mismatch")
    text(a["session_id"])
    text(a["revision_id"])
    text(a["editor_id"])
    timestamp(a["created_at"])
    if type(a["revision"]) is not int or a["revision"] < 1:
        raise ValueError("Session revision")
    if a["parent_reference"] is not None:
        reference(a["parent_reference"])
    from .volume import physical_calibration, plan

    class Header:
        metadata = type(
            "Metadata",
            (),
            {
                "format": "TIFF",
                "channels": s.channels,
                "dtype": s.dtype,
                "page_count": s.page_count,
                "height": s.height,
                "width": s.width,
            },
        )()

        def validate_region(self, x, y, w, h):
            if (
                x < 0
                or y < 0
                or w <= 0
                or h <= 0
                or x + w > s.width
                or y + h > s.height
            ):
                raise ValueError("ROI outside Source")

    selection = a["selection"]
    if selection != plan(
        Header(), selection["roi"], *selection["page_range"], selection["xy_step"]
    ):
        raise ValueError("Session mapping mismatch")
    expected = physical_calibration(s, s.page_count)
    if a["coordinate_mode"] == "INDEXED":
        if a["calibration"] is not None:
            raise ValueError("Indexed mode has no physical scale")
    elif (
        a["coordinate_mode"] != "PHYSICAL"
        or not expected
        or a["calibration"] != expected
    ):
        raise ValueError("Physical 3D evidence incomplete")
    settings = a["settings"]
    if set(settings) != {"cursor", "window", "camera", "plane_limit"}:
        raise ValueError("Session settings")
    if len(settings["cursor"]) != 3 or any(
        type(v) is not int or not 0 <= v < n
        for v, n in zip(settings["cursor"], selection["shape"])
    ):
        raise ValueError("Session cursor")
    finite(settings["window"])
    finite(settings["camera"])
    if (
        len(settings["window"]) != 2
        or not 0 <= settings["window"][0] < settings["window"][1] <= 65535
        or len(settings["camera"]) != 5
        or not 200 <= settings["camera"][4] <= 3000
        or max(abs(v) for v in settings["camera"][:4]) > 10000
    ):
        raise ValueError("Window / camera budget")
    if (
        type(settings["plane_limit"]) is not int
        or not 1 <= settings["plane_limit"] <= 12
    ):
        raise ValueError("Slice plane display budget")
    if (
        not isinstance(a["tracks"], list)
        or len(a["tracks"]) > 100
        or len(set(a["tracks"])) != len(a["tracks"])
    ):
        raise ValueError("Track reference budget")
    for r in a["tracks"]:
        reference(r)
    return a


def reference(ref):
    if not isinstance(ref, str) or not re.fullmatch(
        r"assets/stack-3d/[0-9a-f]{64}\.json", ref
    ):
        raise ValueError("3D asset reference invalid")
    return ref


def encode(a, compact=False):
    layout = {"separators": (",", ":")} if compact else {"indent": 2}
    data = (
        json.dumps(a, sort_keys=True, ensure_ascii=False, allow_nan=False, **layout)
        + "\n"
    ).encode("utf-8")
    if len(data) > MAX_BYTES:
        raise ValueError("3D asset exceeds 8MiB")
    return data


def publish(path, a, compact=False):
    data = encode(a, compact)
    return publish_bytes(path, data)


def publish_bytes(path, data):
    ref = PREFIX + hashlib.sha256(data).hexdigest() + ".json"
    root = Path(path).resolve().parent
    target = root / ref
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.parent.resolve().is_relative_to(root) or target.is_symlink():
        raise ValueError("3D asset path escape")
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError("3D asset overwrite forbidden")
        return ref
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=".stack3d-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(name, target)
        except FileExistsError:
            if target.read_bytes() != data:
                raise ValueError("Concurrent 3D publication differs")
    finally:
        Path(name).unlink(missing_ok=True)
    return ref


def read(path, ref):
    from sic_xrt_analyzer.results.persistence import ProjectStore

    reference(ref)
    with ProjectStore().resolve_asset(path, ref).open("rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != Path(ref).stem:
        raise ValueError("3D asset SHA / size mismatch")

    def pairs(rows):
        d = {}
        for k, v in rows:
            if k in d:
                raise ValueError("3D duplicate JSON key")
            d[k] = v
        return d

    return json.loads(
        data,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
    )


def sessions(project):
    return {
        s.source_id: s.acquisition_metadata[KEY]
        for s in project.image_sources
        if KEY in s.acquisition_metadata
    }


def chain(path, ref, project):
    rows = []
    seen = set()
    budget = 0
    track_seen = set()
    review_cache = {}
    previous = None
    while ref:
        if ref in seen or len(rows) >= MAX_HISTORY:
            raise ValueError("3D history cycle / revision budget")
        seen.add(ref)
        a = validate_session(read(path, ref), project)
        budget += len(encode(a))
        if previous and (
            a["session_id"] != previous["session_id"]
            or a["source_id"] != previous["source_id"]
            or a["revision"] + 1 != previous["revision"]
            or datetime.fromisoformat(a["created_at"])
            > datetime.fromisoformat(previous["created_at"])
        ):
            raise ValueError("3D session history order")
        ts = []
        for tr in a["tracks"]:
            t = validate_track(read(path, tr), project)
            if (
                t["source_id"] != a["source_id"]
                or t["source_sha256"] != a["source_sha256"]
            ):
                raise ValueError("Track belongs to different Source")
            ts.append(t)
            if tr not in track_seen:
                budget += len(encode(t))
                track_seen.add(tr)
        if len({t["track_id"] for t in ts}) != len(ts):
            raise ValueError("Duplicate Track ID")
        review = None
        if a.get(REVIEW_KEY):
            review = validate_review(read(path, a[REVIEW_KEY]), project, a)
            budget += len(encode(review))
            if not rows:  # head revision: replay events on the stored AUTO result
                load_result(path, review, a)
            else:
                newer = rows[-1][1].get(REVIEW_KEY)
                newer = review_cache.get(newer)
                if newer and newer["review_id"] == review["review_id"] and (
                    newer["result_reference"] != review["result_reference"]
                    or newer["events"][: len(review["events"])] != review["events"]
                ):
                    raise ValueError("Page-track review history rewriting forbidden")
            review_cache[a[REVIEW_KEY]] = review
        if rows:
            newer = {t["track_id"]: t for t in rows[-1][2]}
            for old in ts:
                new = newer.get(old["track_id"])
                if (
                    not new
                    or new["name"] != old["name"]
                    or new["creator"] != old["creator"]
                    or new["created_at"] != old["created_at"]
                    or new["events"][: len(old["events"])] != old["events"]
                ):
                    raise ValueError("Track history rewriting forbidden")
        if budget > 32 * 1024**2:
            raise ValueError("3D history cumulative 32MiB budget")
        rows.append((ref, a, ts))
        previous = a
        ref = a["parent_reference"]
    if rows and rows[-1][1]["revision"] != 1:
        raise ValueError("Missing first session revision")
    return rows


def validate_project_assets(path, project):
    try:
        for sid, ref in sessions(project).items():
            a = chain(path, ref, project)[0][1]
            if sid != a["source_id"]:
                raise ValueError("Session Source anchor mismatch")
    except (KeyError, TypeError, AttributeError, IndexError) as e:
        raise ValueError("Malformed 3D asset contract") from e


def attach(project, source_id, ref):
    reference(ref)
    return project.evolve(
        image_sources=tuple(
            replace(s, acquisition_metadata={**s.acquisition_metadata, KEY: ref})
            if s.source_id == source_id
            else s
            for s in project.image_sources
        )
    )


def check_history(path, old, new):
    before = sessions(old)
    after = sessions(new)
    for sid, ref in before.items():
        if sid not in after:
            raise ValueError("Cannot delete 3D session history")
        if after[sid] != ref and ref not in {
            r for r, _, _ in chain(path, after[sid], new)[1:]
        }:
            raise ValueError("Cannot rewrite session history")


def copy_assets(old_path, new_path, project):
    seen = set()
    for ref in sessions(project).values():
        for r, a, tracks in reversed(chain(old_path, ref, project)):
            for t in tracks:
                tr = PREFIX + hashlib.sha256(encode(t)).hexdigest() + ".json"
                if tr not in seen:
                    publish(new_path, t)
                    seen.add(tr)
            extra = []
            if a.get(REVIEW_KEY):
                review = read(old_path, a[REVIEW_KEY])
                extra = [review["result_reference"], a[REVIEW_KEY]]
            for x in extra:
                if x not in seen:
                    copy_raw(old_path, new_path, x)
                    seen.add(x)
            if r not in seen:
                publish(new_path, a)
                seen.add(r)


def copy_raw(old_path, new_path, ref):
    """Copy an asset byte-for-byte after its SHA check (any JSON layout)."""
    from sic_xrt_analyzer.results.persistence import ProjectStore

    read(old_path, ref)
    data = ProjectStore().resolve_asset(old_path, ref).read_bytes()
    if publish_bytes(new_path, data) != ref:
        raise ValueError("3D asset copy SHA mismatch")


# Page-track review (#188) ------------------------------------------------------

REVIEW_KEYS = {
    "schema",
    "project_id",
    "source_id",
    "source_sha256",
    "review_id",
    "result_reference",
    "result_schema",
    "algorithm_version",
    "selection",
    "creator",
    "created_at",
    "revision",
    "events",
}
MAX_REVIEW_EVENTS = 4096


def review_selection(selection):
    return {
        "roi": list(selection["roi"]),
        "page_range": list(selection["page_range"]),
        "xy_step": selection["xy_step"],
    }


def new_review(s, project_id, result_ref, selection, creator):
    from .tracking.model import ALGORITHM_VERSION, SCHEMA
    from .tracking.review import REVIEW

    text(creator)
    return {
        "schema": REVIEW,
        "project_id": project_id,
        "source_id": s.source_id,
        "source_sha256": s.content_hash.value,
        "review_id": str(uuid4()),
        "result_reference": reference(result_ref),
        "result_schema": SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
        "selection": review_selection(selection),
        "creator": creator,
        "created_at": utc_now().isoformat(),
        "revision": 0,
        "events": [],
    }


def review_event(action, track_id, reviewer, *, other=None, source_detection=None,
                 target_detection=None, page=None):
    text(reviewer)
    return {
        "revision": 0,  # numbered when appended
        "action": action,
        "track_id": track_id,
        "other_track_id": other,
        "source_detection": source_detection,
        "target_detection": target_detection,
        "page_index": page,
        "reviewer": reviewer,
        "status": "REVIEWED",
        "method": "MANUAL",
        "created_at": utc_now().isoformat(),
    }


def validate_review(r, project, session):
    from .tracking.model import SCHEMA
    from .tracking.review import REVIEW

    if not isinstance(r, dict) or set(r) != REVIEW_KEYS or r["schema"] != REVIEW:
        raise ValueError("Unsupported page-track review schema")
    if (
        r["project_id"] != project.project_id
        or r["source_id"] != session["source_id"]
        or r["source_sha256"] != session["source_sha256"]
    ):
        raise ValueError("Page-track review belongs to different Source")
    source(project, r["source_id"], r["source_sha256"])
    reference(r["result_reference"])
    if r["result_schema"] != SCHEMA:
        raise ValueError("Unsupported page-track result schema")
    text(r["review_id"])
    text(r["creator"])
    text(r["algorithm_version"])
    timestamp(r["created_at"])
    if r["selection"] != review_selection(session["selection"]):
        raise ValueError("Page-track review selection mismatch")
    events = r["events"]
    if (
        not isinstance(events, list)
        or len(events) > MAX_REVIEW_EVENTS
        or type(r["revision"]) is not int
        or r["revision"] != len(events)
    ):
        raise ValueError("Page-track review event budget / revision")
    previous = r["created_at"]
    for n, e in enumerate(events, 1):
        if not isinstance(e, dict) or type(e.get("revision")) is not int or e["revision"] != n:
            raise ValueError("Page-track review event revision")
        text(e.get("reviewer"))
        timestamp(e.get("created_at"))
        if datetime.fromisoformat(e["created_at"]) < datetime.fromisoformat(previous):
            raise ValueError("Page-track review timestamp order")
        previous = e["created_at"]
        page = e.get("page_index")
        if page is not None and (type(page) is not int or not 0 <= page < session["stack_page_count"]):
            raise ValueError("Page-track review page out of Source")
    return r


def load_result(path, review, session):
    """Read the AUTO result and replay review events; returns (result, state)."""
    from .tracking.model import TrackResult
    from .tracking.review import ReviewState

    result = TrackResult.from_dict(read(path, review["result_reference"]))
    sel = session["selection"]
    if (
        list(result.origin) != sel["roi"][:2]
        or result.first_page != sel["page_range"][0]
        or list(result.shape) != sel["shape"]
    ):
        raise ValueError("Page-track result does not match session selection")
    return result, ReviewState(result, review["events"])
