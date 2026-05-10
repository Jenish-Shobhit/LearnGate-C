# Spec 0-2: Database schema & RLS

**Phase:** 0
**Branch:** spec/0-2-database-schema-rls
**Depends on:** 0.1

---

## Goal

By the end of this step, the full Postgres relational schema exists in 12 Alembic migrations that can be applied from scratch (`alembic upgrade head`) or rolled back to nothing (`alembic downgrade base`) without errors. Every user-scoped table enforces row-level security via a `app.user_id` session variable so that application code running as the service role cannot accidentally read another user's rows. A developer starting from a clean Postgres container runs `make migrate` once and gets a fully indexed, policy-protected database ready for Step 0.3 (auth + API shell). The Pydantic mirror of every table lands in `packages/shared/schema.py` so both the API and tests have a single source of structural truth.

---

## Deliverables

- `apps/api/alembic.ini` — Alembic config pointing at `DATABASE_URL` from env
- `apps/api/alembic/env.py` — standard async-compatible env; import `Base` from `learngate.db`
- `apps/api/alembic/versions/0001_users.py`
- `apps/api/alembic/versions/0002_concept_graph.py`
- `apps/api/alembic/versions/0003_archetypes.py`
- `apps/api/alembic/versions/0004_questions.py`
- `apps/api/alembic/versions/0005_mastery.py`
- `apps/api/alembic/versions/0006_sessions.py`
- `apps/api/alembic/versions/0007_plans.py`
- `apps/api/alembic/versions/0008_mocks.py`
- `apps/api/alembic/versions/0009_review.py`
- `apps/api/alembic/versions/0010_events.py`
- `apps/api/alembic/versions/0011_llm_calls.py`
- `apps/api/alembic/versions/0012_tutor_turns.py`
- `apps/api/src/learngate/db.py` — SQLAlchemy `Base`, `async_engine`, `async_sessionmaker`
- `packages/shared/schema.py` — Pydantic v2 models mirroring every table
- `apps/api/tests/integration/test_migrations.py`
- `apps/api/tests/unit/test_schema_pydantic.py`

---

## Implementation plan

### 1. Alembic bootstrap (`apps/api/`)

Create `alembic.ini` with:
```ini
[alembic]
script_location = alembic
file_template = %%(rev)s_%%(slug)s
sqlalchemy.url =   # intentionally blank; overridden in env.py
```

Create `alembic/env.py`:
```python
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from learngate.db import Base
import os

config = context.config
target_metadata = Base.metadata

def run_migrations_online() -> None:
    url = os.environ["DATABASE_URL"]  # injected by make migrate / CI
    engine = create_async_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata,
                          compare_type=True, compare_server_default=True)
        with context.begin_transaction():
            context.run_migrations()
```

Create `apps/api/src/learngate/db.py`:
```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
import os

class Base(DeclarativeBase):
    pass

DATABASE_URL: str = os.environ["DATABASE_URL"]
async_engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=5)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)
```

The `Makefile` `migrate` target must set `DATABASE_URL` from `.env.local` before calling `alembic upgrade head`.

> Decision: All migrations are pure `op.*` calls (no ORM models in migration files) to avoid import issues as models evolve. The `Base.metadata` is used only for `alembic check`.

---

### 2. `0001_users.py` — users table

```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("""
        CREATE TABLE users (
          id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          clerk_id      text UNIQUE NOT NULL,
          email         citext UNIQUE NOT NULL,
          display_name  text,
          exam_date     date,
          target_pct    numeric(5,2),
          hours_per_day numeric(3,1),
          timezone      text NOT NULL DEFAULT 'Asia/Kolkata',
          locale        text NOT NULL DEFAULT 'en-IN',
          graph_version int  NOT NULL DEFAULT 1,
          created_at    timestamptz NOT NULL DEFAULT now(),
          updated_at    timestamptz NOT NULL DEFAULT now(),
          deleted_at    timestamptz
        )
    """)
    op.execute("CREATE INDEX users_clerk ON users(clerk_id)")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_self_isolation ON users
          USING (id = current_setting('app.user_id', true)::uuid)
    """)

def downgrade() -> None:
    op.execute("DROP TABLE users")
```

