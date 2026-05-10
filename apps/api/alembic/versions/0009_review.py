"""review

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE open_loops (
            id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     uuid        NOT NULL REFERENCES users(id),
            question_id uuid        REFERENCES questions(id),
            concept_id  uuid        REFERENCES concepts(id),
            note        text,
            status      text        NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
            created_at  timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz,
            CHECK (question_id IS NOT NULL OR concept_id IS NOT NULL OR note IS NOT NULL)
        )
    """)
    op.execute("CREATE INDEX open_loops_user ON open_loops(user_id, status, created_at DESC)")
    op.execute("ALTER TABLE open_loops ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE open_loops FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON open_loops
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)
    op.execute("""
        CREATE TABLE debriefs (
            id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id    uuid        UNIQUE REFERENCES sessions(id),
            user_id       uuid        NOT NULL REFERENCES users(id),
            summary_md    text        NOT NULL,
            mastery_delta jsonb       NOT NULL,
            created_at    timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("ALTER TABLE debriefs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE debriefs FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON debriefs
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)
    op.execute("""
        CREATE TABLE review_cards (
            id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          uuid        NOT NULL REFERENCES users(id),
            scope            text        NOT NULL CHECK (scope IN ('concept','question')),
            ref_id           uuid        NOT NULL,
            state            text        NOT NULL CHECK (state IN ('new','learning','review','relearning')),
            stability        numeric,
            difficulty       numeric,
            due_at           timestamptz NOT NULL,
            last_reviewed_at timestamptz,
            UNIQUE (user_id, scope, ref_id)
        )
    """)
    op.execute("CREATE INDEX review_cards_due ON review_cards(user_id, due_at) WHERE state != 'new'")
    op.execute("ALTER TABLE review_cards ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE review_cards FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON review_cards
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_isolation ON review_cards")
    op.execute("ALTER TABLE review_cards NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE review_cards")
    op.execute("DROP POLICY IF EXISTS user_isolation ON debriefs")
    op.execute("ALTER TABLE debriefs NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE debriefs")
    op.execute("DROP POLICY IF EXISTS user_isolation ON open_loops")
    op.execute("ALTER TABLE open_loops NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE open_loops")
