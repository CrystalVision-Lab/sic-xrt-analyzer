import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def database_url():
    if os.getenv("XRT_DATABASE_URL"):
        return os.environ["XRT_DATABASE_URL"]
    from sqlalchemy.engine import URL

    secret = Path(os.environ["XRT_DB_PASSWORD_FILE"]).read_text().strip()
    return URL.create(
        "postgresql+psycopg",
        username="xrt",
        password=secret,
        host="postgres",
        database=os.getenv("XRT_TEST_DATABASE_NAME", "xrt"),
    )


def connect(url=None):
    engine = create_engine(
        url or database_url(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 5},
    )
    if engine.dialect.name != "postgresql":
        raise RuntimeError("PostgreSQL required")
    return engine, sessionmaker(engine, expire_on_commit=False)