> Decision: We use `gen_random_uuid()` (UUIDv4) because UUIDv7 requires the `pg_uuidv7` extension which is not available on all Supabase tiers. The UUIDv7 upgrade path is tracked as a future migration once confirmed available.

---

### 3. `0002_concept_graph.py` — concept_graph_versions, concepts, concept_edges

```sql
CREATE TABLE concept_graph_versions (
  version    int PRIMARY KEY,
  notes      text,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE concepts (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  graph_version  int  NOT NULL REFERENCES concept_graph_versions(version),
  slug           text NOT NULL,
  name           text NOT NULL,
  section        text NOT NULL CHECK (section IN ('QA','VARC','DILR')),
  parent_id      uuid REFERENCES concepts(id),
  depth          int  NOT NULL,
  weight_in_exam numeric NOT NULL DEFAULT 0.0,
  half_life_days numeric NOT NULL DEFAULT 14,
  metadata       jsonb NOT NULL DEFAULT '{}',
  UNIQUE (graph_version, slug)
);
CREATE INDEX concepts_section ON concepts(section, graph_version);

CREATE TABLE concept_edges (
  graph_version int  NOT NULL,
  parent_id     uuid NOT NULL REFERENCES concepts(id),
  child_id      uuid NOT NULL REFERENCES concepts(id),
  kind          text NOT NULL CHECK (kind IN ('prereq','related')),
  weight        numeric NOT NULL DEFAULT 1.0,
  PRIMARY KEY (graph_version, parent_id, child_id, kind)
);
```

No RLS on these tables — concept graph is public, user-agnostic data.

---

### 4. `0003_archetypes.py` — archetypes

```sql
CREATE TABLE archetypes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        text UNIQUE NOT NULL,
  name        text NOT NULL,
  section     text NOT NULL CHECK (section IN ('QA','VARC','DILR')),
  description text
);
```

No RLS — archetypes are system-level reference data.

---

### 5. `0004_questions.py` — question_groups, questions, question_concepts

```sql
CREATE TABLE question_groups (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind           text NOT NULL CHECK (kind IN ('rc_passage','dilr_set','lr_set','standalone')),
  shared_text    text,
  shared_assets  jsonb DEFAULT '[]',
  source         text NOT NULL,
  metadata       jsonb DEFAULT '{}'
);

CREATE TABLE questions (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  group_id          uuid REFERENCES question_groups(id),
  group_position    int,
  source            text NOT NULL,
  source_license    text NOT NULL DEFAULT 'public',
  year              int,
  slot              int,
  section           text NOT NULL CHECK (section IN ('QA','VARC','DILR')),
  stem              text NOT NULL,
  options           jsonb,
  answer_key        jsonb NOT NULL,
  official_solution text,
  archetype_id      uuid REFERENCES archetypes(id),
  difficulty_b      numeric,
  difficulty_a      numeric DEFAULT 1.0,
  attempts_n        int NOT NULL DEFAULT 0,
  attempts_correct  int NOT NULL DEFAULT 0,
  embedding_id      uuid,
  quality_flag      text CHECK (quality_flag IN ('ok','disputed','errata')),
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX questions_source ON questions(source, year, slot, section);
CREATE INDEX questions_section ON questions(section);
CREATE INDEX questions_archetype ON questions(archetype_id) WHERE archetype_id IS NOT NULL;
CREATE INDEX questions_options_gin ON questions USING GIN (options);

CREATE TABLE question_concepts (
  question_id uuid NOT NULL REFERENCES questions(id),
  concept_id  uuid NOT NULL REFERENCES concepts(id),
  weight      numeric DEFAULT 1.0,
  PRIMARY KEY (question_id, concept_id)
);
CREATE INDEX question_concepts_concept ON question_concepts(concept_id);
```

No RLS — questions are shared corpus data.

---

### 6. `0005_mastery.py` — mastery, mastery_snapshots

