import hashlib
import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.engine import make_url
from xrt_server.api import create_app
from xrt_server.auth import grant, issue
from xrt_server.db import connect, database_url
from xrt_server.models import Base, User

from sic_xrt_analyzer.analysis.contracts import AnalysisScope, AnalysisState, utc_now
from sic_xrt_analyzer.results.contracts import (
    AnalysisProject,
    AnalysisRunRecord,
    CandidateObservation,
    FileIdentity,
    ImageSourceRecord,
    ModelPrediction,
    ModelProvenance,
    ReviewTarget,
    VerifiedContentHash,
)
from sic_xrt_analyzer.results.geometry import (
    DefectGeometry,
    DefectGeometryKind,
    GeometrySource,
)
from sic_xrt_analyzer.results.review_workspace import append_review


@pytest.fixture(scope="session")
def database():
    url = os.environ.get("XRT_TEST_DATABASE_URL") or (
        database_url() if os.getenv("XRT_TEST_DATABASE_NAME") else None
    )
    if not url or not make_url(url).database.endswith("_test"):
        pytest.fail("Explicit dedicated PostgreSQL *_test database required")
    engine, sessions = connect(url)
    Base.metadata.drop_all(engine)
    # Isolated test DB only; production database is never cleared.
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    previous = os.environ.get("XRT_DATABASE_URL")
    os.environ["XRT_DATABASE_URL"] = make_url(url).render_as_string(hide_password=False)
    command.upgrade(Config("server/alembic.ini"), "head")
    if previous is None:
        os.environ.pop("XRT_DATABASE_URL", None)
    else:
        os.environ["XRT_DATABASE_URL"] = previous
    yield url, engine, sessions
    engine.dispose()


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "synthetic.jpg"
    Image.new("RGB", (96, 96), (111, 123, 137)).save(path)
    stat = path.stat()
    now = utc_now()
    sid = str(uuid4())
    rid = str(uuid4())
    proid = str(uuid4())
    resultid = str(uuid4())
    gid = str(uuid4())
    oid = str(uuid4())
    p = AnalysisProject("Synthetic sync test")
    source = ImageSourceRecord(
        sid,
        path.name,
        str(path),
        96,
        96,
        "uint8",
        8,
        3,
        1,
        FileIdentity(str(path), stat.st_size, stat.st_mtime_ns),
        acquisition_metadata={"format": "JPEG"},
        content_hash=VerifiedContentHash(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            now,
            str(path),
            stat.st_size,
            stat.st_mtime_ns,
        ),
    )
    provenance = ModelProvenance(
        proid,
        "synthetic-test-model",
        "1",
        resultid,
        "a" * 64,
        input_contract={"dtype": "uint8"},
        output_contract={"meaning": "uncalibrated_class_scores"},
    )
    run = AnalysisRunRecord(
        rid,
        p.project_id,
        sid,
        0,
        AnalysisScope.FULL_IMAGE,
        None,
        provenance.model_id,
        "1",
        "a" * 64,
        proid,
        "synthetic",
        {},
        {},
        now,
        now,
        AnalysisState.COMPLETED,
        resultid,
        {
            "canonical_path": str(path),
            "file_size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "page_index": 0,
            "width": 96,
            "height": 96,
        },
    )
    geometry = DefectGeometry(
        gid, sid, 0, DefectGeometryKind.POINT, GeometrySource.MODEL, ((32.0, 32.0),)
    )
    observation = CandidateObservation(
        oid,
        rid,
        "candidate-1",
        "point-1",
        32.0,
        32.0,
        0,
        "BPD",
        (0.9, 0.05, 0.05),
        0.9,
        False,
        "synthetic",
        gid,
    )
    prediction = ModelPrediction(
        str(uuid4()),
        oid,
        proid,
        "BPD",
        (0.9, 0.05, 0.05),
        0.9,
        ("BPD", "TED", "TSD"),
        "UNCALIBRATED",
    )
    p = p.evolve(
        image_sources=(source,),
        analysis_runs=(run,),
        model_provenance=(provenance,),
        geometries=(geometry,),
        observations=(observation,),
        predictions=(prediction,),
    )
    return append_review(
        p,
        ReviewTarget.OBSERVATION,
        oid,
        "local-reviewer",
        "PRESENT",
        "TED",
        "ACCEPTED",
        "synthetic test",
        source_id=sid,
        run_id=rid,
    )[0]


@pytest.fixture
def api(database, project, tmp_path):
    url, _engine, sessions = database
    user = User(id=str(uuid4()), name="Synthetic researcher", role="RESEARCHER")
    admin = User(id=str(uuid4()), name="Synthetic admin", role="ADMIN")
    with sessions.begin() as s:
        s.add_all([user, admin])
        s.flush()
        client = str(uuid4())
        cred, token = issue(s, user.id, client)
        admin_client = str(uuid4())
        _, admin_token = issue(s, admin.id, admin_client)
        grant(s, user.id, project.project_id, True)
    app = create_app(url, tmp_path / "assets")
    with TestClient(app, raise_server_exceptions=False) as http:
        yield http, app, sessions, user, client, token, admin_token, cred.id
    app.state.engine.dispose()
