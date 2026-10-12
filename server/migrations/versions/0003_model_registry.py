"""Immutable model candidates, approval/key/channel events and signed releases."""

from alembic import op
from xrt_server.models import ModelCandidate, ModelEvent, ModelRelease

revision = "0003"
down_revision = "0002"
branch_labels = depends_on = None


def upgrade():
    for table in (
        ModelCandidate.__table__,
        ModelEvent.__table__,
        ModelRelease.__table__,
    ):
        table.create(op.get_bind())
        op.execute(
            f"CREATE TRIGGER {table.name}_immutable BEFORE UPDATE OR DELETE ON {table.name} "
            "FOR EACH ROW EXECUTE FUNCTION xrt_dataset_append_only()"
        )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a verified backup")
