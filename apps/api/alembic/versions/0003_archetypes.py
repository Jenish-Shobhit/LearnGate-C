"""archetypes

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE archetypes (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            slug        text UNIQUE NOT NULL,
            name        text NOT NULL,
            section     text NOT NULL CHECK (section IN ('QA','VARC','DILR')),
            description text
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE archetypes")
