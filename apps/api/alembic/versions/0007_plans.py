"""plans

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE plans (
            id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            uuid        NOT NULL REFERENCES users(id),
            generated_by       text        NOT NULL,
            prompt_version     text,
            horizon_days       int         NOT NULL,
            rationale          jsonb       NOT NULL,
            predicted_pct_band jsonb,
            created_at         timestamptz NOT NULL DEFAULT now(),
            superseded_at      timestamptz
        )
    """)
    op.execute("CREATE INDEX plans_user ON plans(user_id, created_at DESC) WHERE superseded_at IS NULL")
    op.execute("ALTER TABLE plans ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE plans FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON plans
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)
    op.execute("""
        CREATE TABLE plan_blocks (
            id                 uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id            uuid  NOT NULL REFERENCES plans(id),
            day                date  NOT NULL,
            ord                int   NOT NULL,
            goal               text  NOT NULL,
            block_kind         text  NOT NULL CHECK (block_kind IN ('tutor','drill','pyq','review','mock')),
            target_concept_ids uuid[] NOT NULL,
            duration_min       int   NOT NULL,
            status             text  NOT NULL DEFAULT 'pending'
                                   CHECK (status IN ('pending','done','skipped','rescheduled')),
            rescheduled_to     date
        )
    """)
    op.execute("CREATE INDEX plan_blocks_plan ON plan_blocks(plan_id, day, ord)")
    op.execute("ALTER TABLE plan_blocks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE plan_blocks FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON plan_blocks
            USING (
                EXISTS (
                    SELECT 1 FROM plans p
                    WHERE p.id = plan_id
                      AND p.user_id = current_setting('app.user_id', true)::uuid
                )
            )
    """)
    # Backfill FK: sessions.plan_block_id → plan_blocks.id (deferred from 0006)
    op.execute("""
        ALTER TABLE sessions
            ADD CONSTRAINT sessions_plan_block_fk
            FOREIGN KEY (plan_block_id) REFERENCES plan_blocks(id)
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP CONSTRAINT IF EXISTS sessions_plan_block_fk")
    op.execute("DROP POLICY IF EXISTS user_isolation ON plan_blocks")
    op.execute("ALTER TABLE plan_blocks NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE plan_blocks")
    op.execute("DROP POLICY IF EXISTS user_isolation ON plans")
    op.execute("ALTER TABLE plans NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE plans")