```sql
CREATE TABLE mastery (
  user_id           uuid NOT NULL REFERENCES users(id),
  concept_id        uuid NOT NULL REFERENCES concepts(id),
  graph_version     int  NOT NULL,
  p_known           numeric NOT NULL CHECK (p_known >= 0 AND p_known <= 1),
  alpha             numeric NOT NULL,
  beta              numeric NOT NULL,
  ci_low            numeric,
  ci_high           numeric,
  last_practiced_at timestamptz,
  decayed_at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, concept_id, graph_version)
);
CREATE INDEX mastery_user ON mastery(user_id, graph_version);
ALTER TABLE mastery ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON mastery
  USING (user_id = current_setting('app.user_id', true)::uuid);

-- Weekly snapshot for BKT replay efficiency (§8.2)
CREATE TABLE mastery_snapshots (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users(id),
  snapshot_at timestamptz NOT NULL,
  snapshot    jsonb NOT NULL,   -- {concept_id: {p_known, alpha, beta}}
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, snapshot_at)
);
ALTER TABLE mastery_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON mastery_snapshots
  USING (user_id = current_setting('app.user_id', true)::uuid);
```

---

### 7. `0006_sessions.py` — sessions, attempts

```sql
CREATE TABLE sessions (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id),
  kind          text NOT NULL CHECK (kind IN ('study','drill','pyq','mock','diagnostic','review')),
  plan_block_id uuid,          -- FK added in 0007
  started_at    timestamptz NOT NULL DEFAULT now(),
  ended_at      timestamptz,
  status        text NOT NULL DEFAULT 'active'
                  CHECK (status IN ('active','completed','abandoned','crashed')),
  metadata      jsonb DEFAULT '{}'
);
CREATE INDEX sessions_user_time ON sessions(user_id, started_at DESC);
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON sessions
  USING (user_id = current_setting('app.user_id', true)::uuid);

CREATE TABLE attempts (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users(id),
  session_id    uuid REFERENCES sessions(id),
  question_id   uuid NOT NULL REFERENCES questions(id),
  response      jsonb NOT NULL,   -- {answer, changed_n, flagged, working_text}
  is_correct    bool,
  time_ms       int,
  confidence    int CHECK (confidence BETWEEN 1 AND 5),
  error_type    text CHECK (error_type IN ('conceptual','procedural','careless','time','misread','none')),
  process_grade jsonb,
  near_miss     bool DEFAULT false,
  graded_at     timestamptz,
  idem_key      text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, question_id, idem_key)
);
CREATE INDEX attempts_user_time    ON attempts(user_id, created_at DESC);
CREATE INDEX attempts_user_question ON attempts(user_id, question_id);
ALTER TABLE attempts ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON attempts
  USING (user_id = current_setting('app.user_id', true)::uuid);
```

> Decision: `sessions.plan_block_id` FK is deferred to migration `0007` (after `plan_blocks` exists) via `ALTER TABLE sessions ADD CONSTRAINT ... FOREIGN KEY`. This preserves forward migration order and avoids a circular dependency.

---

### 8. `0007_plans.py` — plans, plan_blocks; backfill FK on sessions

```sql
CREATE TABLE plans (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            uuid NOT NULL REFERENCES users(id),
  generated_by       text NOT NULL,   -- 'planner_v1_heur' | 'planner_v2_llm'
  prompt_version     text,
  horizon_days       int  NOT NULL,
  rationale          jsonb NOT NULL,  -- {assumptions, deltas, target_pct}
  predicted_pct_band jsonb,           -- {low, mid, high}
  created_at         timestamptz NOT NULL DEFAULT now(),
  superseded_at      timestamptz
);
CREATE INDEX plans_user ON plans(user_id, created_at DESC) WHERE superseded_at IS NULL;
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON plans
  USING (user_id = current_setting('app.user_id', true)::uuid);

CREATE TABLE plan_blocks (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id            uuid NOT NULL REFERENCES plans(id),
  day                date NOT NULL,
  ord                int  NOT NULL,
  goal               text NOT NULL,
  block_kind         text NOT NULL CHECK (block_kind IN ('tutor','drill','pyq','review','mock')),
  target_concept_ids uuid[] NOT NULL,
  duration_min       int  NOT NULL,
  status             text NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','done','skipped','rescheduled')),
  rescheduled_to     date
);
CREATE INDEX plan_blocks_plan ON plan_blocks(plan_id, day, ord);
ALTER TABLE plan_blocks ENABLE ROW LEVEL SECURITY;
-- plan_blocks doesn't have user_id directly; join policy via plan ownership
CREATE POLICY user_isolation ON plan_blocks
  USING (EXISTS (
    SELECT 1 FROM plans p
    WHERE p.id = plan_id
      AND p.user_id = current_setting('app.user_id', true)::uuid
  ));

-- Backfill FK: sessions.plan_block_id → plan_blocks.id
ALTER TABLE sessions
  ADD CONSTRAINT sessions_plan_block_fk
  FOREIGN KEY (plan_block_id) REFERENCES plan_blocks(id);
```

