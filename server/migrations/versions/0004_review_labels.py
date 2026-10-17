"""Append-only candidate review labels (review_label/v1)."""

from alembic import op
from xrt_server.models import ReviewLabel

revision = "0004"
down_revision = "0003"
branch_labels = depends_on = None


def upgrade():
    table = ReviewLabel.__table__
    table.create(op.get_bind())
    op.execute(
        f"CREATE TRIGGER {table.name}_immutable BEFORE UPDATE OR DELETE ON {table.name} "
        "FOR EACH ROW EXECUTE FUNCTION xrt_dataset_append_only()"
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a verified backup")
