"""Initial append-only collection and authentication schema."""

from alembic import op
from xrt_server.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(op.get_bind())


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; restore a verified backup")
