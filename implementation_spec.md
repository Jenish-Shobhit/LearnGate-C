# LearnGate-C — Implementation Specification

**Version:** 0.2
**Companion to:** `master_spec.md` (vision/product spec)
**Last updated:** 2026-04-30
**Audience:** engineers building the system end-to-end
**Reading order:** read `master_spec.md` first; cross-references like *(MS §7.2)* point back to it.

This document is the buildable counterpart to the master spec. It assumes the *what* is settled and answers *how it is built*: components, contracts, schemas, algorithms, request flows, failure modes, and milestone exit criteria. Where the master spec leaves a question open, this spec either makes a defensible v1 decision or marks the item explicitly as **DEFERRED**.

The aim is concreteness over comprehensiveness — every section should give an engineer enough to start typing.

---

## 0. Table of contents

- Part I — Architecture (HLD)
  - 1. System context & boundaries
  - 2. Component diagram & deployment
  - 3. Canonical request flows
  - 4. Architectural invariants
- Part II — Data layer (LLD)
  - 5. Storage taxonomy
  - 6. Relational schema
  - 7. Question groups (RC, DILR, LR)
  - 8. Event log design
  - 9. Migration strategy & data lifecycle
- Part III — Knowledge layer (LLD)
  - 10. PYQ ingestion pipeline
  - 11. Concept graph: schema, versioning, evolution
  - 12. Tagging & archetype taxonomy
  - 13. Difficulty calibration (IRT)
  - 14. Vector store contracts
- Part IV — Estimation & planning (LLD)
  - 15. BKT formulation
  - 16. Decay & cross-node lift
  - 17. Mastery → predicted percentile
  - 18. Planner optimization
- Part V — Agents (LLD)
  - 19. Shared agent substrate
  - 20. Diagnostician
  - 21. Planner
  - 22. Tutor
  - 23. Examiner
  - 24. Analyst
  - 25. Coach (phase 2)
- Part VI — Surfaces (LLD)
  - 26. API contract
  - 27. SSE / streaming protocol
  - 28. Frontend architecture
  - 29. Mock interface (state machine)
  - 30. Spaced review & open loops
- Part VII — Platform
  - 31. LLM layer (router, prompts, caching)
  - 32. Background jobs (Temporal)
  - 33. Observability & evals
  - 34. Security, privacy, compliance
  - 35. DevOps & CI/CD
  - 36. Performance & cost engineering
  - 37. Testing strategy
  - 38. Failure modes compendium
- Part VIII — Execution
  - 39. Build sequence (phase 0–5)
  - 40. Open implementation questions
- Appendices A–F (schemas, prompts, sequence diagrams)

---

# Part I — Architecture (HLD)

## 1. System context & boundaries

### 1.1 In-scope, v1
- A web product (desktop + mobile-web) for individual CAT aspirants.
- A multi-agent backend that diagnoses, plans, teaches, examines, and analyzes one student at a time.
- A PYQ corpus (CAT 2010–2025) with concept tags, archetypes, and embeddings.
- A Learner State per user with append-only event history.

### 1.2 Out of scope, v1
- Native mobile apps (PWA only; native deferred to phase 4).
- Group/cohort features (phase 2 social).
- Multi-tenant educator/B2B surfaces (phase 5).
- GMAT/GRE/banking domains (phase 5).
- Webcam proctoring, anti-cheat ML.

### 1.3 External dependencies
| System | Use | Failover |
|---|---|---|
| Anthropic API (Claude Sonnet/Opus) | All agent LLM calls | Provider router with OpenAI fallback for non-grounded tasks; Tutor degrades to scripted mode |
| Clerk | Auth, user identity | Email/password fallback signed by API; degrade to read-only if Clerk down |
| Supabase Postgres | Primary OLTP store | PITR + read replica; manual failover runbook |
| Qdrant (self-hosted) | PYQ + notes vectors | RAG falls back to keyword + concept-tag retrieval; tutor still works, lower quality |
| Cloudflare R2 | PDFs, static assets | Cache TTL + warm replicas |
| Temporal Cloud | Durable workflows | Local fallback queue (SQLite) for nightly tasks during outage |
| Voyage AI / OpenAI embeddings | Embedding generation | Re-queue ingestion; serve cached embeddings |

## 2. Component diagram & deployment

### 2.1 Logical components

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              Web Client                                  │
│   Next.js 15 (App Router, RSC) · Tailwind · shadcn/ui · TanStack Query   │
│   Streaming hooks · KaTeX · xstate (mock) · IndexedDB (mock recovery)    │
└────────────────────┬───────────────────────────────────┬─────────────────┘
                     │ HTTPS (REST + SSE)                │ Clerk SDK
                     ▼                                   ▼
