from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sic_xrt_analyzer.sync.protocol import SPECS


class Base(DeclarativeBase):
    pass


def now():
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "server_users"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(16))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("server_users.id"))


class Credential(Base):
    __tablename__ = "credentials"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Project(Base):
    __tablename__ = "research_projects"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Membership(Base):
    __tablename__ = "project_memberships"
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("server_users.id"), primary_key=True
    )
    crops: Mapped[bool] = mapped_column(Boolean, default=False)


# Separate typed entity tables, indexed relation columns and JSONB for full contract details.
ENTITIES = {}
for kind in SPECS:
    attributes = {
        "__tablename__": kind,
        "__annotations__": {},
        "project_id": mapped_column(
            String(128), ForeignKey("research_projects.id"), primary_key=True
        ),
        "id": mapped_column(String(128), primary_key=True),
        "digest": mapped_column(String(64), nullable=False),
        "payload": mapped_column(JSONB, nullable=False),
        "actor_id": mapped_column(
            String(128), ForeignKey("server_users.id"), nullable=False
        ),
        "device_id": mapped_column(
            String(128), ForeignKey("devices.id"), nullable=False
        ),
        "received_at": mapped_column(
            DateTime(timezone=True), default=now, nullable=False
        ),
        "source_id": mapped_column(String(128), index=True),
        "run_id": mapped_column(String(128), index=True),
        "geometry_id": mapped_column(String(128), index=True),
        "target_id": mapped_column(String(128), index=True),
        "provenance_id": mapped_column(String(128), index=True),
    }
    ENTITIES[kind] = type("Stored" + kind.title().replace("_", ""), (Base,), attributes)


class Batch(Base):
    __tablename__ = "sync_batches"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id"), index=True
    )
    client_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("server_users.id"))
    digest: Mapped[str] = mapped_column(String(64))
    receipt: Mapped[dict] = mapped_column(JSONB)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Snapshot(Base):
    __tablename__ = "sync_receipts"
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id"), primary_key=True
    )
    client_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str] = mapped_column(ForeignKey("sync_batches.id"))


class Asset(Base):
    __tablename__ = "crop_assets"
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(ForeignKey("server_users.id"))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DatasetEvent(Base):
    """Immutable administrator assertions; never overwrite individual reviews."""

    __tablename__ = "dataset_events"
    __table_args__ = (UniqueConstraint("project_id", "kind", "subject_id", "revision"),)
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("research_projects.id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    subject_id: Mapped[str] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(ForeignKey("server_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version: Mapped[str] = mapped_column(String(80), unique=True)
    digest: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(ForeignKey("server_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelCandidate(Base):
    __tablename__ = "model_candidates"
    __table_args__ = (UniqueConstraint("model_id", "version"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(96))
    version: Mapped[str] = mapped_column(String(96))
    realm: Mapped[str] = mapped_column(String(16))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("dataset_versions.id"))
    payload: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(ForeignKey("server_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelEvent(Base):
    __tablename__ = "model_events"
    __table_args__ = (UniqueConstraint("subject_id", "revision"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(128), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(ForeignKey("server_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelRelease(Base):
    __tablename__ = "model_releases"
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, unique=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("model_candidates.id"))
    channel: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(ForeignKey("server_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ReviewLabel(Base):
    """One human decision on a candidate (review_label/v1). Append-only."""

    __tablename__ = "review_labels"
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(ForeignKey("server_users.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    candidate_id: Mapped[str] = mapped_column(String(256), index=True)
    parent_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    predicted: Mapped[str] = mapped_column(String(8))
    queue_kind: Mapped[str] = mapped_column(String(16))
    has_crop: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, index=True
    )
    payload: Mapped[dict] = mapped_column(JSONB)