---

### 9. `0008_mocks.py` — mock_papers, mocks, mock_state, mock_calibration

```sql
CREATE TABLE mock_papers (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source          text NOT NULL,   -- 'CAT_2024_S1' | 'GEN_2026_04_30_a'
  generated       bool NOT NULL DEFAULT false,
  question_layout jsonb NOT NULL   -- ordered list of section/group/question refs
);

CREATE TABLE mocks (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            uuid NOT NULL REFERENCES users(id),
  paper_id           uuid NOT NULL REFERENCES mock_papers(id),
  started_at         timestamptz,
  ended_at           timestamptz,
  status             text NOT NULL CHECK (status IN ('active','completed','abandoned')),
  scaled_score       jsonb,          -- {QA, VARC, DILR, total}
  predicted_pct_band jsonb,
  metadata           jsonb DEFAULT '{}'
);
CREATE INDEX mocks_user ON mocks(user_id, started_at DESC);
ALTER TABLE mocks ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON mocks
  USING (user_id = current_setting('app.user_id', true)::uuid);

CREATE TABLE mock_state (
  mock_id    uuid PRIMARY KEY REFERENCES mocks(id),
  user_id    uuid NOT NULL REFERENCES users(id),
  state_blob jsonb NOT NULL,    -- xstate snapshot (timer, navigation, answers)
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE mock_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON mock_state
  USING (user_id = current_setting('app.user_id', true)::uuid);

-- Percentile calibration table (CAT official scaling lookup)
CREATE TABLE mock_calibration (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source     text NOT NULL,        -- matches mock_papers.source
  section    text NOT NULL CHECK (section IN ('QA','VARC','DILR','total')),
  raw_score  int NOT NULL,
  percentile numeric(5,2) NOT NULL,
  year       int NOT NULL,
  UNIQUE (source, section, raw_score)
);
```

No RLS on `mock_papers` or `mock_calibration` — system reference data. `mocks` and `mock_state` get user isolation.

---

### 10. `0009_review.py` — open_loops, debriefs, review_cards

```sql
CREATE TABLE open_loops (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES users(id),
  question_id uuid REFERENCES questions(id),
  concept_id  uuid REFERENCES concepts(id),
  note        text,
  status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
  created_at  timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
CREATE INDEX open_loops_user ON open_loops(user_id, status, created_at DESC);
ALTER TABLE open_loops ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON open_loops
  USING (user_id = current_setting('app.user_id', true)::uuid);

CREATE TABLE debriefs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id    uuid UNIQUE REFERENCES sessions(id),
  user_id       uuid NOT NULL REFERENCES users(id),
  summary_md    text NOT NULL,
  mastery_delta jsonb NOT NULL,   -- {concept_id: {before, after}}
  created_at    timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE debriefs ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON debriefs
  USING (user_id = current_setting('app.user_id', true)::uuid);

CREATE TABLE review_cards (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid NOT NULL REFERENCES users(id),
  scope            text NOT NULL CHECK (scope IN ('concept','question')),
  ref_id           uuid NOT NULL,
  state            text NOT NULL CHECK (state IN ('new','learning','review','relearning')),
  stability        numeric,
  difficulty       numeric,
  due_at           timestamptz NOT NULL,
  last_reviewed_at timestamptz,
  UNIQUE (user_id, scope, ref_id)
);
CREATE INDEX review_cards_due ON review_cards(user_id, due_at) WHERE state != 'new';
ALTER TABLE review_cards ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON review_cards
  USING (user_id = current_setting('app.user_id', true)::uuid);
```

---

### 11. `0010_events.py` — events (immutable append-only)