┌──────────────────────────────────────────┐    ┌────────────────────┐
│           API Gateway (FastAPI)          │◄───│    Clerk (Auth)    │
│  /api/v1/* · OpenAPI · SSE · idempotency │    └────────────────────┘
└──┬─────────┬─────────────┬──────┬────────┘
   │         │             │      │
   │         │             │      └─► [Rate limiter / Redis tokens]
   │         │             │
   │         │             ▼
   │         │     ┌─────────────────────────────────┐
   │         │     │   Agent Orchestrator            │
   │         │     │   LangGraph state machines      │
   │         │     │   Diagnostician · Planner ·     │
   │         │     │   Tutor · Examiner · Analyst    │
   │         │     └──┬─────────────┬────────────────┘
   │         │        │             │
   │         │        ▼             ▼
   │         │   ┌──────────┐   ┌──────────────┐
   │         │   │ LLM      │   │ Tools layer  │
   │         │   │ Router   │   │ (pyq.search, │
   │         │   │ Anthropic│   │  problem.gen,│
   │         │   │ +cache   │   │  grader.*,   │
   │         │   └──────────┘   │  mastery.*)  │
   │         │                  └──────┬───────┘
   │         ▼                         │
   │   ┌────────────────────────┐      │
   │   │   Service Layer        │◄─────┘
   │   │   sessions · plans ·   │
   │   │   mocks · review · etc │
   │   └──┬──────────┬──────┬───┘
   │      │          │      │
   ▼      ▼          ▼      ▼
┌────────┐ ┌────────┐ ┌──────┐ ┌──────────┐
│Postgres│ │ Qdrant │ │Redis │ │ R2 / S3  │
│Supabase│ │vectors │ │cache │ │ PDFs/img │
└────────┘ └────────┘ └──────┘ └──────────┘
                              ▲
                              │
                     ┌────────┴────────┐
                     │   Temporal      │
                     │   workers:      │
                     │   ingestion ·   │
                     │   plan regen ·  │
                     │   post-session  │
                     │   analysis ·    │
                     │   FSRS schedule │
                     └─────────────────┘

Observability: OTel → Honeycomb · LLM traces → Langfuse · Logs → Loki
Feature flags: GrowthBook (server SDK + edge eval)
```

### 2.2 Process model
- **API**: 2 Fly machines × 1 GB shared CPU (autoscale 2→8). Single FastAPI app, uvicorn with 2 workers each, async-first.
- **Workers**: separate Fly app `learngate-workers`. 2 machines × 2 GB. Run Temporal worker process subscribed to all task queues. Workers are stateless and horizontally scalable.
- **Web**: Vercel, edge-rendered shell + node-rendered authed routes.
- **Postgres**: Supabase Pro (8 GB, 2 vCPU). PITR. Read replica added in phase 3.
- **Qdrant**: 1 node Hetzner CCX23 (8 vCPU, 32 GB). Replica + replication added when corpus crosses 1 M vectors.
- **Redis**: Upstash global (low cold cost, high read replicas).

### 2.3 Modular monolith (backend)
We deliberately do **not** decompose into microservices in v1.

Reasoning: agents, services, and the Learner State are tightly coupled by domain; a service split now would add network boundaries inside what is fundamentally one transaction. The boundary that matters is **API ↔ Workers** (latency-critical vs. durable), and that already exists. Internal modularity is enforced by package boundaries and a CI lint rule disallowing cross-module imports except via published interfaces.

Module map (`apps/api/src/learngate/`):
```
api/         # FastAPI routers, request DTOs, error mappers
services/    # business orchestration, no LLM calls
agents/      # LangGraph definitions, prompts, schemas
rag/         # ingestion, retrieval, embeddings
mastery/     # BKT, decay, percentile model
planner/     # heuristic + LLM refinement
examiner/    # grading + generation
analyst/     # debrief + delta computation
diagnostic/  # IRT engine, item bank
mocks/       # paper assembly, scoring, calibration
review/      # FSRS, open loops
events/      # event store, replay, snapshotting
llm/         # provider router, prompt registry, cost meter
jobs/        # Temporal workflow + activity definitions
obs/         # OTel, langfuse adapters
auth/        # Clerk verification, RLS context
config.py    # pydantic-settings
```

## 3. Canonical request flows

The four flows below cover ~95% of real traffic. Each is authoritative; deviations require RFC.

### 3.1 Flow A — Tutor turn (latency-critical, streaming)
```
Client                   API                     Orchestrator              LLM/Tools
  │                       │                            │                       │
  │── POST /sessions/{id}/messages ──►                 │                       │
  │   (idempotency-key, message text)                  │                       │
  │                       │── verify JWT, RLS ctx ────►│                       │
  │                       │── load session+last 8 turns│                       │
  │                       │── kickoff Tutor graph     ─►                       │
  │                       │                            │── pyq.search ────────►│
  │                       │                            │◄── top-6 PYQ chunks ──│
  │                       │                            │── llm.stream(claude-sonnet)
  │                       │◄── SSE: token stream ──────┤                       │
  │◄── SSE: token stream ─┤                            │                       │
  │                       │                            │── cite-validate ─────►│
  │                       │                            │── persist turn ──────►│
  │◄── SSE: done ─────────┤                            │                       │
```
Targets: TTFB <800 ms, full turn p50 <4 s, p95 <8 s. Tools layer runs concurrently with LLM stream where possible (e.g., parallel PYQ fetch + system prompt warm-up).

### 3.2 Flow B — Attempt submitted, mastery updated (durable, async tail)
```
Client → POST /sessions/{id}/attempts
  API: validate, idempotent insert into attempts (unique on (session_id, question_id, idem_key))
  API: emit event `attempt.created`
  API: respond 201 with grading stub  ◄── client may show "checking…"
  Background (in-process async task): Examiner.grade_attempt
    → updates attempts.is_correct, error_type, time_ms
    → emits event `attempt.graded`
  Temporal signal to live PostSessionAnalysis workflow (if open)
```
Mastery itself is updated either at session-end (default) or on a per-question basis in **drill mode** (user expects fast feedback loops).

### 3.3 Flow C — Session end → analysis (durable, async)
```
POST /sessions/{id}/end → 202 Accepted, returns workflow_id
Temporal `PostSessionAnalysis(session_id)`:
  activity grade_session()        # examiner final pass
  activity update_mastery()       # bkt updates, batched per concept
  activity detect_regressions()   # |Δp_known| > 0.10 with N≥3
  activity write_debrief()        # analyst LLM call
  activity emit_events()          # session.analyzed, mastery.delta
  signal RegeneratePlan if significant change

Client subscribes to /sessions/{id}/debrief (SSE) or polls /debrief
```

### 3.4 Flow D — Nightly plan regeneration (batched)
```
Temporal schedule "nightly_sweep" @ 02:00 IST
  workflow NightlySweep():
    for each user with activity in last 7d (paged 500/batch):
      child workflow RegeneratePlan(user_id, cause=nightly):
        load Learner State snapshot
        compute heuristic skeleton (LP)
        call planner LLM (Opus) with skeleton
        validate plan schema, persist, supersede previous
        invalidate dashboard cache for user
Cap: 10k users in <30 min by parallelism (200 concurrent activity executions).
```

## 4. Architectural invariants

These are non-negotiable; code review will reject violations.

1. **Single source of behavioral truth: the event log.** Mastery, plans, dashboards are derivable. If an event isn't logged, the action didn't happen.
2. **No agent calls another agent directly.** Coordination is through Learner State + orchestrator. This keeps each agent independently testable.
3. **All LLM outputs are validated against Pydantic schemas before any side effect.** A failed parse triggers one structured retry, then a graceful degradation path.
4. **All LLM prompts live in `agents/<agent>/prompts/` with frontmatter (`prompt_version`, `model`, `eval_suite`).** Inline f-strings are forbidden.
5. **All POSTs that mutate accept an `Idempotency-Key`.** Stored in Redis with 24 h TTL; key collision returns prior response.
6. **All authenticated requests propagate `user_id` into a request-scoped context that RLS enforces.** No service method ignores it.
7. **No cross-module imports except via the module's `__init__` interface.** Lint enforced.
8. **Background work that can fail is a Temporal workflow.** Background work that cannot fail (caches, derived columns) may use FastAPI `BackgroundTasks`.
9. **Cost is metered per LLM call and attributed to a `user_id` and a `cause_event_id`.** Untagged calls fail in CI.

---

# Part II — Data layer (LLD)

## 5. Storage taxonomy

| Store | Role | Why |
|---|---|---|
| Postgres (Supabase) | Authoritative state, events, mastery, attempts | ACID, JSONB, RLS, ecosystem |
| Qdrant | Dense vector retrieval | Filters + payload, self-host control |
| Redis (Upstash) | Idempotency keys, rate limits, response cache, transient session locks | Sub-ms reads, TTL native |
| Cloudflare R2 | PDFs of original papers, generated images, CSV exports | Egress-free, S3-API compatible |
| ClickHouse (phase 3) | Long-horizon analytics queries | Columnar speed for dashboards at scale |

## 6. Relational schema

All tables use UUIDv7 PKs (sortable; ID order ≈ time order, gives free index locality). All have `created_at`/`updated_at` (`updated_at` only where mutable). Soft delete via `deleted_at` only where users see lists (questions, plans, mocks). Events and attempts are immutable.

Core DDL (abridged; full DDL in **Appendix B**):

```sql
-- 6.1 Identity
CREATE TABLE users (
  id              uuid PRIMARY KEY DEFAULT uuidv7(),
  clerk_id        text UNIQUE NOT NULL,
  email           citext UNIQUE NOT NULL,
  display_name    text,
  exam_date       date,
  target_pct      numeric(5,2),
  hours_per_day   numeric(3,1),
  timezone        text NOT NULL DEFAULT 'Asia/Kolkata',
  locale          text NOT NULL DEFAULT 'en-IN',  -- 'en-IN' | 'hi-IN' | 'hi-en'
  graph_version   int NOT NULL DEFAULT 1,         -- which concept graph snapshot they're on
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  deleted_at      timestamptz
);

-- 6.2 Concept graph (versioned)
CREATE TABLE concept_graph_versions (
  version int PRIMARY KEY,
  notes   text,
  created_at timestamptz DEFAULT now()
);
CREATE TABLE concepts (
  id             uuid PRIMARY KEY DEFAULT uuidv7(),
  graph_version  int  NOT NULL REFERENCES concept_graph_versions(version),
  slug           text NOT NULL,
  name           text NOT NULL,
  section        text NOT NULL CHECK (section IN ('QA','VARC','DILR')),
  parent_id      uuid REFERENCES concepts(id),
  depth          int NOT NULL,
  weight_in_exam numeric NOT NULL DEFAULT 0.0,    -- empirical share of question count
  half_life_days numeric NOT NULL DEFAULT 14,
  metadata       jsonb NOT NULL DEFAULT '{}',
  UNIQUE (graph_version, slug)
);
CREATE TABLE concept_edges (
  graph_version int NOT NULL,
  parent_id uuid NOT NULL,
  child_id  uuid NOT NULL,
  kind      text NOT NULL CHECK (kind IN ('prereq','related')),
  weight    numeric NOT NULL DEFAULT 1.0,
  PRIMARY KEY (graph_version, parent_id, child_id, kind)
);

-- 6.3 PYQ corpus
CREATE TABLE question_groups (   -- shared content for RC/DILR/LR
  id          uuid PRIMARY KEY DEFAULT uuidv7(),
  kind        text NOT NULL CHECK (kind IN ('rc_passage','dilr_set','lr_set','standalone')),
  shared_text text,
  shared_assets jsonb DEFAULT '[]',  -- images, tables
  source      text NOT NULL,
  metadata    jsonb DEFAULT '{}'
);
CREATE TABLE questions (
  id              uuid PRIMARY KEY DEFAULT uuidv7(),
  group_id        uuid REFERENCES question_groups(id),
  group_position  int,
  source          text NOT NULL,             -- e.g., 'CAT_2019_S2'
  source_license  text NOT NULL DEFAULT 'public',
  year            int, slot int, section text NOT NULL,
  stem            text NOT NULL,
  options         jsonb,                     -- null for TITA
  answer_key      jsonb NOT NULL,
  official_solution text,
  archetype_id    uuid REFERENCES archetypes(id),
  difficulty_b    numeric,                   -- IRT b-parameter
  difficulty_a    numeric DEFAULT 1.0,       -- IRT a-parameter
  attempts_n      int NOT NULL DEFAULT 0,
  attempts_correct int NOT NULL DEFAULT 0,
  embedding_id    uuid,
  quality_flag    text,                      -- 'ok' | 'disputed' | 'errata'
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE question_concepts (
  question_id uuid, concept_id uuid, weight numeric DEFAULT 1.0,
  PRIMARY KEY (question_id, concept_id)
);
CREATE TABLE archetypes (
  id   uuid PRIMARY KEY DEFAULT uuidv7(),
  slug text UNIQUE NOT NULL,           -- 'tsd_relative_motion', 'parajumble_thematic'
  name text NOT NULL, section text NOT NULL,
  description text
);

-- 6.4 Mastery (materialized; rebuildable from events)
CREATE TABLE mastery (
  user_id     uuid NOT NULL,
  concept_id  uuid NOT NULL,
  graph_version int NOT NULL,
  p_known     numeric NOT NULL CHECK (p_known >= 0 AND p_known <= 1),
  alpha       numeric NOT NULL,        -- beta posterior shape
  beta        numeric NOT NULL,
  ci_low      numeric, ci_high numeric,
  last_practiced_at timestamptz,
  decayed_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, concept_id, graph_version)
);

-- 6.5 Sessions / attempts
CREATE TABLE sessions (
  id            uuid PRIMARY KEY DEFAULT uuidv7(),
  user_id       uuid NOT NULL,
  kind          text NOT NULL CHECK (kind IN ('study','drill','pyq','mock','diagnostic','review')),
  plan_block_id uuid REFERENCES plan_blocks(id),
  started_at    timestamptz NOT NULL DEFAULT now(),
  ended_at      timestamptz,
  status        text NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active','completed','abandoned','crashed')),
  metadata      jsonb DEFAULT '{}'
);
CREATE TABLE attempts (
  id            uuid PRIMARY KEY DEFAULT uuidv7(),
  user_id       uuid NOT NULL,
  session_id    uuid REFERENCES sessions(id),
  question_id   uuid NOT NULL,
  response      jsonb NOT NULL,                  -- {answer, changed_n, flagged, working_text}
  is_correct    bool,
  time_ms       int,
  confidence    int,                             -- 1..5
  error_type    text,                            -- conceptual|procedural|careless|time|misread|none
  process_grade jsonb,                           -- examiner output (see §23)
  near_miss     bool DEFAULT false,
  graded_at     timestamptz,
  idem_key      text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, question_id, idem_key)
);

-- 6.6 Plans
CREATE TABLE plans (
  id            uuid PRIMARY KEY DEFAULT uuidv7(),
  user_id       uuid NOT NULL,
  generated_by  text NOT NULL,                   -- 'planner_v1_heur' | 'planner_v2_llm' ...
  prompt_version text,
  horizon_days  int NOT NULL,
  rationale     jsonb NOT NULL,                  -- structured: {assumptions, deltas, target_pct}
  predicted_pct_band jsonb,                      -- {low, mid, high}
  created_at    timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz
);
CREATE TABLE plan_blocks (
  id          uuid PRIMARY KEY DEFAULT uuidv7(),
  plan_id     uuid NOT NULL REFERENCES plans(id),
  day         date NOT NULL,
  ord         int NOT NULL,
  goal        text NOT NULL,
  block_kind  text NOT NULL,                     -- tutor|drill|pyq|review|mock
  target_concept_ids uuid[] NOT NULL,
  duration_min int NOT NULL,
  status      text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','done','skipped','rescheduled')),
  rescheduled_to date
);

-- 6.7 Mocks
CREATE TABLE mocks (
  id          uuid PRIMARY KEY DEFAULT uuidv7(),
  user_id     uuid NOT NULL,
  paper_id    uuid NOT NULL REFERENCES mock_papers(id),
  started_at  timestamptz, ended_at timestamptz,
  status      text NOT NULL,                     -- active|completed|abandoned
  scaled_score jsonb,                            -- {QA, VARC, DILR, total}
  predicted_pct_band jsonb,
  metadata    jsonb DEFAULT '{}'
);
CREATE TABLE mock_papers (
  id        uuid PRIMARY KEY DEFAULT uuidv7(),
  source    text NOT NULL,                       -- 'CAT_2024_S1' | 'GEN_2026_04_30_a'
  generated bool NOT NULL DEFAULT false,
  question_layout jsonb NOT NULL                 -- ordered list of section/group/question refs
);
CREATE TABLE mock_state (
  mock_id     uuid PRIMARY KEY,
  user_id     uuid NOT NULL,
  state_blob  jsonb NOT NULL,                    -- xstate snapshot (timer, navigation, answers)
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- 6.8 Open loops, debriefs, review cards
CREATE TABLE open_loops (
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  user_id uuid NOT NULL, question_id uuid, concept_id uuid,
  note text, status text DEFAULT 'open',
  created_at timestamptz, resolved_at timestamptz
);
CREATE TABLE debriefs (
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  session_id uuid UNIQUE REFERENCES sessions(id),
  user_id uuid NOT NULL,
  summary_md text NOT NULL,
  mastery_delta jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE review_cards (   -- FSRS state per (user, concept) and per (user, question)
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  user_id uuid NOT NULL,
  scope text NOT NULL,                           -- 'concept' | 'question'
  ref_id uuid NOT NULL,
  state text NOT NULL,                           -- new|learning|review|relearning
  stability numeric, difficulty numeric,
  due_at timestamptz NOT NULL,
  last_reviewed_at timestamptz,
  UNIQUE (user_id, scope, ref_id)
);

-- 6.9 Event log (immutable)
CREATE TABLE events (
  id            uuid PRIMARY KEY DEFAULT uuidv7(),
  user_id       uuid,
  kind          text NOT NULL,                   -- see §8 catalog
  schema_version int NOT NULL,
  payload       jsonb NOT NULL,
  cause_event_id uuid,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX events_user_kind_time ON events(user_id, kind, created_at DESC);

-- 6.10 LLM call log (cost + replay)
CREATE TABLE llm_calls (
  id              uuid PRIMARY KEY DEFAULT uuidv7(),
  user_id         uuid,
  agent           text NOT NULL,
  prompt_version  text NOT NULL,
  model           text NOT NULL,
  input_tokens    int, output_tokens int, cached_tokens int,
  latency_ms      int, cost_usd numeric(12,6),
  request         jsonb, response jsonb,
  trace_id        text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
```

**Indexes worth calling out** (others routine):
- `attempts (user_id, created_at DESC)` — recency feed.
- `attempts (user_id, question_id)` — re-attempt lookup.
- Partial index on `events` for hot kinds (`attempt.created`, `mastery.updated`, `tutor.turn.completed`).
- BRIN on `events.created_at` (event log is time-ordered, BRIN saves space).
- GIN on `questions.options`, `plans.rationale`, `events.payload`.

**RLS policies.** Every user-scoped table gets:
```sql
ALTER TABLE attempts ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_isolation ON attempts USING (user_id = current_setting('app.user_id', true)::uuid);
```
The API sets `app.user_id` per request inside a transaction; service-role connections (workers) skip RLS but pass `user_id` explicitly.

## 7. Question groups (RC, DILR, LR)

CAT has shared-context questions: an RC passage with 4 questions, a DILR set with 4. The data model treats this with `question_groups` (§6.3). Important downstream rules:

- **Serving**: when serving a single question that belongs to a group, the API returns the group payload (`shared_text`, `shared_assets`) once per session; subsequent questions in the same group reuse it (cache key `group:{id}`).
- **Timing**: per-question time is captured, and `group_dwell_time_ms` is computed as the sum of in-group time. Used in process grading (was the student stuck on the *passage* or on *that* question?).
- **Mastery**: each question carries its own `question_concepts` rows. Group-level concept tags are aggregated dynamically (`SELECT DISTINCT concept_id ...`). Mastery updates always go to question-level concepts.
- **Generation**: when the Examiner generates a parallel problem in a group context, it must generate either the whole group or label the new question as standalone. Mixing is not allowed because it confuses telemetry.

## 8. Event log design

The event log is the system's behavioral memory. Mastery, plans, dashboards, and even debriefs are derived from it.

### 8.1 Event kinds (catalog, v1)
| Kind | Producer | Payload (shape) |
|---|---|---|
| `user.created` | API | `{display_name, exam_date, target_pct}` |
| `user.goals.updated` | API | `{before, after}` |
| `diagnostic.started` | API | `{session_id}` |
| `diagnostic.item.served` | Diagnostician | `{session_id, question_id, theta, info}` |
| `diagnostic.item.answered` | API | `{session_id, attempt_id}` |
| `diagnostic.completed` | Diagnostician | `{session_id, mastery_seed, error_profile}` |
| `attempt.created` | API | `{attempt_id, question_id, response, time_ms}` |
| `attempt.graded` | Examiner | `{attempt_id, is_correct, error_type, process_grade}` |
| `mastery.updated` | Analyst | `{concept_id, p_before, p_after, cause}` |
| `mastery.regression` | Analyst | `{concept_id, magnitude}` |
| `session.started` | API | `{session_id, plan_block_id?}` |
| `session.ended` | API | `{session_id, status}` |
| `session.analyzed` | Analyst | `{session_id, debrief_id}` |
| `tutor.turn.completed` | Tutor | `{session_id, move, citations, tokens}` |
| `plan.generated` | Planner | `{plan_id, prompt_version, predicted_pct_band, cause}` |
| `plan.block.completed` | API | `{block_id}` |
| `mock.started` / `mock.ended` / `mock.scored` | Mocks | `{mock_id, ...}` |
| `openloop.flagged` / `openloop.resolved` | API | `{loop_id}` |
| `cost.budget.exceeded` | LLM router | `{period, amount}` |
| `eval.regression` | CI | `{suite, baseline, new}` |

`schema_version` is set per kind; payload schemas live in `events/schemas/<kind>/v<n>.py`. Old payloads are preserved verbatim; readers are version-aware.

### 8.2 Replay & snapshots
- Mastery is rebuildable: replay `attempt.graded` events in order through BKT.
- For tractability we snapshot mastery weekly (`mastery_snapshots` table; not shown above) and replay deltas since the latest snapshot.
- Non-deterministic events (LLM-produced debriefs, plans) are not regenerable on replay — they're persisted as-is. Replay is for derived numeric state, not narrative artifacts.

### 8.3 Causality
Every event carries `cause_event_id`. This makes traces possible without distributed tracing for product-level questions ("why did the planner change today?"). The CI lint forbids producing an event without a cause unless it's an entry-point (user-initiated POST or scheduled trigger).

## 9. Migration strategy & data lifecycle

- **Schema migrations**: Alembic; one revision per PR. CI runs `alembic upgrade head` against a clone of prod schema before merge. Migrations must be backward-compatible for one release (old code must read new schema).
- **Concept graph migrations**: see §11.3.
- **Retention**: events kept 36 months online, then archived to R2 as Parquet (one file per user per month). Attempts and mastery online indefinitely.
- **PII export**: `/me/export` enqueues a workflow that produces a JSON dump (signed URL, 7-day TTL).
- **Right to delete**: `/me/delete` soft-deletes user immediately, full purge at 30 days (events purged, attempts hashed-out, vectors removed). Cohort-level analytics retain only anonymized counts.

---

# Part III — Knowledge layer (LLD)

## 10. PYQ ingestion pipeline

Implemented as Temporal workflow `IngestPaper(source_id)` for full idempotency.

```
1. Fetch source PDF from R2.                          [activity: fetch_pdf]
2. Layout-aware parse (pdfplumber + custom tables).    [activity: parse_pdf]
   Output: list[Page] with text spans + tables + figures (PNG bbox crops).
3. Segment into questions.                              [activity: segment]
   Heuristics: section headers, question numbering ("Q.1", "1."), option blocks.
   Output: list[QuestionDraft].
4. For RC/DILR: detect group boundaries.                [activity: detect_groups]
5. Extract answer key from key PDF (separate doc).      [activity: extract_keys]
6. LLM tagger (Opus, structured output).                [activity: tag_concepts]
   Input: question stem + options + correct answer.
   Output: {concepts:[{slug, weight}], archetype, difficulty_seed, suggested_solution_outline}.
7. SME review queue write (first 100 per section + 5% sample thereafter).  [activity: enqueue_review]
8. Embed (stem + canonical solution summary).            [activity: embed]
9. Upsert into Postgres + Qdrant transactionally.        [activity: persist]
10. Emit event `pyq.ingested`.                           [activity: emit_event]
```

Workflow is idempotent on `source_id`; activities idempotent on `(source_id, question_index)`.

**Failure handling.** Any activity failure pauses the workflow; SME is paged on parser/tagger drift (when ≥10% of items fail validation). No partial paper goes live: a paper either passes review fully or sits in a `staging` Qdrant collection.

## 11. Concept graph

### 11.1 Schema
See §6.2. Forest-of-trees with `prereq` cross-edges. Sections are the roots (QA/VARC/DILR), each with ~150 leaf concepts at v1.

### 11.2 Initial graph (v1)
- Hand-curated by founder + 2 SMEs over 2 weeks.
- Reviewed against AIMCAT/IMS topic lists for completeness.
- ~450 nodes, ~700 edges total. (Fits master spec's "<500 nodes" guidance.)

### 11.3 Graph evolution
Adding/renaming/merging concepts must be safe for live users. Rules:

- **Add**: new nodes get default mastery prior 0.2, except where they have a parent at >0.5 (then prior = parent × 0.7).
- **Rename**: pure metadata change; no mastery migration.
- **Merge (a, b → c)**: combined Beta posterior `Beta(α_a + α_b - α_prior, β_a + β_b - β_prior)`. Loses some information but is conservative.
- **Split (a → a, b)**: copy a's posterior to b with widened CI (multiply variance by 1.5). User does some practice and posterior tightens.
- **Delete**: forbidden in v1; mark `deprecated=true` instead and stop using for new mastery writes.

Each user's `users.graph_version` advances when their mastery has been re-mapped to the new graph. A workflow `MigrateUserToGraphVersion(user_id, target)` runs in the background after every graph release.

## 12. Tagging & archetype taxonomy

### 12.1 Concept tagger
- Model: Claude Opus, JSON-mode, low temp (0.1).
- Output schema:
```python
class ConceptTag(BaseModel):
    slug: str            # must exist in current graph_version
    weight: float        # 0..1; sums approx 1.0 across primary tags
    role: Literal["primary","secondary","supporting"]

class TaggerOutput(BaseModel):
    concepts: list[ConceptTag] = Field(min_items=1, max_items=5)
    archetype_slug: str | None
    difficulty_seed: float = Field(ge=-3, le=3)  # IRT b-scale
    notes: str | None
```
- Validation: `slug` must be in `concepts.slug` for current graph_version; archetype must exist or be null.
- Disagreement: if SME review changes ≥1 tag, the disagreement is logged and used to update the tagger's few-shot bank.

### 12.2 Archetypes
Archetypes are recurring question templates. Examples:
- QA: `tsd_relative_motion`, `mixtures_replacement`, `mod_arithmetic_remainders`, `quad_roots_nature`.
- VARC: `parajumble_thematic_anchor`, `rc_inference_authors_tone`, `rc_main_idea_inverse`, `summary_concise`.
- DILR: `linear_seating`, `bipartite_matching`, `caselet_payoff_table`, `set_visualization_venn`.

~120 archetypes total at v1. They're a coarser layer than concepts and mostly used by the Examiner ("generate one of these") and by analytics ("you're weakest on archetype X").

## 13. Difficulty calibration (IRT)

### 13.1 Model
2-parameter logistic (2PL):
```
P(correct | θ, a, b) = 1 / (1 + exp(-a (θ - b)))
```
- θ: student ability (per section).
- b: question difficulty.
- a: question discrimination (default 1.0 until refit).

Why 2PL not 3PL: guessing parameter is hard to estimate without far more data than we have at v1; we model guess via BKT instead.

### 13.2 Cold start
b-priors, in order of preference:
1. Official CAT difficulty tags (if available).
2. Coaching difficulty estimates (TIME/IMS), licensed and normalized to b-scale.
3. Tagger's `difficulty_seed`.
4. SME panel rating (Likert 1–5 → b ∈ [-2, 2]).

### 13.3 Refit
Nightly job `RefitIRT()` after a question crosses 30 attempts:
- Estimate `(a, b)` via marginal MLE per question, holding student θ fixed (computed from dashboard mastery).
- Lock parameter updates if change <0.1; otherwise version-bump and emit event.
- Recompute student θ per section weekly using the refit parameters.

Population calibration to scaled scores and percentiles: §17.

## 14. Vector store contracts

### 14.1 Collections (Qdrant)
| Collection | Vector source | Payload | Filters |
|---|---|---|---|
| `pyq_questions` | embed(stem + solution summary) | `{question_id, section, archetype, concepts, difficulty_b, year, group_id}` | section, concepts (any), difficulty_b range, year |
| `pyq_solutions` | embed(solution paragraph) | `{question_id, chunk_idx, section}` | section |
| `student_notes` | embed(note text) | `{user_id, scope, ref_id}` | user_id (mandatory) |
| `concepts` | embed(concept name + description) | `{concept_id}` | section |

Embedding model: Voyage `voyage-3-large` (1024 dim). On model upgrade, re-embed entire corpus in a shadow collection, swap atomically.

### 14.2 Retrieval API (tools layer)
```python
class PyqQuery(BaseModel):
    user_id: UUID
    concepts: list[UUID]
    section: Literal["QA","VARC","DILR"]
    difficulty_band: tuple[float,float] = (-1.0, 1.0)
    exclude_recent_days: int = 30
    k: int = 6
    mmr_lambda: float = 0.5

def pyq_search(q: PyqQuery) -> list[QuestionRef]
```
Implementation: top-50 dense → MMR re-rank to k → filter out previously attempted within `exclude_recent_days` (reads `attempts` for that user).

---

# Part IV — Estimation & planning (LLD)

## 15. BKT formulation

Per (user, concept) we maintain:
- `p_known ∈ [0,1]` — current point estimate.
- `(α, β)` — Beta posterior parameters, used to derive CI.
- Constants per concept: `p_slip = 0.1`, `p_guess = 0.2` (MCQ) or `0.05` (TITA), `p_learn = 0.15`. Tuned later from population data.

Update on attempt with outcome `correct ∈ {0,1}`:
```
if correct:
   num = p * (1 - p_slip);  den = num + (1 - p) * p_guess
else:
   num = p * p_slip;        den = num + (1 - p) * (1 - p_guess)
posterior = num / max(den, 1e-9)
p_next = posterior + (1 - posterior) * p_learn
```
Beta update (approximate — fold the binary outcome into Beta for the CI track):
```
if correct: α += 1   else: β += 1
ci_low, ci_high = beta.ppf([0.1, 0.9], α, β)
```
Persist (`p_next`, α, β, `last_practiced_at`).

For DILR/RC group items, attempts contribute to *each* of the question's concept tags weighted by `question_concepts.weight`.

## 16. Decay & cross-node lift

### 16.1 Decay (lazy)
On read or scheduled sweep:
```
days = now() - last_practiced_at
decay = exp(-ln(2) * days / half_life_days)
p_decayed = 0.5 + (p_known - 0.5) * decay      # decays toward indifference, not zero
```
Persisted on next write or in a nightly `DecaySweep` workflow that touches users with `last_practiced_at < now() - interval '7 days'`.

### 16.2 Cross-node lift
After Analyst run, for each newly-mastered concept (`p_known > 0.8`):
```
for each prereq parent p of concept c:
    parent.p_known = min(0.9, parent.p_known + 0.05 * edge_weight)
```
Only applied to *prerequisites* (not related edges). Capped at 0.9 to avoid runaway. Logged as `mastery.updated` events with `cause = "cross_node_lift"` for auditability.

## 17. Mastery → predicted percentile

This is the linchpin algorithm: it makes the Planner's objective measurable.

### 17.1 Per-question correctness model
For a candidate question `q` with concepts `C_q` and difficulty `b_q`:
```
p_known(q) = weighted_avg over c in C_q of mastery[c].p_known     # weights from question_concepts
θ_q = logit(p_known(q))                                          # map [0,1] → ℝ
P(correct | q) = 1 / (1 + exp(-a_q (θ_q - b_q)))
```

### 17.2 Behavioral overlay
We add three behavioral factors derived from session telemetry (rolling 30 days):
- `attempt_rate(section)` — fraction of presented questions the student tries (vs. skips).
- `careless_rate(section)` — share of attempts graded `error_type=careless`.
- `time_pressure_rate(section)` — share with `error_type=time`.

Adjusted P(correct) = `P_irt × (1 − careless_rate) × pressure_factor(time_pressure_rate, q.difficulty_b)`.

### 17.3 Monte Carlo simulation
1. Draw a representative section paper (22 questions per CAT 2024 spec) sampled by section concept distribution and difficulty distribution from PYQs.
2. For each question, sample correct/incorrect from adjusted probability.
3. Compute scaled score using the section's official scoring rule (CAT: +3/-1 for MCQ, +3/0 for TITA).
4. Sum across sections.
5. Repeat 1000 times. Report mean ± 80% interval.

### 17.4 Scaled → percentile
A `mock_calibration` table (per section, fitted nightly from population mock attempts and historical CAT cutoffs) maps scaled score → predicted percentile. CI on score becomes CI on percentile.

### 17.5 Cold start (no population data)
Use the 2024 official CAT score-to-percentile table baseline. Replace with our calibration once N>5k mocks done.

## 18. Planner optimization

### 18.1 Inputs
- Mastery vector (with CIs).
- Behavioral overlay (above).
- Days-to-exam, hours/day available, recent adherence (% of planned blocks completed).
- Open loops (must touch in next 7 days).
- Last 14 days of attempts (summary stats: attempts/day, accuracy/section).
- Calendar constraints: weekend extra hours, declared blackout days.

### 18.2 Heuristic skeleton (solver)

We don't run a full continuous LP; the structure is naturally discrete (study slots).

- Discretize the 7-day horizon into 30-min slots: `K = 7 × hours_per_day × 2` slots.
- Decision variables: assignment of each slot to one of `(concept, mode)` ∈ Concepts × {tutor, drill, review} or `mock` or `rest`.
- Objective: maximize Δ predicted_percentile over horizon.
- Constraints:
  - At least one `mock` slot in horizon if days_to_exam < 60.
  - Concepts with prereqs `<0.6` mastery require ≥1 prereq slot earlier in the same day.
  - No concept gets >25% of weekly slots (diversification).
  - Spaced review schedule from FSRS (§30): cards due today must be allocated.
- Algorithm: greedy seed (sort concepts by `expected_lift_per_minute` desc; fill slots from highest), then 2-opt local search (swap pairs of slots if Δ predicted_percentile > 0). Converges in <2s for 7-day horizon.

`expected_lift_per_minute(c)` ≈ saturating function: `weight_in_exam(c) × Φ(p_known(c)) × decay_urgency(c)`. Φ is a saturating curve peaking at p_known≈0.5 (most marginal value).

### 18.3 LLM refinement (Opus)
Inputs: heuristic skeleton + last 7 days session logs + open loops + adherence pattern.
Output (validated):
```python
class PlanBlockOut(BaseModel):
    day: date
    ord: int
    goal: str
    block_kind: Literal["tutor","drill","pyq","review","mock"]
    target_concept_slugs: list[str]    # validated against current graph
    duration_min: int = Field(ge=10, le=180)
    rationale: str

class PlanOut(BaseModel):
    horizon_days: int = Field(ge=1, le=14)
    blocks: list[PlanBlockOut]
    predicted_pct_band: tuple[float, float, float]  # low, mid, high
    assumptions: list[str]
    risks: list[str]
```

The LLM is allowed to: rename goals to be more specific, swap PYQ pickings, reorder within a day, suggest a rest day. The LLM is **not** allowed to: change the total minute budget, drop FSRS-due reviews, override prereq constraint. A post-validator enforces this.

### 18.4 Triggers
- Nightly sweep (default).
- On `mock.scored` event with sectional swing > 5 percentile points.
- On `mastery.regression` event.
- On 2+ consecutive `session.skipped` days.
- On user-initiated `/plan/regenerate`.

### 18.5 Stickiness rule
Don't regenerate within 6 hours of last regeneration unless user-initiated. Avoids plan-flicker.

---

# Part V — Agents (LLD)

## 19. Shared agent substrate

Every agent is a LangGraph `StateGraph` with:
- Typed input (Pydantic) and typed output.
- A standard `AgentRun` envelope:
  ```python
  class AgentRun(BaseModel):
      agent_id: str
      version: str            # bump on logic change
      prompt_version: str     # frontmatter from prompt file
      model: str
      seed_event_id: UUID     # cause
      started_at: datetime
      ended_at: datetime | None
      status: Literal["pending","completed","failed","degraded"]
      cost_usd: float
  ```
- Required hooks: `on_start`, `on_node_complete`, `on_error`, `on_finish` — all emit events through the `events` module.

Code layout:
```
agents/
  base/  graph.py  validators.py  retries.py
  diagnostician/  graph.py  irt.py  prompts/  schemas.py
  planner/        graph.py  heuristic.py  prompts/  schemas.py
  tutor/          graph.py  policy.py  prompts/  schemas.py
  examiner/       graph.py  graders.py  generators.py  prompts/  schemas.py
  analyst/        graph.py  detectors.py  prompts/  schemas.py
  coach/          (phase 2)
```

Validation contract: every LLM-producing node passes its output through Pydantic's `model_validate` before any side effect. Failures cause one structured re-prompt with the validator's error message inlined; second failure triggers the agent's degraded path.

## 20. Diagnostician

**Responsibility:** in 60–90 minutes, produce a v0 mastery vector and an error-type profile.

### 20.1 Multi-section orchestration
Three sub-diagnostics (QA, VARC, DILR) run sequentially. Student picks order; default is the order they declared as weakest first (highest-info on prep target).

Per-section budget: 25 minutes target, 35 max.

### 20.2 IRT engine
- Item bank: balanced across difficulty `b ∈ [-2, 2]` in 0.25 steps and across concepts. ~80 items per section (curated from CAT 2010–2018 to avoid contamination with practice content).
- Initial θ = 0 (median ability).
- Item selection: maximum Fisher information at current θ̂, with a coverage constraint — avoid >2 items from the same concept until each top-level concept area has been touched.
- Stopping rule: `SE(θ̂) < 0.3` OR 25 items OR 35 minutes per section.

### 20.3 Seeding mastery vector
After diagnostic ends, for each leaf concept `c`:
- If `c` was probed: `p_known(c) = sigmoid(θ̂_section + (b_low_for_c - b_passed_threshold))` clamped to [0.05, 0.95].
- If not probed: `p_known(c) = 0.5 × sigmoid(θ̂_section)` (broad prior tied to section ability).
- Beta posterior initialized with effective sample size 5 (so subsequent attempts move it).

### 20.4 Post-test narrative
Single Sonnet call producing the student's first-impression debrief, strict template:
```
Section strengths (1–2 sentences each)
Two specific gaps with evidence (cite question ids)
Tomorrow's first session preview
What you can ignore for now
```
Tone: confident, specific, no platitudes.

### 20.5 UI hooks
Diagnostic is broken into ≥3 sittings allowed: state persists between sessions. Progress bar visible. After each section the user sees a 2-line preview ("you handled QA confidently — let's see VARC").

## 21. Planner — see §18

(Duplicate avoided.) Implementation modules:
- `planner/heuristic.py` — slot allocation algorithm.
- `planner/refine.py` — Opus call + post-validator.
- `planner/percentile.py` — Monte Carlo from §17.

## 22. Tutor

The latency-critical agent. Streamed, Socratic, RAG-grounded, citation-required.

### 22.1 State
```python
class TutorState(BaseModel):
    user_id: UUID
    session_id: UUID
    plan_block: PlanBlock
    history: list[TutorTurn]      # last 8 turns
    candidate_pyqs: list[QuestionRef]
    last_attempt: Attempt | None
    move_decision: TutorMoveDecision | None
    streamed_text: str
    citations: list[Citation]
```

### 22.2 Move policy
Deterministic-first; LLM only where it adds value. Pseudocode:
```python
def decide_move(state):
    if not state.history:
        return Move.OPEN_WITH_FRAMING
    if state.last_attempt and not state.last_attempt.is_correct:
        eg = state.last_attempt.error_type
        if eg == "conceptual":
            return Move.PROBE_MISCONCEPTION
        if eg in ("careless","time"):
            return Move.NORMALIZE_AND_RETRY
    if streak_correct(state) >= 2 and within_first_60pct_time(state):
        return Move.SHOW_HARDER_PYQ
    if streak_incorrect(state) >= 3:
        return Move.ESCAPE_WITH_WORKED_EXAMPLE
    if elapsed > target_duration:
        return Move.WRAP_UP
    return Move.LLM_FREE_CHOICE   # narrow set: ASK | EXPLAIN | SHOW_PYQ
```
For `LLM_FREE_CHOICE`, a Sonnet call returns one of three moves with rationale. JSON-mode, schema-validated.

### 22.3 Graph
```
START → load_context → decide_move → (branch by move) → record_turn → END
   load_context fans out: history fetch, RAG search, open-loop fetch (parallel)
   each move node either streams a response or emits a card
```

### 22.4 Streaming protocol (SSE)
Event grammar:
```
event: token       data: {"text": "..."}
event: citation    data: {"kind":"pyq","ref":"<question_id>","span":[start,end]}
event: card        data: {"type":"question","question_id":"...","options":[...]}
event: move        data: {"move":"SHOW_PYQ","rationale":"..."}
event: tool_call   data: {"name":"problem.generate","status":"started"}
event: error       data: {"code":"...","message":"..."}
event: done        data: {"turn_id":"...","cost_usd":0.0123}
```
Order: `move` (immediately) → tokens interleaved with `citation` markers → optional `card`s → `done`.

### 22.5 Citation discipline
Every factual claim sentence must reference a `question_id` or `concept_note_id`. Implementation:
- The LLM is prompted to emit citations inline as `[[cite:pyq:UUID]]` within text.
- A post-stream validator parses out citations, attaches them to spans, strips the markers from the user-visible text. If a sentence flagged "factual" by a lightweight classifier (regex + 60M-param classifier from HF) lacks any citation in its window, the response is short-stopped and re-prompted with a stronger guard.
- Failure mode: if even on retry citations are missing, the system emits a degraded response from a templated explainer keyed on concept slug.

### 22.6 Prompt caching
- System prompt + concept graph summary + style guide (~6k tokens) marked `cache_control: ephemeral`. Stable across sessions; ~80% expected cache hit.
- Per-user RAG context is the cache-busting suffix.

### 22.7 Persistence
Each turn writes a row to a `tutor_turns` table (omitted in §6 for brevity; see Appendix B) and emits `tutor.turn.completed`. Turns are immutable.

### 22.8 Locale (English / Hinglish)
- `users.locale` drives a system-prompt addendum (`"You may use Hinglish (Hindi-English code-switch) where natural."` for `hi-en`).
- Math & technical terms always rendered in English regardless of locale.
- Locale change re-renders next turn only; history isn't translated.

## 23. Examiner

Two responsibilities: **grade** and **generate**.

### 23.1 Grading

Deterministic grading first:
```python
def grade_mcq(q, response) -> GradeResult:
    correct = response["answer"] == q.answer_key["value"]
    return GradeResult(is_correct=correct, time_ms=response["time_ms"], ...)
```

Process grading (Sonnet) augments — produces a structured judgement on *how* the student got there:
```python
class ProcessGrade(BaseModel):
    method_correct: Literal["yes","partial","no","unknown"]
    error_type: Literal["conceptual","procedural","careless","time","misread","none"]
    near_miss: bool                    # wrong answer was a designed trap
    concepts_struggled: list[str]      # concept slugs
    rationale_md: str
```
Inputs: question + correct answer + student's answer + working text (if captured) + time_ms + (optionally) student's confidence.

Process grading is async and not on the hot path; UI shows immediate correct/incorrect and updates with process grade ~1s later.

### 23.2 Mock grading
Whole-paper grader runs as a single workflow activity:
- Per-question grade (deterministic).
- Sectional scaled score per CAT scoring rules.
- Predicted percentile via §17.4 calibration table.
- "What if" precomputed: for each attempted question, the score if that question were skipped (used by the simulator).

### 23.3 Generation

Two paths:

**Templated generation (preferred where possible).**
- For QA archetypes with parameterizable structure (TSD, mixtures, percentages, mod arithmetic), a template language defines variable bindings and constraints. Example (TSD relative motion):
  ```yaml
  template: tsd_relative_motion
  vars:
    v_a: int 30..80
    v_b: int 20..70
    distance: int 100..400
  constraints:
    - v_a != v_b
  stem: "Two trains start from points A and B... A at {v_a} kmph and B at {v_b} kmph..."
  answer: "{distance / (v_a + v_b)} hours"
  ```
- Solved deterministically; difficulty estimated by parameter ranges via a regression on PYQ b-values.

**LLM generation (fallback).**
- Used for VARC (RC passages, parajumbles) and novel DILR sets.
- Sonnet generates draft; Opus QA-checks: (a) exactly one defensible answer, (b) no off-topic content, (c) difficulty in target band.
- Failures are not shown to students; quality gate retries up to 3×.

All generated questions have `source = 'GEN_<id>'` and a flag `quality.review_status = 'auto_passed' | 'sme_reviewed'`. Until the LLM-generation quality eval crosses a threshold (target: 95% pass rate), generated questions are only used for drill mode, never for mocks or diagnostic.

## 24. Analyst

### 24.1 Trigger
- After every session (Temporal `PostSessionAnalysis`).
- After every mock (`PostMockAnalysis`).
- Daily idle-summary for users active in last 7d but no session today (one-line trend update).

### 24.2 Steps
1. Pull all attempts since last analyst run for this user.
2. Recompute BKT updates (batched per concept).
3. Apply decay (cheap on read, but explicit here for changed concepts).
4. Apply cross-node lift.
5. Detect regressions: any concept where p_known dropped >0.10 with ≥3 graded attempts.
6. Detect divergences: |predicted_delta − actual_delta| > 0.10 on planner predictions; logged for prompt iteration.
7. Generate debrief (Sonnet, ≤250 words) — strict template, no rambling.
8. Persist `debriefs` row, emit `session.analyzed` / `mastery.updated` events.

### 24.3 Debrief template
```
Headline (1 sentence, what changed): "{concept} is up from {x}% to {y}%."
Wins (1–2 bullets, each citing question ids).
Drags (1–2 bullets, with the specific error types).
Tomorrow's pivot (one sentence): the planner is likely to do X.
```

## 25. Coach (phase 2)

DEFERRED, but architecture provisions:
- Reads `session.*`, `mock.*`, and adherence stats.
- Outputs at most one nudge per 24h via push/email.
- Daily decision is structured: `{should_nudge, channel, content_template, target_time}`.
- All nudges are events, allowing downstream A/B analysis.

---

# Part VI — Surfaces (LLD)

## 26. API contract

REST + SSE, versioned at `/api/v1`. OpenAPI generated by FastAPI; client types via `openapi-typescript`.

### 26.1 Endpoint catalog (selected)

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/auth/sync` | Upsert user from Clerk JWT |
| GET  | `/me` | Profile + goals |
| PATCH| `/me` | Update goals (`exam_date`, `target_pct`, `hours_per_day`, `timezone`, `locale`) |
| POST | `/diagnostic/start` | `{section_order?: ["QA","VARC","DILR"]}` → `{session_id}` |
| GET  | `/diagnostic/{id}/next` | Next item or `done` |
| POST | `/diagnostic/{id}/answer` | `{question_id, response, time_ms}` |
| GET  | `/plan/current` | Current plan with blocks |
| POST | `/plan/regenerate` | Enqueue regen, returns workflow id |
| POST | `/plan/blocks/{id}/start` | Start a session for this block |
| POST | `/sessions` | `{kind, plan_block_id?}` → `{id}` |
| POST | `/sessions/{id}/messages` | SSE stream, body `{text}` |
| POST | `/sessions/{id}/attempts` | `{question_id, response, time_ms, confidence?}` |
| POST | `/sessions/{id}/end` | 202 Accepted |
| GET  | `/sessions/{id}/debrief` | SSE or polled |
| GET  | `/mastery` | `{ [concept_slug]: { p, ci_low, ci_high, last_practiced_at } }` |
| GET  | `/analytics/trends?range=30d` | Series for charts |
| POST | `/mocks/start` | `{paper_id?}` → `{mock_id}` |
| POST | `/mocks/{id}/state` | `{state_blob}` (autosave) |
| POST | `/mocks/{id}/end` | Submit mock |
| GET  | `/mocks/{id}/analysis` | Post-mock analysis |
| POST | `/openloops` | Flag a doubt |
| GET  | `/openloops` | List |
| POST | `/review/answer` | Spaced review answer |
| GET  | `/review/due` | Due cards today |

### 26.2 Conventions
- Auth: Clerk JWT in `Authorization: Bearer …`.
- Idempotency: any mutation accepts `Idempotency-Key`. Stored in Redis 24h.
- Errors: RFC 7807 `application/problem+json`. Codes namespaced by domain (`mastery.not_found`, `tutor.budget_exceeded`).
- Rate limits: per-user 60 req/min general, 20 req/min on `/sessions/*/messages`. Bucketed in Redis.
- Pagination: cursor-based (`?after=<event_id>&limit=50`). Never offset.
- Versioning: `/api/v1` is stable for 12 months past v2 release; deprecation headers from launch of v2.

## 27. SSE / streaming protocol

### 27.1 Connection lifecycle
- Client opens `EventSource` (with `Authorization` carried via custom fetch + WHATWG streams polyfill on iOS).
- Server flushes a `connected` event with `turn_id`.
- Heartbeat: server emits `: keepalive\n\n` every 15 s.
- Reconnect: client passes `Last-Event-ID`; server resumes from buffer (Redis list, 5 min retention).

### 27.2 Backpressure
SSE is unidirectional. We buffer up to 64 KB per stream in Redis; if exceeded (rare), the server emits an `error: backpressure` and closes — the client retries via a fresh POST.

### 27.3 Token order guarantees
- Tokens within a single move are strictly ordered.
- Citations are emitted *immediately after* their associated text token (or windowed within the same sentence boundary). Client renders citation chip after the sentence completes.

## 28. Frontend architecture

### 28.1 Tech
- Next.js 15 App Router (RSC + streaming for static surfaces, client components for interactive).
- TanStack Query for server state.
- shadcn/ui + Tailwind for design system.
- KaTeX for math; rehype pipeline for question rendering.
- xstate for the mock interface.
- IndexedDB (`idb-keyval`) for: mock answers buffer, open-loop drafts, last-known plan.

### 28.2 Routing
```
app/
  (marketing)/     # public landing
  (app)/
    layout.tsx     # auth-guarded shell
    dashboard/page.tsx
    plan/page.tsx
    session/[id]/page.tsx        # tutor UI
    drill/page.tsx
    mock/[id]/page.tsx           # mock interface
    mock/[id]/analysis/page.tsx
    analytics/page.tsx
    review/page.tsx
    open-loops/page.tsx
    settings/page.tsx
