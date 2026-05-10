"""llm_calls

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE llm_calls (
            id             uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        uuid,
            agent          text         NOT NULL,
            prompt_version text         NOT NULL,
            model          text         NOT NULL,
            input_tokens   int,
            output_tokens  int,
            cached_tokens  int,
            latency_ms     int,
            cost_usd       numeric(12,6),
            request        jsonb,
            response       jsonb,
            trace_id       text,
            cause_event_id uuid         REFERENCES events(id),
            created_at     timestamptz  NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX llm_calls_user_time ON llm_calls(user_id, created_at DESC)")
    op.execute("CREATE INDEX llm_calls_agent     ON llm_calls(agent, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE llm_calls")
