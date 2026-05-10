"""events

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE events (
            id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id        uuid,
            kind           text        NOT NULL,
            schema_version int         NOT NULL,
            payload        jsonb       NOT NULL,
            cause_event_id uuid        REFERENCES events(id),
            created_at     timestamptz NOT NULL DEFAULT now()
        )
    """)
    # Primary access pattern: per-user, per-kind, recent-first
    op.execute("CREATE INDEX events_user_kind_time ON events(user_id, kind, created_at DESC)")
    # BRIN is efficient because the event log is time-ordered
    op.execute("CREATE INDEX events_time_brin ON events USING BRIN (created_at)")
    # Partial indexes for the three hottest event kinds
    op.execute("CREATE INDEX events_attempt_created ON events(user_id, created_at DESC) WHERE kind = 'attempt.created'")
    op.execute("CREATE INDEX events_mastery_updated ON events(user_id, created_at DESC) WHERE kind = 'mastery.updated'")
    op.execute("CREATE INDEX events_tutor_turn ON events(user_id, created_at DESC) WHERE kind = 'tutor.turn.completed'")
    # GIN for payload queries (e.g. find events by session_id inside payload)
    op.execute("CREATE INDEX events_payload_gin ON events USING GIN (payload)")


def downgrade() -> None:
    op.execute("DROP TABLE events")