```

### 28.3 Critical components
- `TutorChat` — streaming hook, citation chips, question cards, working-pad.
- `MasteryHeatmap` — D3 force-directed layout of concept graph; virtualized labels; color = `p_known`, opacity = CI width.
- `MockInterface` — pixel-faithful CAT replica. Section tabs locked per CAT rules (within-section flexible, between-section sequential). Question palette with status colors (answered, marked-for-review, visited-not-answered, not-visited). Built on xstate so transitions are predictable and replayable.
- `WhatIfSimulator` — server-precomputed deltas (`/mocks/{id}/analysis`); client toggles questions on/off; recomputes locally from a small lookup.
- `WorkingPad` — capture rough work as text + drawing (canvas → SVG). Sent with attempt for process grading.

### 28.4 Performance budgets
- LCP <1.8 s on 4G (dashboard).
- Tutor TTFB → first token rendered <900 ms.
- JS for app shell <180 KB gz.
- Mock interface keypress→echo <100 ms (no debounce, direct state machine transitions).

### 28.5 Math & diagrams
- Math: KaTeX server-side render where possible; client-side hydration for dynamic content.
- Pre-stored figures (PNGs from PDFs) for PYQs. Generated diagrams (geometry) drawn via `mafs` or vanilla SVG; LLM emits a typed draw spec, not raw SVG. (Avoids unsafe SVG.)

### 28.6 PWA
- Installable manifest, offline shell, IndexedDB-backed plan view.
- Mock interface explicitly *online-only* (timer integrity); attempts to start offline show a friendly block.

## 29. Mock interface (state machine)

State machine (xstate), simplified:
```
states:
  idle
  loading_paper
  ready_to_start
  in_section: { type: 'parallel', states: { timer, navigation, answer_buffer } }
  section_break (only when student finishes section early)
  submitted
  crashed_recovery
