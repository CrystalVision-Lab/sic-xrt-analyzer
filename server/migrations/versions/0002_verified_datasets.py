"""Add approval/group events and immutable dataset versions, preserving TD06."""

from alembic import op
from xrt_server.models import DatasetEvent, DatasetVersion

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    for table in (DatasetEvent.__table__, DatasetVersion.__table__):
        table.create(op.get_bind())
    op.execute("""CREATE OR REPLACE FUNCTION xrt_dataset_append_only()
        RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'Dataset history is append-only'; END $$""")
    for name in ("dataset_events", "dataset_versions"):
        op.execute(
            f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} "
            "FOR EACH ROW EXECUTE FUNCTION xrt_dataset_append_only()"
        )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a verified backup")