```sql
CREATE TABLE events (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid,           -- null for system events (eval.regression, etc.)
  kind           text NOT NULL,
  schema_version int  NOT NULL,
  payload        jsonb NOT NULL,
  cause_event_id uuid REFERENCES events(id),
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- Primary access pattern: per-user, per-kind, recent-first
CREATE INDEX events_user_kind_time ON events(user_id, kind, created_at DESC);

-- BRIN index for time-range scans; event log is time-ordered so BRIN is efficient
CREATE INDEX events_time_brin ON events USING BRIN (created_at);

-- Partial indexes for hot kinds
CREATE INDEX events_attempt_created ON events(user_id, created_at DESC)
  WHERE kind = 'attempt.created';
CREATE INDEX events_mastery_updated ON events(user_id, created_at DESC)
  WHERE kind = 'mastery.updated';
CREATE INDEX events_tutor_turn ON events(user_id, created_at DESC)
  WHERE kind = 'tutor.turn.completed';

-- GIN for payload queries (e.g., find events by session_id inside payload)
CREATE INDEX events_payload_gin ON events USING GIN (payload);
```

No RLS on events — workers write events with explicit `user_id`; the API filters by `user_id` in queries. This avoids RLS overhead on the highest-write table.

> Decision: Events table deliberately does **not** get RLS. It is append-only; the API and workers always pass `user_id` explicitly in queries and never do wildcard `SELECT * FROM events`. The CI lint rule (Step 4.1) enforces all event queries include a `user_id` filter.

---

### 12. `0011_llm_calls.py` — llm_calls

```sql
CREATE TABLE llm_calls (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid,             -- null for system-level calls (eval runs)
  agent          text NOT NULL,    -- 'tutor' | 'examiner' | 'planner' | ...
  prompt_version text NOT NULL,
  model          text NOT NULL,
  input_tokens   int,
  output_tokens  int,
  cached_tokens  int,
  latency_ms     int,
  cost_usd       numeric(12,6),
  request        jsonb,
  response       jsonb,
  trace_id       text,
  cause_event_id uuid REFERENCES events(id),
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX llm_calls_user_time ON llm_calls(user_id, created_at DESC);
CREATE INDEX llm_calls_agent    ON llm_calls(agent, created_at DESC);
```

No RLS — cost attribution queries are admin/worker scope.

---

### 13. `0012_tutor_turns.py` — tutor_turns

```sql
CREATE TABLE tutor_turns (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id     uuid NOT NULL REFERENCES sessions(id),
  user_id        uuid NOT NULL REFERENCES users(id),
  turn_index     int  NOT NULL,
  move           text NOT NULL,         -- move policy label (§22.2)
  prompt_version text,
  model          text,
  input_text     text,
  output_text    text,
  citations      jsonb NOT NULL DEFAULT '[]',   -- [{question_id, marker}]
  tokens_input   int,
  tokens_output  int,
  cached_tokens  int,
  cost_usd       numeric(12,6),
  latency_ms     int,
  llm_call_id    uuid REFERENCES llm_calls(id),
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, turn_index)
);
CREATE INDEX tutor_turns_session ON tutor_turns(session_id, turn_index);
ALTER TABLE tutor_turns ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON tutor_turns
  USING (user_id = current_setting('app.user_id', true)::uuid);
```

---

### 14. Pydantic mirror — `packages/shared/schema.py`

Create one Pydantic v2 `BaseModel` per table. Every model must be importable without touching the database. Models are **read models** (not ORM; not used for inserts — that stays in the API layer).

