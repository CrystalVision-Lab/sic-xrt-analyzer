"""Initial append-only collection and authentication schema."""

from alembic import op
from xrt_server.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(
        op.get_bind(),
        tables=[
            t
            for t in Base.metadata.sorted_tables
            if t.name not in {"dataset_events", "dataset_versions", "model_candidates", "model_events", "model_releases", "review_labels", "label_dataset_versions"}
        ],
    )


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a verified backup")
