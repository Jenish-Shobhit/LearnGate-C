"""sessions

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # plan_block_id FK is intentionally left as plain uuid here;
    # the FK constraint is added in 0007 after plan_blocks exists.
    op.execute("""
        CREATE TABLE sessions (
            id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       uuid        NOT NULL REFERENCES users(id),
            kind          text        NOT NULL CHECK (kind IN ('study','drill','pyq','mock','diagnostic','review')),
            plan_block_id uuid,
            started_at    timestamptz NOT NULL DEFAULT now(),
            ended_at      timestamptz,
            status        text        NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active','completed','abandoned','crashed')),
            metadata      jsonb       DEFAULT '{}'
        )
    """)
    op.execute("CREATE INDEX sessions_user_time ON sessions(user_id, started_at DESC)")
    op.execute("ALTER TABLE sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sessions FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON sessions
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)
    op.execute("""
        CREATE TABLE attempts (
            id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id       uuid        NOT NULL REFERENCES users(id),
            session_id    uuid        REFERENCES sessions(id),
            question_id   uuid        NOT NULL REFERENCES questions(id),
            response      jsonb       NOT NULL,
            is_correct    bool,
            time_ms       int,
            confidence    int         CHECK (confidence BETWEEN 1 AND 5),
            error_type    text        CHECK (error_type IN ('conceptual','procedural','careless','time','misread','none')),
            process_grade jsonb,
            near_miss     bool        DEFAULT false,
            graded_at     timestamptz,
            idem_key      text,
            created_at    timestamptz NOT NULL DEFAULT now(),
            UNIQUE (session_id, question_id, idem_key)
        )
    """)
    op.execute("CREATE INDEX attempts_user_time     ON attempts(user_id, created_at DESC)")
    op.execute("CREATE INDEX attempts_user_question ON attempts(user_id, question_id)")
    op.execute("ALTER TABLE attempts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE attempts FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON attempts
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_isolation ON attempts")
    op.execute("ALTER TABLE attempts NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE attempts")
    op.execute("DROP POLICY IF EXISTS user_isolation ON sessions")
    op.execute("ALTER TABLE sessions NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE sessions")