```python
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

class UserSchema(BaseModel):
    id: UUID
    clerk_id: str
    email: str
    display_name: Optional[str] = None
    exam_date: Optional[date] = None
    target_pct: Optional[Decimal] = None
    hours_per_day: Optional[Decimal] = None
    timezone: str = "Asia/Kolkata"
    locale: Literal["en-IN", "hi-IN", "hi-en"] = "en-IN"
    graph_version: int = 1
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

class ConceptGraphVersionSchema(BaseModel):
    version: int
    notes: Optional[str] = None
    created_at: datetime

class ConceptSchema(BaseModel):
    id: UUID
    graph_version: int
    slug: str
    name: str
    section: Literal["QA", "VARC", "DILR"]
    parent_id: Optional[UUID] = None
    depth: int
    weight_in_exam: Decimal = Decimal("0.0")
    half_life_days: Decimal = Decimal("14")
    metadata: dict[str, Any] = Field(default_factory=dict)

class ConceptEdgeSchema(BaseModel):
    graph_version: int
    parent_id: UUID
    child_id: UUID
    kind: Literal["prereq", "related"]
    weight: Decimal = Decimal("1.0")

class ArchetypeSchema(BaseModel):
    id: UUID
    slug: str
    name: str
    section: Literal["QA", "VARC", "DILR"]
    description: Optional[str] = None

class QuestionGroupSchema(BaseModel):
    id: UUID
    kind: Literal["rc_passage", "dilr_set", "lr_set", "standalone"]
    shared_text: Optional[str] = None
    shared_assets: list[Any] = Field(default_factory=list)
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)

class QuestionSchema(BaseModel):
    id: UUID
    group_id: Optional[UUID] = None
    group_position: Optional[int] = None
    source: str
    source_license: str = "public"
    year: Optional[int] = None
    slot: Optional[int] = None
    section: Literal["QA", "VARC", "DILR"]
    stem: str
    options: Optional[list[Any]] = None
    answer_key: Any
    official_solution: Optional[str] = None
    archetype_id: Optional[UUID] = None
    difficulty_b: Optional[Decimal] = None
    difficulty_a: Decimal = Decimal("1.0")
    attempts_n: int = 0
    attempts_correct: int = 0
    embedding_id: Optional[UUID] = None
    quality_flag: Optional[Literal["ok", "disputed", "errata"]] = None
    created_at: datetime

class QuestionConceptSchema(BaseModel):
    question_id: UUID
    concept_id: UUID
    weight: Decimal = Decimal("1.0")

class MasterySchema(BaseModel):
    user_id: UUID
    concept_id: UUID
    graph_version: int
    p_known: Decimal = Field(ge=0, le=1)
    alpha: Decimal
    beta: Decimal
    ci_low: Optional[Decimal] = None
    ci_high: Optional[Decimal] = None
    last_practiced_at: Optional[datetime] = None
    decayed_at: datetime

class SessionSchema(BaseModel):
    id: UUID
    user_id: UUID
    kind: Literal["study", "drill", "pyq", "mock", "diagnostic", "review"]
    plan_block_id: Optional[UUID] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    status: Literal["active", "completed", "abandoned", "crashed"] = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)

class AttemptSchema(BaseModel):
    id: UUID
    user_id: UUID
    session_id: Optional[UUID] = None
    question_id: UUID
    response: dict[str, Any]
    is_correct: Optional[bool] = None
    time_ms: Optional[int] = None
    confidence: Optional[int] = Field(default=None, ge=1, le=5)
    error_type: Optional[Literal["conceptual","procedural","careless","time","misread","none"]] = None
    process_grade: Optional[dict[str, Any]] = None
    near_miss: bool = False
    graded_at: Optional[datetime] = None
    idem_key: Optional[str] = None
    created_at: datetime

class PlanSchema(BaseModel):
    id: UUID
    user_id: UUID
    generated_by: str
    prompt_version: Optional[str] = None
    horizon_days: int
    rationale: dict[str, Any]
    predicted_pct_band: Optional[dict[str, Any]] = None
    created_at: datetime
    superseded_at: Optional[datetime] = None

class PlanBlockSchema(BaseModel):
    id: UUID
    plan_id: UUID
    day: date
    ord: int
    goal: str
    block_kind: Literal["tutor", "drill", "pyq", "review", "mock"]
    target_concept_ids: list[UUID]
    duration_min: int
    status: Literal["pending", "done", "skipped", "rescheduled"] = "pending"
    rescheduled_to: Optional[date] = None

class MockPaperSchema(BaseModel):
    id: UUID
    source: str
    generated: bool = False
    question_layout: Any

class MockSchema(BaseModel):
    id: UUID
    user_id: UUID
    paper_id: UUID
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    status: Literal["active", "completed", "abandoned"]
    scaled_score: Optional[dict[str, Any]] = None
    predicted_pct_band: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class MockStateSchema(BaseModel):
    mock_id: UUID
    user_id: UUID
    state_blob: dict[str, Any]
    updated_at: datetime

class MockCalibrationSchema(BaseModel):
    id: UUID
    source: str
    section: Literal["QA", "VARC", "DILR", "total"]
    raw_score: int
    percentile: Decimal
    year: int

class OpenLoopSchema(BaseModel):
    id: UUID
    user_id: UUID
    question_id: Optional[UUID] = None
    concept_id: Optional[UUID] = None
    note: Optional[str] = None
    status: Literal["open", "resolved"] = "open"
    created_at: datetime
    resolved_at: Optional[datetime] = None

class DebriefSchema(BaseModel):
    id: UUID
    session_id: Optional[UUID] = None
    user_id: UUID
    summary_md: str
    mastery_delta: dict[str, Any]
    created_at: datetime

class ReviewCardSchema(BaseModel):
    id: UUID
    user_id: UUID
    scope: Literal["concept", "question"]
    ref_id: UUID
    state: Literal["new", "learning", "review", "relearning"]
    stability: Optional[Decimal] = None
    difficulty: Optional[Decimal] = None
    due_at: datetime
    last_reviewed_at: Optional[datetime] = None

class EventSchema(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    kind: str
    schema_version: int
    payload: dict[str, Any]
    cause_event_id: Optional[UUID] = None
    created_at: datetime

class LlmCallSchema(BaseModel):
    id: UUID
    user_id: Optional[UUID] = None
    agent: str
    prompt_version: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    cost_usd: Optional[Decimal] = None
    request: Optional[dict[str, Any]] = None
    response: Optional[dict[str, Any]] = None
    trace_id: Optional[str] = None
    cause_event_id: Optional[UUID] = None
    created_at: datetime

class TutorTurnSchema(BaseModel):
    id: UUID
    session_id: UUID
    user_id: UUID
    turn_index: int
    move: str
    prompt_version: Optional[str] = None
    model: Optional[str] = None
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    cached_tokens: Optional[int] = None
    cost_usd: Optional[Decimal] = None
    latency_ms: Optional[int] = None
    llm_call_id: Optional[UUID] = None
    created_at: datetime
```

