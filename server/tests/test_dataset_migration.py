"""Upgrade populated TD06 and logical backup/restore of TD07 in isolated *_test DBs."""

import os
import subprocess
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from xrt_server.db import connect
from xrt_server.models import DatasetEvent, DatasetVersion, Project, User


def test_populated_0001_upgrade_and_verified_registry_restore(database):
    _url, _engine, _sessions = database
    names = ["xrt_td108_" + uuid4().hex[:10] + "_test" for _ in range(2)]
    bootstrap = create_engine(
        _engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    previous = os.environ.get("XRT_DATABASE_URL")
    engines = []
    try:
        with bootstrap.connect() as c:
            for name in names:
                assert name.startswith("xrt_td108_") and name.endswith("_test")
                c.execute(text(f'CREATE DATABASE "{name}"'))
        config = Config("server/alembic.ini")
        first_url = _engine.url.set(database=names[0])
        os.environ["XRT_DATABASE_URL"] = first_url.render_as_string(hide_password=False)
        command.upgrade(config, "0001")
        first, sessions = connect(first_url)
        engines.append(first)
        assert "dataset_events" not in inspect(first).get_table_names()
        with sessions.begin() as s:
            s.add(
                User(
                    id="legacy-admin", name="Synthetic migration sentinel", role="ADMIN"
                )
            )
            s.add(Project(id="legacy-project", payload={"sentinel": "preserve TD06"}))
        command.upgrade(config, "head")
        with sessions.begin() as s:
            assert s.get(Project, "legacy-project").payload == {
                "sentinel": "preserve TD06"
            }
            s.add(
                DatasetEvent(
                    id="synthetic-approval",
                    project_id="legacy-project",
                    kind="APPROVAL",
                    subject_id="fixture",
                    revision=1,
                    actor_id="legacy-admin",
                    payload={"status": "APPROVED", "data_origin": "synthetic_fixture"},
                )
            )
            s.add(
                DatasetVersion(
                    id="synthetic-version",
                    version="synthetic-restore",
                    digest="a" * 64,
                    actor_id="legacy-admin",
                    payload={"sentinel": "immutable fixture registry"},
                )
            )
        with sessions() as s:
            before = s.get(DatasetVersion, "synthetic-version").payload
        # Logical DB copy exercises Postgres schema, trigger and payload restoration, never operational DB.
        env = {**os.environ, "PGPASSWORD": _engine.url.password}
        container = os.getenv("XRT_TEST_PG_CLIENT_CONTAINER")
        prefix = (
            ["docker", "exec", "-i", "-e", "PGPASSWORD", container] if container else []
        )
        source = [
            "-h",
            "127.0.0.1" if container else _engine.url.host,
            "-U",
            _engine.url.username,
        ]
        dump = subprocess.run(
            [*prefix, "pg_dump", *source, "-d", names[0], "--no-owner"],
            env=env,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            [*prefix, "psql", *source, "-d", names[1], "-v", "ON_ERROR_STOP=1"],
            input=dump.stdout,
            env=env,
            capture_output=True,
            check=True,
        )
        second, sessions2 = connect(_engine.url.set(database=names[1]))
        engines.append(second)
        with sessions2() as s:
            assert s.get(DatasetVersion, "synthetic-version").payload == before
            assert (
                s.get(DatasetEvent, "synthetic-approval").payload["status"]
                == "APPROVED"
            )
            assert s.get(Project, "legacy-project").payload == {
                "sentinel": "preserve TD06"
            }
        command.upgrade(config, "head")  # repeated upgrade is harmless
    finally:
        if previous is None:
            os.environ.pop("XRT_DATABASE_URL", None)
        else:
            os.environ["XRT_DATABASE_URL"] = previous
        for engine in engines:
            engine.dispose()
        with bootstrap.connect() as c:
            for name in names:
                if name.startswith("xrt_td108_") and name.endswith("_test"):
                    c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        bootstrap.dispose()
