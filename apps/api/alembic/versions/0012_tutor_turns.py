"""tutor_turns

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE tutor_turns (
            id             uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id     uuid         NOT NULL REFERENCES sessions(id),
            user_id        uuid         NOT NULL REFERENCES users(id),
            turn_index     int          NOT NULL,
            move           text         NOT NULL,
            prompt_version text,
            model          text,
            input_text     text,
            output_text    text,
            citations      jsonb        NOT NULL DEFAULT '[]',
            tokens_input   int,
            tokens_output  int,
            cached_tokens  int,
            cost_usd       numeric(12,6),
            latency_ms     int,
            llm_call_id    uuid         REFERENCES llm_calls(id),
            created_at     timestamptz  NOT NULL DEFAULT now(),
            UNIQUE (session_id, turn_index)
        )
    """)
    op.execute("CREATE INDEX tutor_turns_session ON tutor_turns(session_id, turn_index)")
    op.execute("ALTER TABLE tutor_turns ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tutor_turns FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_isolation ON tutor_turns
            USING (user_id = current_setting('app.user_id', true)::uuid)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_isolation ON tutor_turns")
    op.execute("ALTER TABLE tutor_turns NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE tutor_turns")