events:
  START, ANSWER, CHANGE_ANSWER, MARK_FOR_REVIEW, NAVIGATE, NEXT_SECTION, SUBMIT, TICK, OFFLINE, ONLINE, RESUME
guards:
  can_navigate_within_section, section_time_remaining, all_sections_complete
```

### 29.1 Timer integrity
- Timer ticks client-side (1s) and server-side (every 15 s autosave verifies remaining time).
- Source of truth: server. On reconnect, server's `time_remaining` overrides client's.
- Pause is **not** allowed (mirrors real CAT). If user disconnects, time still elapses.

### 29.2 Persistence
- Every navigation, answer change, and TICK at 15s cadence emits `POST /mocks/{id}/state` with the full state blob.
- Client also stores in IndexedDB; on `OFFLINE` event we queue mutations and replay on reconnect.
- On reload mid-mock, client fetches `GET /mocks/{id}/state`, hydrates xstate, resumes.

### 29.3 Submission
- On `SUBMIT` (manual or timeout), state transitions to `submitted` and `POST /mocks/{id}/end` is called with final state.
- Server triggers `PostMockAnalysis` workflow.
- Client navigates to analysis route which subscribes via SSE for the analysis-ready event.

## 30. Spaced review & open loops

### 30.1 FSRS for spaced review
- We use FSRS-4.5 with default parameters (re-fit when N>5k cards/user).
- Per (user, concept) and per (user, question) cards.
- States: `new | learning | review | relearning`.
- Daily review queue = cards with `due_at < now()`, capped at 30 per day (configurable).
- Planner inserts review blocks first, then fills with new content.

### 30.2 Open loops
- User flags a question or concept mid-session ("I don't get this").
- Stored in `open_loops` with status `open`.
- Resurfacing rule: surfaced again in the *next* tutor block targeting any of the question's concepts, OR after 7d, whichever first.
- Resolution: marked `resolved` automatically when the user answers a parallel question correctly within 30s, or manually by the user.

---

# Part VII — Platform

## 31. LLM layer

### 31.1 Provider router
A thin layer over the Anthropic SDK with a stable interface:
```python
class LLM(Protocol):
    async def complete(self, *, messages, model, schema=None, stream=False, cache_control=None, user_id, agent, prompt_version, cause_event_id) -> CompletionResult
