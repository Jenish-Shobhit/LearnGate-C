"""Integration tests: Alembic migrations and RLS policies via testcontainers."""
import os
import subprocess
import sys
from uuid import uuid4

import pytest
import psycopg2

pytest.importorskip("testcontainers", reason="testcontainers not installed")
from testcontainers.postgres import PostgresContainer  # noqa: E402

ALEMBIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..")

EXPECTED_TABLES = sorted([
    "archetypes",
    "attempts",
    "concept_edges",
    "concept_graph_versions",
    "concepts",
    "debriefs",
    "events",
    "llm_calls",
    "mastery",
    "mastery_snapshots",
    "mock_calibration",
    "mock_papers",
    "mock_state",
    "mocks",
    "open_loops",
    "plan_blocks",
    "plans",
    "question_concepts",
    "question_groups",
    "questions",
    "review_cards",
    "sessions",
    "tutor_turns",
    "users",
])


@pytest.fixture(scope="module")
def pg_container():
    """Shared container for upgrade + RLS tests (always at head)."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="function")
def pg_container_fresh():
    """Isolated container for round-trip tests; never shared."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


def _run_alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        ["python", "-m", "alembic", *args],
        cwd=ALEMBIC_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    return result


def _get_tables(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        return [row[0] for row in cur.fetchall()]


def _pg_url_sync(container_url: str) -> str:
    """Convert asyncpg URL to psycopg2 URL for direct inspection."""
    return container_url.replace("postgresql+asyncpg://", "postgresql://")


class TestRoundTrip:
    """Uses a fresh isolated container so downgrade/upgrade never affects RLS tests."""

    def test_round_trip_downgrade_then_upgrade(self, pg_container_fresh):
        db_url = pg_container_fresh.get_connection_url()

        up = _run_alembic(db_url, "upgrade", "head")
        assert up.returncode == 0, f"alembic upgrade failed:\n{up.stderr}"

        conn = psycopg2.connect(_pg_url_sync(db_url))
        conn.autocommit = True
        assert _get_tables(conn) == EXPECTED_TABLES
        conn.close()

        down = _run_alembic(db_url, "downgrade", "base")
        assert down.returncode == 0, f"alembic downgrade failed:\n{down.stderr}"

        conn = psycopg2.connect(_pg_url_sync(db_url))
        conn.autocommit = True
        assert _get_tables(conn) == [], "Expected no tables after downgrade"
        conn.close()

        up2 = _run_alembic(db_url, "upgrade", "head")
        assert up2.returncode == 0, f"alembic upgrade failed after downgrade:\n{up2.stderr}"

        conn = psycopg2.connect(_pg_url_sync(db_url))
        conn.autocommit = True
        assert _get_tables(conn) == EXPECTED_TABLES
        conn.close()


class TestMigrations:
    def test_upgrade_creates_all_tables(self, pg_container):
        db_url = pg_container.get_connection_url()
        result = _run_alembic(db_url, "upgrade", "head")
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        conn = psycopg2.connect(_pg_url_sync(db_url))
        conn.autocommit = True
        tables = _get_tables(conn)
        conn.close()

        assert tables == EXPECTED_TABLES

    def test_rls_attempts_user_isolation(self, pg_container):
        db_url = pg_container.get_connection_url()
        _run_alembic(db_url, "upgrade", "head")  # no-op if already at head

        conn = psycopg2.connect(_pg_url_sync(db_url))
        conn.autocommit = True

        user_a = str(uuid4())
        user_b = str(uuid4())

        with conn.cursor() as cur:
            # Insert user_A and user_B
            cur.execute(
                "INSERT INTO users (id, clerk_id, email) VALUES (%s, %s, %s)",
                (user_a, "clerk_a", "a@test.com"),
            )
            cur.execute(
                "INSERT INTO users (id, clerk_id, email) VALUES (%s, %s, %s)",
                (user_b, "clerk_b", "b@test.com"),
            )
            # Insert a question (needed for the FK on attempts)
            q_id = str(uuid4())
            cur.execute(
                "INSERT INTO questions (id, source, section, stem, answer_key) VALUES (%s, %s, %s, %s, %s)",
                (q_id, "TEST", "QA", "What is 2+2?", '{"answer": "4"}'),
            )
            # Insert an attempt for user_A with RLS context set
            cur.execute(f"SET app.user_id = '{user_a}'")
            cur.execute(
                "INSERT INTO attempts (id, user_id, question_id, response) VALUES (%s, %s, %s, %s)",
                (str(uuid4()), user_a, q_id, '{"answer": "A"}'),
            )

            # Switch to user_B — should see 0 rows
            cur.execute(f"SET app.user_id = '{user_b}'")
            cur.execute("SELECT COUNT(*) FROM attempts")
            count = cur.fetchone()[0]

        conn.close()
        assert count == 0, f"RLS isolation failed: user_B saw {count} attempts from user_A"

    def test_rls_mastery_user_isolation(self, pg_container):
        db_url = pg_container.get_connection_url()
        _run_alembic(db_url, "upgrade", "head")  # no-op if already at head
        conn = psycopg2.connect(_pg_url_sync(db_url))
        conn.autocommit = True

        user_a = str(uuid4())
        user_b = str(uuid4())

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, clerk_id, email) VALUES (%s, %s, %s)",
                (user_a, f"clerk_{user_a[:8]}", f"{user_a[:8]}@test.com"),
            )
            cur.execute(
                "INSERT INTO users (id, clerk_id, email) VALUES (%s, %s, %s)",
                (user_b, f"clerk_{user_b[:8]}", f"{user_b[:8]}@test.com"),
            )
            # Seed concept graph version + concept for the FK
            cur.execute("INSERT INTO concept_graph_versions (version) VALUES (1) ON CONFLICT DO NOTHING")
            concept_id = str(uuid4())
            cur.execute(
                "INSERT INTO concepts (id, graph_version, slug, name, section, depth) VALUES (%s, 1, %s, %s, 'QA', 0)",
                (concept_id, f"slug_{concept_id[:8]}", "Arithmetic"),
            )

            cur.execute(f"SET app.user_id = '{user_a}'")
            cur.execute(
                "INSERT INTO mastery (user_id, concept_id, graph_version, p_known, alpha, beta) VALUES (%s, %s, 1, 0.5, 1.0, 1.0)",
                (user_a, concept_id),
            )

            cur.execute(f"SET app.user_id = '{user_b}'")
            cur.execute("SELECT COUNT(*) FROM mastery")
            count = cur.fetchone()[0]

        conn.close()
        assert count == 0, f"RLS isolation failed: user_B saw {count} mastery rows from user_A"

    def test_rls_sessions_user_isolation(self, pg_container):
        db_url = pg_container.get_connection_url()
        _run_alembic(db_url, "upgrade", "head")  # no-op if already at head
        conn = psycopg2.connect(_pg_url_sync(db_url))
        conn.autocommit = True

        user_a = str(uuid4())
        user_b = str(uuid4())

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (id, clerk_id, email) VALUES (%s, %s, %s)",
                (user_a, f"ca_{user_a[:8]}", f"sa_{user_a[:8]}@test.com"),
            )
            cur.execute(
                "INSERT INTO users (id, clerk_id, email) VALUES (%s, %s, %s)",
                (user_b, f"cb_{user_b[:8]}", f"sb_{user_b[:8]}@test.com"),
            )

            cur.execute(f"SET app.user_id = '{user_a}'")
            cur.execute(
                "INSERT INTO sessions (id, user_id, kind) VALUES (%s, %s, 'study')",
                (str(uuid4()), user_a),
            )

            cur.execute(f"SET app.user_id = '{user_b}'")
            cur.execute("SELECT COUNT(*) FROM sessions")
            count = cur.fetchone()[0]

        conn.close()
        assert count == 0, f"RLS isolation failed: user_B saw {count} sessions from user_A"
