"""Immutable review-label consensus datasets (verified_xrt_dataset/v2)."""

from alembic import op
from xrt_server.models import LabelDatasetVersion

revision = "0005"
down_revision = "0004"
branch_labels = depends_on = None


def upgrade():
    table = LabelDatasetVersion.__table__
    table.create(op.get_bind())
    op.execute(
        f"CREATE TRIGGER {table.name}_immutable BEFORE UPDATE OR DELETE ON {table.name} "
        "FOR EACH ROW EXECUTE FUNCTION xrt_dataset_append_only()"
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a verified backup")