---

### 15. Makefile `migrate` and `migrate-down` targets

Add to the root `Makefile`:
```makefile
migrate:
	cd apps/api && set -a && source ../../.env.local && set +a && \
	  alembic upgrade head

migrate-down:
	cd apps/api && set -a && source ../../.env.local && set +a && \
	  alembic downgrade base

migrate-check:
	cd apps/api && set -a && source ../../.env.local && set +a && \
	  alembic check
```

---

## Acceptance criteria

1. Running `make migrate` against a freshly created Postgres instance (no existing tables) exits 0; running `make migrate-down` then `make migrate` again also exits 0.
2. After `make migrate`, `alembic current` reports `head` and `alembic check` reports "No new upgrade operations detected."
3. `SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1` returns exactly 20 tables: `archetypes`, `attempts`, `concept_edges`, `concept_graph_versions`, `concepts`, `debriefs`, `events`, `llm_calls`, `mastery`, `mastery_snapshots`, `mock_calibration`, `mock_papers`, `mock_state`, `mocks`, `open_loops`, `plan_blocks`, `plans`, `question_concepts`, `question_groups`, `questions`, `review_cards`, `sessions`, `tutor_turns`, `users`. (24 tables total)
4. All 12 migrations are independently reversible: each `downgrade()` undoes its `upgrade()` with no orphaned objects.
5. RLS test — connect as service role, set `SET LOCAL app.user_id = '<user_A_id>'`; insert one row into `attempts` for `user_A`; switch setting to `user_B`; `SELECT COUNT(*) FROM attempts` returns 0.
6. The same RLS isolation test passes for: `mastery`, `sessions`, `plans`, `plan_blocks`, `mocks`, `mock_state`, `open_loops`, `debriefs`, `review_cards`, `tutor_turns`.
7. `python -c "from packages.shared.schema import *"` exits 0 — all models importable.
8. Every Pydantic schema model round-trips through `model.model_validate(model.model_dump())` without exception for a minimal valid instance (no database required).
9. CI migration dry-run step (`alembic upgrade head --sql` piped to review) passes in the GitHub Actions pipeline.

---

## Out of scope

- Seeding any data (concept graph CSV seed is Step 0.4; PYQ ingestion is Step 0.5).
- Alembic autogenerate models (`models.py` ORM file); only `db.py` base and raw DDL are created here. ORM models are added per-module as each agent/service is built.
- The `0013_domains` migration for multi-domain support (Step 5.1).
- ClickHouse schema for analytics (Step 3.2 or later).
- Full PII export/delete workflow (Step 4.1).
- Vector store (Qdrant) collection setup (Step 0.5).

