"""concept_graph

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE concept_graph_versions (
            version    int         PRIMARY KEY,
            notes      text,
            created_at timestamptz DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE concepts (
            id             uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
            graph_version  int     NOT NULL REFERENCES concept_graph_versions(version),
            slug           text    NOT NULL,
            name           text    NOT NULL,
            section        text    NOT NULL CHECK (section IN ('QA','VARC','DILR')),
            parent_id      uuid    REFERENCES concepts(id),
            depth          int     NOT NULL,
            weight_in_exam numeric NOT NULL DEFAULT 0.0,
            half_life_days numeric NOT NULL DEFAULT 14,
            metadata       jsonb   NOT NULL DEFAULT '{}',
            UNIQUE (graph_version, slug)
        )
    """)
    op.execute("CREATE INDEX concepts_section ON concepts(section, graph_version)")
    op.execute("""
        CREATE TABLE concept_edges (
            graph_version int     NOT NULL,
            parent_id     uuid    NOT NULL REFERENCES concepts(id),
            child_id      uuid    NOT NULL REFERENCES concepts(id),
            kind          text    NOT NULL CHECK (kind IN ('prereq','related')),
            weight        numeric NOT NULL DEFAULT 1.0,
            PRIMARY KEY (graph_version, parent_id, child_id, kind)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE concept_edges")
    op.execute("DROP TABLE concepts")
    op.execute("DROP TABLE concept_graph_versions")
