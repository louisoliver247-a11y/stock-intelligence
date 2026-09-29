"""Enable hypertable only if Timescale is available to this database."""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        CREATE EXTENSION IF NOT EXISTS timescaledb;
        PERFORM create_hypertable('candles', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);
      END IF;
    END $$""")


def downgrade():
    # Extension is shared infrastructure; never drop it (or candle history) on downgrade.
    pass