---

## Tests and validation

### Unit tests — `apps/api/tests/unit/test_schema_pydantic.py`

**1. Round-trip: UserSchema**
- Type: `unit`
- File: `tests/unit/test_schema_pydantic.py`
- Setup: Import `UserSchema` from `packages.shared.schema`
- Action: `UserSchema.model_validate({"id": str(uuid4()), "clerk_id": "clerk_abc", "email": "a@b.com", "created_at": now_iso, "updated_at": now_iso})`
- Expected: No exception; `model.email == "a@b.com"`

**2. Round-trip: AttemptSchema with optional fields**
- Type: `unit`
- File: `tests/unit/test_schema_pydantic.py`
- Setup: Build minimal dict with required fields only
- Action: `AttemptSchema.model_validate(minimal_dict)`; then `AttemptSchema.model_validate(a.model_dump())`
- Expected: No exception; `is_correct is None`, `error_type is None`

**3. Validation: MasterySchema rejects p_known out of range**
- Type: `unit`
- File: `tests/unit/test_schema_pydantic.py`
- Setup: None
- Action: `MasterySchema.model_validate({..., "p_known": 1.5, ...})`
- Expected: `pydantic.ValidationError` raised with field `p_known`

**4. Round-trip: all 24 schemas have a valid minimal instance**
- Type: `unit`
- File: `tests/unit/test_schema_pydantic.py`
- Setup: Parametrize with one minimal dict per schema class
- Action: `SchemaClass.model_validate(minimal_dict)` for each
- Expected: Zero exceptions across all 24 models

**5. Validation: AttemptSchema rejects unknown error_type literal**
- Type: `unit`
- File: `tests/unit/test_schema_pydantic.py`
- Setup: None
- Action: `AttemptSchema.model_validate({..., "error_type": "guessed", ...})`
- Expected: `ValidationError` with field `error_type`

---

### Integration tests — `apps/api/tests/integration/test_migrations.py`

Uses `testcontainers-python` to spin up a fresh Postgres 16 container per test session.

**6. All tables created after upgrade**
- Type: `integration`
- File: `tests/integration/test_migrations.py`
- Setup: Start Postgres container; run `alembic upgrade head`
- Action: `SELECT table_name FROM information_schema.tables WHERE table_schema='public'`
- Expected: Result set contains all 24 expected table names

**7. Round-trip migrations (downgrade + upgrade)**
- Type: `integration`
- File: `tests/integration/test_migrations.py`
- Setup: Postgres container; `alembic upgrade head`
- Action: `alembic downgrade base`; `alembic upgrade head`
- Expected: Both commands exit 0; all 24 tables exist again after re-upgrade

**8. RLS isolation — attempts**
- Type: `integration`
- File: `tests/integration/test_migrations.py`
- Setup: Postgres container with migrations applied; insert `user_A` and `user_B` in `users`; insert one `attempts` row for `user_A`
- Action: Open second connection; `SET LOCAL app.user_id = '<user_B_id>'`; `SELECT COUNT(*) FROM attempts`
- Expected: Returns 0

**9. RLS isolation — mastery, sessions, plans**
- Type: `integration`
- File: `tests/integration/test_migrations.py`
- Setup: Same as test 8 pattern; insert one row of each table for `user_A`
- Action: Connect as `user_B` (app.user_id = user_B_id); SELECT COUNT on each table
- Expected: All counts = 0 for all 3 tables

**10. Application-level causality lint (CI check)**
- Type: `integration`
- File: `tests/integration/test_migrations.py`
- Setup: Postgres container; migrations applied; insert a non-entry-point event kind (e.g. `attempt.graded`) with `cause_event_id = NULL`
- Action: Run the causality lint script `scripts/lint_event_causality.py` against the DB
- Expected: Script exits non-zero and reports the violating event id

---

### E2E / Manual smoke test

**11. Fresh-machine `make migrate` smoke**
- Type: `manual`
- File: N/A — checklist in PR description
- Setup: Engineer on a machine with only Docker and `.env.local` populated; no prior Postgres state
- Action: `make migrate`
- Expected: Exit 0; `psql $DATABASE_URL -c '\dt'` shows 24 tables; `alembic current` shows `head`
