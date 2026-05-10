"""users

Revision ID: 0001
Revises:
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("""
        CREATE TABLE users (
            id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            clerk_id      text        UNIQUE NOT NULL,
            email         citext      UNIQUE NOT NULL,
            display_name  text,
            exam_date     date,
            target_pct    numeric(5,2),
            hours_per_day numeric(3,1),
            timezone      text        NOT NULL DEFAULT 'Asia/Kolkata',
            locale        text        NOT NULL DEFAULT 'en-IN',
            graph_version int         NOT NULL DEFAULT 1,
            created_at    timestamptz NOT NULL DEFAULT now(),
            updated_at    timestamptz NOT NULL DEFAULT now(),
            deleted_at    timestamptz
        )
    """)
    op.execute("CREATE INDEX users_clerk ON users(clerk_id)")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_self_isolation ON users
            USING (id = current_setting('app.user_id', true)::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_self_isolation ON users")
    op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE users")
