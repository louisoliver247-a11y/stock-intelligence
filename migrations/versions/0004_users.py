"""Workspace users and revocable sessions."""
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.execute("""CREATE TABLE app_users (
        id uuid PRIMARY KEY, email text NOT NULL UNIQUE,
        password_hash text NOT NULL, role text NOT NULL CHECK (role IN ('admin','user')),
        created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE user_sessions (
        token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
        expires_at timestamptz NOT NULL)""")


def downgrade():
    op.execute("DROP TABLE user_sessions")
    op.execute("DROP TABLE app_users")
