"""mocks

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE mock_papers (
            id              uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
            source          text  NOT NULL,
            generated       bool  NOT NULL DEFAULT false,
            question_layout jsonb NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE mocks (
            id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            uuid        NOT NULL REFERENCES users(id),
            paper_id           uuid        NOT NULL REFERENCES mock_papers(id),
            started_at         timestamptz,
            ended_at           timestamptz,
            status             text        NOT NULL CHECK (status IN ('active','completed','abandoned')),
            scaled_score       jsonb,
            predicted_pct_band jsonb,
            metadata           jsonb       DEFAULT '{}'
        )
    """)
    op.execute("CREATE INDEX mocks_user ON mocks(user_id, started_at DESC)")
    op.execute("ALTER TABLE mocks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mocks FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON mocks
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)
    op.execute("""
        CREATE TABLE mock_state (
            mock_id    uuid        PRIMARY KEY REFERENCES mocks(id),
            user_id    uuid        NOT NULL REFERENCES users(id),
            state_blob jsonb       NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE mock_state ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE mock_state FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON mock_state
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)
    op.execute("""
        CREATE TABLE mock_calibration (
            id         uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
            source     text         NOT NULL,
            section    text         NOT NULL CHECK (section IN ('QA','VARC','DILR','total')),
            raw_score  int          NOT NULL,
            percentile numeric(5,2) NOT NULL,
            year       int          NOT NULL,
            UNIQUE (source, section, raw_score)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE mock_calibration")
    op.execute("DROP POLICY IF EXISTS user_isolation ON mock_state")
    op.execute("ALTER TABLE mock_state NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE mock_state")
    op.execute("DROP POLICY IF EXISTS user_isolation ON mocks")
    op.execute("ALTER TABLE mocks NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE mocks")
    op.execute("DROP TABLE mock_papers")