```
Implementations: `AnthropicLLM` (primary), `OpenAILLM` (fallback for non-grounded tasks). Routing decided per-call; **never silently swap providers on the Tutor or Examiner grading paths** (citation grammar differs).

### 31.2 Model defaults
| Agent | Model | Why |
|---|---|---|
| Tutor (free choice + streaming) | Claude Sonnet 4.6 | Latency + cost |
| Examiner (process grading) | Claude Sonnet 4.6 | Cheap structured output |
| Examiner (problem QA) | Claude Opus 4.7 | Quality matters more than cost |
| Analyst (debrief) | Claude Sonnet 4.6 | Templated, doesn't need depth |
| Planner (refinement) | Claude Opus 4.7 | Reasoning over heterogeneous inputs |
| Diagnostician (narrative) | Claude Sonnet 4.6 | Templated |
| Tagger (ingestion) | Claude Opus 4.7 | One-time per question; quality compounds |

### 31.3 Prompt registry
- Each prompt: `agents/<agent>/prompts/<name>.md` with frontmatter:
  ```
  ---
  prompt_version: tutor.free_choice.2026-04-30
  model: claude-sonnet-4-6
  inputs: [history, candidate_pyqs, plan_block]
  output_schema: TutorMove
  eval_suite: tutor_grounding
  ---
  ```
- Loaded at startup; immutable in memory; bumping version requires a new file (no in-place edits).
- Prompt promotion gate: a new version cannot replace its predecessor unless the relevant eval suite scores ≥ baseline AND no related suite regresses by >2% (CI-enforced).

### 31.4 Caching
- **Prompt prefix cache** (Anthropic ephemeral cache_control): system + concept graph summary + style guide. ~6k tokens. Target ~80% hit rate.
- **Response cache** (Redis, keyed by hash of `(prompt_version, model, concrete_messages)`):
  - Tutor "intro to PYQ X" cached 24h.
  - Examiner process grade cached on `(question_id, response_hash)`. Big wins for common wrong-answer trap options.
- Never cache user-specific reasoning that depends on Learner State; only cache content-only outputs.

### 31.5 Cost guardrails
- Per-call cost computed from token counts × pricing table.
- Per-user soft circuit breaker at $1/day: subsequent Tutor calls force Sonnet-only mode and disable problem generation (use bank only). Hard breaker at $3/day pauses LLM calls and surfaces a "system is rebalancing, try again in 1h" notice.
- Per-prompt-version budget caps (e.g., Planner refinement <$0.05/user/run).

## 32. Background jobs (Temporal)

Workflow catalog:
| Workflow | Schedule / Trigger | Activities |
|---|---|---|
| `IngestPaper(source_id)` | manual | fetch_pdf, parse, segment, detect_groups, extract_keys, tag, embed, persist |
| `RegeneratePlan(user_id, cause)` | nightly + signals | load_state, heuristic_skeleton, llm_refine, validate, persist |
| `PostSessionAnalysis(session_id)` | session-ended signal | grade_session, update_mastery, detect_regressions, write_debrief |
| `PostMockAnalysis(mock_id)` | mock-ended signal | grade_mock, predict_percentile, build_what_if, write_analysis |
| `RebuildMastery(user_id)` | manual / migration | replay events from latest snapshot |
| `MigrateUserToGraphVersion(user_id, target)` | on graph release | remap mastery, update users.graph_version |
| `RefitIRT()` | nightly | per-question MLE refit |
| `DecaySweep()` | nightly | apply lazy decay to stale users |
| `FSRSDailyTick()` | nightly | recompute due cards |
| `EvalNightly()` | nightly | run full eval suites |
| `NightlySweep()` | cron 02:00 IST | enqueues child workflows for active users |

Activity contracts: idempotent, retried with exponential backoff (max 5 attempts), timeouts declared per activity. Workflow code is pure Python without I/O — all I/O lives in activities.

## 33. Observability & evals

### 33.1 Tracing
- OpenTelemetry across API, agents, workers. Trace headers propagated via Temporal too.
- LLM calls: each is a Langfuse span with prompt, response, model, tokens, cost, latency, prompt_version. Linked to the parent OTel trace.

### 33.2 Metrics (Prometheus, exported to Honeycomb derivatives)
- API: RED per route, error type breakdown.
- Tutor: TTFB, full-turn duration, citation-failure rate, post-filter retry rate.
- Planner: per-run latency, cost, % users with material change.
- Mastery: updates/day, regression count, divergence count (predicted vs actual).
- Cost: $/active_user/day rolling 7d/30d, by agent.
- Eval scores per suite over time.

### 33.3 Eval harness
Folder: `evals/`. Categories:
- `tutor_grounding` (50 fast / 500 nightly): given a turn input, the response must cite at least one PYQ for each factual claim and the cited PYQs must be plausibly relevant.
- `examiner_grading` (200 nightly): hand-graded attempts with expected `process_grade`. We score with exact match on `error_type` and edit-distance on rationale.
- `planner_quality` (50 nightly): synthetic Learner States; check the planner's predicted_pct_band brackets the simulated outcome (calibration).
- `diagnostic_calibration` (offline): replay stored diagnostics, ensure final θ̂ correlates with subsequent mock performance (r > 0.6 target).
- `tagger_agreement` (200, ongoing): tagger output vs SME labels; precision/recall per concept.

CI runs the `_fast` versions on every PR touching prompts or agent code. Nightly runs full suites and reports regressions to Slack with diff links.

## 34. Security, privacy, compliance

### 34.1 Tenancy
Single-tenant per-user with Postgres RLS. Connection pool sets `app.user_id` per request.

### 34.2 Secrets
Doppler → Fly secrets (no env files in repo). Rotation quarterly. Anthropic API key per-environment.

### 34.3 Encryption
At rest: Supabase + R2 default. Sensitive free-text columns (notes, working text) AES-GCM with per-user DEK wrapped by KMS CMK — phase 2.

### 34.4 Authz
Service-level decorator: every method receiving `user_id` checks `request.user_id == user_id`. Admin paths require a separate `support` role with audit log.

### 34.5 PII boundary
- LLM prompts include `display_name` only (never email, phone).
- Working text sent for grading is stripped of any URL or email patterns by a regex pass before egress.

### 34.6 Compliance posture
- DPDP Act (India) ready: `/me/export`, `/me/delete`, consent on signup for processing, no sensitive personal data category processed.
- Children: explicit minimum age 18 on signup.
- We do not train shared models on identifying user data without opt-in (and we don't train at all in v1).

## 35. DevOps & CI/CD

### 35.1 Environments
- `local` — docker-compose with Postgres, Qdrant, Redis, Temporal dev server.
- `preview` — per-PR ephemeral: Vercel preview, Fly preview app, Supabase branch DB.
- `staging` — long-lived; mirrors prod config; seeded with anonymized prod snapshot.
- `prod`.

### 35.2 CI (GitHub Actions)
Pipeline:
1. Lint: ruff, mypy --strict (api), eslint, tsc --noEmit (web).
2. Unit tests (pytest, vitest).
3. Eval fast suites if `agents/` or `prompts/` changed.
4. Migration dry-run against staging clone.
5. Build images.
6. Snapshot test OpenAPI spec for breaking changes.

### 35.3 CD
- Web: Vercel auto on `main`.
- API: GH Action → `fly deploy` with rolling release (health check gated).
- Workers: same.
- Migrations: `alembic upgrade head` is a release command, gated on dry-run success.

### 35.4 Backups & DR
- Supabase PITR (7d).
- Weekly logical dump to R2, 90d retention.
- Quarterly restore drill into a fresh Supabase branch.
- Qdrant snapshots nightly to R2; restore tested monthly.

## 36. Performance & cost engineering

### 36.1 Latency budgets (p95)
| Path | Budget |
|---|---|
| `GET /mastery` | 120 ms |
| Tutor TTFB | 800 ms |
| Tutor full turn | 8 s |
| Mock keypress→echo | 100 ms |
| Plan regen per user | 30 s |
| PYQ retrieval | 300 ms |
| Diagnostic next-item | 250 ms |

### 36.2 Cost levers (target: <$5/active user/month at v1)
- Sonnet-first routing.
- Aggressive prompt caching (~80% cache hit on Tutor).
- Result caching (Redis) for stable content.
- Batched overnight LLM (Planner/Analyst summary).
- Per-user circuit breaker.
- LLM-free heuristic in the Planner does ~60% of the work.

### 36.3 Capacity planning (back of envelope)
- 1k DAU × 8 Tutor turns × 3k tokens average × $0.000003/token ≈ $72/day → $2160/month → $2.16/user/month at full volume. With caching hit rate 0.8 effective tokens halve: ~$1.08/user/month. Comfortable.

## 37. Testing strategy

Layers:
1. **Unit** (fast, deterministic): BKT, decay, FSRS, LP, validators. Coverage ≥85% on `mastery/`, `planner/heuristic`, `mocks/score`.
2. **Contract**: Pydantic round-trip; OpenAPI snapshot.
3. **Integration**: testcontainers (Postgres, Qdrant, Redis); agent graphs run with stubbed LLM (fixture replies tied to prompt_version).
4. **Eval** (see §33.3).
5. **E2E** (Playwright): signup → diagnostic → first plan → first session → debrief; full mock; review loop.
6. **Load** (k6 nightly): 50 concurrent Tutor SSE; 100 concurrent attempt POSTs; mock interface state churn at 10 keys/sec/user × 100 users.
7. **Chaos** (phase 2): kill a Temporal worker mid-PostSessionAnalysis; assert idempotent recovery. Network partition Qdrant; assert Tutor degraded mode.

Fixtures: a `seed/` directory with deterministic users, PYQ subset, and prompt fixtures; `make seed` provisions a known state.

## 38. Failure modes compendium

| Component | Failure | Detection | Graceful degradation |
|---|---|---|---|
| Anthropic API down | 5xx / timeouts | Health probes + circuit breaker | Tutor → templated explainer; Examiner process grading skipped (deterministic only); Planner falls back to heuristic-only |
| Qdrant down | Tool error | OTel + alert | Tutor uses keyword retrieval (Postgres GIN on stems); quality drops, system stays up |
| Postgres slow | p95 spikes | RED alerts | API degrades to read-only mode; mocks blocked from starting; existing sessions continue |
| Redis down | Idempotency unverifiable | Health | API enforces dedup at DB unique index instead; small UX hiccup |
| Temporal down | Workflows stuck | Native alerts | Synchronous fallback for grading (slower turn-around but correct); mocks still grade in-process |
| LLM hallucinates | Eval/citation post-filter | Continuous | Re-prompt; on second failure, degraded templated response |
| Cost runaway (user) | Budget breach event | LLM router meter | Cap → Sonnet-only → freeze with notice |
| Mock browser crash | Heartbeat lost | Server timer | On reconnect, restore from server state; if elapsed, transition to submitted |
| User abandons session mid-stream | No `session.ended` for > 30 min | Watchdog | Mark `abandoned`, run partial Analyst over what completed |
| Invalid generated question slips through | User reports / disputed flag | Quality flag | Mark `quality_flag='disputed'`; exclude from mocks; recompute mastery without it |
| Concept tag wrong | SME spot check | Tagger eval | Manual fix; tagger few-shot bank updated |

---

# Part VIII — Execution

## 39. Build sequence (phase 0–5)

This sequences `master_spec.md §11` into concrete week-by-week deliverables with exit criteria. Adjust dates as we learn — but exit criteria are firm.

### Phase 0 — Foundations (weeks 0–4)
- [ ] Monorepo (Turborepo): `apps/web`, `apps/api`, `packages/shared`.
- [ ] Postgres schemas 0001–0010 (§6).
- [ ] Concept graph v1 seed (CSV import).
- [ ] PYQ ingestion workflow + 2015–2024 ingested, tagged, embedded.
- [ ] Clerk auth + `/me` endpoint.
- [ ] Base observability (OTel + Honeycomb dashboards).
- [ ] CI green: lint, unit, migration dry-run, OpenAPI snapshot.
- **Exit:** dev logs in, `/mastery` returns empty for them, `pyq.search` returns top-k for a sample query, observability shows traces.

### Phase 1 — Diagnostic loop (weeks 4–8)
- [ ] Diagnostician graph + IRT engine + multi-section orchestration.
- [ ] Mastery seeding + BKT (no decay).
- [ ] Planner v1 (heuristic only, no LLM).
- [ ] `/diagnostic/*` and `/plan/current` endpoints.
- [ ] Web: diagnostic UI, "your first plan" page, mastery heatmap (read-only).
- **Exit:** an external user takes a 60–90 min diagnostic and gets a 7-day plan they could follow.

### Phase 2 — Tutor loop (weeks 8–14)
- [ ] Tutor graph + RAG + SSE streaming + citation discipline.
- [ ] Examiner deterministic grading + Sonnet process grading.
- [ ] Analyst run + debrief.
- [ ] PostSessionAnalysis Temporal workflow.
- [ ] Web: session UI with citations, post-session debrief, open loops.
- [ ] tutor_grounding eval suite live in CI, baseline >0.85.
- **Exit:** a user completes a planned session end-to-end; mastery moves; debrief is true and specific.

### Phase 3 — Mocks & analytics (weeks 14–20)
- [ ] Mock interface (xstate, keyboard-first, scratchpad, IndexedDB recovery).
- [ ] Mock grading + percentile prediction (§17 calibration table).
- [ ] What-if simulator.
- [ ] Trends dashboard, error-type breakdown.
- [ ] Spaced review (FSRS) + open-loops resurfacing.
- [ ] BKT decay turned on.
- [ ] Planner v2 with LLM refinement (Opus).
- **Exit:** the product is a complete sole-source CAT prep tool for at least one cohort. Predicted percentile is calibrated within ±5 points 80% of the time.

### Phase 4 — Polish, retention, scale (weeks 20+)
- [ ] Coach agent, gated rollout.
- [ ] Quality-minutes streaks, anonymous leaderboards.
- [ ] PWA install + offline plan view.
- [ ] Cost optimization pass (cache hit rates, batch routing).
- [ ] Hinglish locale shipped.
- [ ] Read replica for analytics; ClickHouse if dashboard latency hurts.

### Phase 5 — Generalization
- [ ] Abstract `concepts`/`questions` to a `domain` boundary.
- [ ] Ingestion pipeline templated; first second-domain dogfood (GMAT or banking).
- [ ] Educator-facing "bring your own corpus" tools (deferred design).

## 40. Open implementation questions

These are the implementation-level decisions still open. Each is a candidate one-pager.

1. **Working-pad capture format.** Plain text only, or text + drawing canvas? Drawing helps QA process grading but ~doubles attempt size and adds a moderation surface.
2. **Mock paper sourcing v1.** Use only CAT 2010–2018 PYQs (no contamination with diagnostic) until our LLM-generated mocks pass a 95% quality bar. Confirm with SME.
3. **Tutor latency vs. quality tradeoff.** Sonnet 4.6 sometimes underperforms Opus on multi-step QA. Should we route 10% of QA-section turns to Opus (cost ~2.2× for that slice)?
4. **Diagnostic reset cadence.** When can a user re-take? Every 90 days? Or after a milestone (e.g., 5 mocks completed)?
5. **Concept graph open-source.** Master spec §14 question 7. Implementation impact: do we maintain a public mirror? Licensing implications.
6. **Hinglish prompt resources.** Need a curated style guide and 50-shot fewshot set for the Tutor. Out of dev scope; need an SME pass.
7. **Process grade SME labeling pipeline.** Building a 200-item gold set is the rate limiter for the `examiner_grading` eval. Who labels? Internal? Crowd?
8. **Pricing → API limits.** What does a free tier give? Probably: full diagnostic, 7 days of Tutor, no mocks. Need product call to wire feature gates.

---

# Appendix A — Pydantic schema sketches (selected)

```python
# Tutor turn output
class Citation(BaseModel):
    kind: Literal["pyq", "concept_note"]
    ref: str  # question_id or concept slug
    span: tuple[int, int]  # char offsets in the visible text

class TutorMoveDecision(BaseModel):
    move: Literal["ASK","EXPLAIN","SHOW_PYQ","GENERATE_PARALLEL","WRAP_UP","PROBE_MISCONCEPTION","NORMALIZE_AND_RETRY","SHOW_HARDER_PYQ","ESCAPE_WITH_WORKED_EXAMPLE"]
    target_concept_id: UUID | None
    pyq_id: UUID | None = None
    rationale: str  # internal

class TutorTurnOut(BaseModel):
    move: TutorMoveDecision
    text: str
    citations: list[Citation]
    cards: list[QuestionCard] = []
    tool_calls: list[ToolCallSummary] = []

# Examiner process grade
class ProcessGrade(BaseModel):
    method_correct: Literal["yes","partial","no","unknown"]
    error_type: Literal["conceptual","procedural","careless","time","misread","none"]
    near_miss: bool
    concepts_struggled: list[str]
    rationale_md: str

# Plan output
class PlanBlockOut(BaseModel):
    day: date
    ord: int
    goal: str
    block_kind: Literal["tutor","drill","pyq","review","mock"]
    target_concept_slugs: list[str]
    duration_min: int = Field(ge=10, le=180)
    rationale: str

class PlanOut(BaseModel):
    horizon_days: int = Field(ge=1, le=14)
    blocks: list[PlanBlockOut]
    predicted_pct_band: tuple[float, float, float]
    assumptions: list[str]
    risks: list[str]
```

# Appendix B — Key DDL extras

```sql
CREATE TABLE tutor_turns (
  id uuid PRIMARY KEY DEFAULT uuidv7(),
  session_id uuid NOT NULL REFERENCES sessions(id),
  ord int NOT NULL,
  user_message text,
  assistant_message_md text,
  move text NOT NULL,
  citations jsonb NOT NULL DEFAULT '[]',
  tool_calls jsonb DEFAULT '[]',
  tokens_in int, tokens_out int,
  prompt_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, ord)
);

CREATE TABLE mastery_snapshots (
  user_id uuid NOT NULL,
  graph_version int NOT NULL,
  taken_at timestamptz NOT NULL,
  state jsonb NOT NULL,                 -- {concept_id: {p, alpha, beta, last}}
  PRIMARY KEY (user_id, graph_version, taken_at)
);

CREATE TABLE mock_calibration (
  computed_at timestamptz NOT NULL,
  section text NOT NULL,
  scaled_score int NOT NULL,
  predicted_pct numeric NOT NULL,
  PRIMARY KEY (computed_at, section, scaled_score)
);
```

# Appendix C — LangGraph Tutor skeleton

```python
g = StateGraph(TutorState)
g.add_node("load_context", load_context)
g.add_node("decide_move", decide_move)
g.add_node("execute_ask", execute_ask)
g.add_node("execute_show_pyq", execute_show_pyq)
g.add_node("execute_parallel", execute_parallel)
g.add_node("execute_escape", execute_escape)
g.add_node("execute_wrap", execute_wrap)
g.add_node("validate_citations", validate_citations)
g.add_node("record_turn", record_turn)

g.add_edge(START, "load_context")
g.add_edge("load_context", "decide_move")
g.add_conditional_edges("decide_move", route_by_move, {
    "ASK": "execute_ask",
    "EXPLAIN": "execute_ask",
    "PROBE_MISCONCEPTION": "execute_ask",
    "NORMALIZE_AND_RETRY": "execute_ask",
    "SHOW_PYQ": "execute_show_pyq",
    "SHOW_HARDER_PYQ": "execute_show_pyq",
    "GENERATE_PARALLEL": "execute_parallel",
    "ESCAPE_WITH_WORKED_EXAMPLE": "execute_escape",
    "WRAP_UP": "execute_wrap",
})
for n in ["execute_ask","execute_show_pyq","execute_parallel","execute_escape","execute_wrap"]:
    g.add_edge(n, "validate_citations")
g.add_edge("validate_citations", "record_turn")
g.add_edge("record_turn", END)
```

# Appendix D — Sample event payloads

```json
{
  "kind": "attempt.graded",
  "schema_version": 1,
  "payload": {
    "attempt_id": "01JX...A",
    "question_id": "01JW...Q",
    "is_correct": false,
    "error_type": "conceptual",
    "near_miss": true,
    "process_grade": {
      "method_correct": "no",
      "error_type": "conceptual",
      "near_miss": true,
      "concepts_struggled": ["mixtures-replacement"],
      "rationale_md": "Treated successive replacement as additive..."
    }
  },
  "cause_event_id": "01JX...E"
}
```

```json
{
  "kind": "plan.generated",
  "schema_version": 1,
  "payload": {
    "plan_id": "01JX...P",
    "horizon_days": 7,
    "prompt_version": "planner.refine.2026-04-30",
    "predicted_pct_band": [78.2, 82.5, 86.4],
    "cause": "nightly_sweep"
  },
  "cause_event_id": "01JX...S"
}
```

# Appendix E — Sequence diagrams (compact)

**Tutor turn**
```
Client          API           Orchestrator         Tools/LLM           DB
  |--POST------>|              |                     |                  |
  |             |--auth/RLS--->|                     |                  |
  |             |--load ctx--->|--pyq.search-------->|                  |
  |             |              |<--top-k-------------|                  |
  |             |              |--decide_move(LLM)-->|                  |
  |             |              |<--move/json---------|                  |
  |             |              |--stream LLM-------->|                  |
  |<==SSE======(token|cite|card|done)======                             |
  |             |              |--validate cites---->|                  |
  |             |              |--record_turn---------------------------|
```

**Mock submit**
```
Client       API        Temporal             DB
  |--SUBMIT-->|--end()-->|                    |
  |           |--start PostMockAnalysis------>|
  |<--202-----|          |--grade_mock-->|    |
  |           |          |--predict_pct->|    |
  |           |          |--what_if----->|    |
  |           |          |--write_analysis--->|
  |--SSE subscribe analysis ready----------> ✓
```

# Appendix F — Glossary delta (extends MS Appendix A)

- **AgentRun** — typed envelope for one execution of an agent graph (§19).
- **Move** — discrete action a Tutor takes in a turn (§22.2).
- **Process grade** — Examiner's judgement on *how* a student arrived at an answer (§23.1).
- **Plan stickiness** — rule preventing thrashing of regenerated plans (§18.5).
- **Cross-node lift** — propagation of mastery to prerequisites when downstream concept is mastered (§16.2).
- **Citation discipline** — invariant that every Tutor factual claim cites a PYQ or concept note (§22.5).
- **Quality flag** — per-question status (`ok`/`disputed`/`errata`) gating use in mocks (§6.3).

---

**End of implementation spec.** v0.2. Treat as living; raise an RFC for any architectural invariant change (§4).
