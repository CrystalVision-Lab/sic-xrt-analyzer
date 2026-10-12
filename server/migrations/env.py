from alembic import context
from xrt_server.db import connect
from xrt_server.models import Base

engine, _ = connect()
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
