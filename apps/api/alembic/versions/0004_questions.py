"""questions

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-10

"""
from typing import Sequence, Union
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE question_groups (
            id             uuid  PRIMARY KEY DEFAULT gen_random_uuid(),
            kind           text  NOT NULL CHECK (kind IN ('rc_passage','dilr_set','lr_set','standalone')),
            shared_text    text,
            shared_assets  jsonb DEFAULT '[]',
            source         text  NOT NULL,
            metadata       jsonb DEFAULT '{}'
        )
    """)
    op.execute("""
        CREATE TABLE questions (
            id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
            group_id          uuid        REFERENCES question_groups(id),
            group_position    int,
            source            text        NOT NULL,
            source_license    text        NOT NULL DEFAULT 'public',
            year              int,
            slot              int,
            section           text        NOT NULL CHECK (section IN ('QA','VARC','DILR')),
            stem              text        NOT NULL,
            options           jsonb,
            answer_key        jsonb       NOT NULL,
            official_solution text,
            archetype_id      uuid        REFERENCES archetypes(id),
            difficulty_b      numeric,
            difficulty_a      numeric     DEFAULT 1.0,
            attempts_n        int         NOT NULL DEFAULT 0,
            attempts_correct  int         NOT NULL DEFAULT 0,
            embedding_id      uuid,
            quality_flag      text        CHECK (quality_flag IN ('ok','disputed','errata')),
            created_at        timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX questions_source ON questions(source, year, slot, section)")
    op.execute("CREATE INDEX questions_section ON questions(section)")
    op.execute("CREATE INDEX questions_archetype ON questions(archetype_id) WHERE archetype_id IS NOT NULL")
    op.execute("CREATE INDEX questions_options_gin ON questions USING GIN (options) WHERE options IS NOT NULL")
    op.execute("""
        CREATE TABLE question_concepts (
            question_id uuid    NOT NULL REFERENCES questions(id),
            concept_id  uuid    NOT NULL REFERENCES concepts(id),
            weight      numeric DEFAULT 1.0,
            PRIMARY KEY (question_id, concept_id)
        )
    """)
    op.execute("CREATE INDEX question_concepts_concept ON question_concepts(concept_id)")


def downgrade() -> None:
    op.execute("DROP TABLE question_concepts")
    op.execute("DROP TABLE questions")
    op.execute("DROP TABLE question_groups")
