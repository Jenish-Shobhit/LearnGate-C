"""mastery

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE mastery (
            user_id           uuid        NOT NULL REFERENCES users(id),
            concept_id        uuid        NOT NULL REFERENCES concepts(id),
            graph_version     int         NOT NULL,
            p_known           numeric     NOT NULL CHECK (p_known >= 0 AND p_known <= 1),
            alpha             numeric     NOT NULL,
            beta              numeric     NOT NULL,
            ci_low            numeric,
            ci_high           numeric,
            last_practiced_at timestamptz,
            decayed_at        timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, concept_id, graph_version)
        )
    """)
    op.execute("CREATE INDEX mastery_user ON mastery(user_id, graph_version)")
    op.execute("ALTER TABLE mastery ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mastery FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON mastery
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)
    op.execute("""
        CREATE TABLE mastery_snapshots (
            id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     uuid        NOT NULL REFERENCES users(id),
            snapshot_at timestamptz NOT NULL,
            snapshot    jsonb       NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, snapshot_at)
        )
    """)
    op.execute("ALTER TABLE mastery_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mastery_snapshots FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON mastery_snapshots
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_isolation ON mastery_snapshots")
    op.execute("ALTER TABLE mastery_snapshots NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE mastery_snapshots")
    op.execute("DROP POLICY IF EXISTS user_isolation ON mastery")
    op.execute("ALTER TABLE mastery NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE mastery")
