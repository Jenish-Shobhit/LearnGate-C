# LearnGate-C — Step-by-Step Build Plan

**Derived from:** `master_spec.md` + `implementation_spec.md`  
**Author:** Jenish  
**Created:** 2026-05-10  
**Status:** Planning

Each step is a self-contained deliverable with a clear goal, acceptance criteria, and tests. Steps are grouped by phase. A step must fully pass its acceptance criteria before the next begins.

---

## How to read this

- **Goal** — what this step exists to produce.
- **Scope** — exact modules / files / UI surfaces to build.
- **Acceptance criteria** — verifiable conditions checked at step end; all must pass.
- **Tests** — specific test cases; listed by layer.

Dependency notation: `Step N depends on Step M` means M's acceptance criteria must be green before N starts.

---

# Phase 0 — Foundations

## Step 0.1 — Dev infrastructure & monorepo

**Goal:** Every engineer can clone, run `make dev`, and have the full local stack running. CI passes on every push.

**Scope:**
- Turborepo monorepo with `apps/web` (Next.js 15), `apps/api` (FastAPI), `packages/shared` (Pydantic + TS shared types).
- `docker-compose.yml`: Postgres 16, Qdrant 1.9, Redis 7, Temporal dev server.
- `Makefile` targets: `dev`, `test`, `lint`, `seed`, `migrate`.
- GitHub Actions pipeline: `lint → unit → build`.
- Pre-commit hooks: ruff, mypy, eslint, tsc.
- `.env.example` with all required variables documented.

**Acceptance criteria:**
- [ ] `make dev` starts all containers and both apps with zero manual steps beyond `cp .env.example .env.local`.
- [ ] `make lint` passes (ruff, mypy --strict on `apps/api`, eslint + tsc --noEmit on `apps/web`) with zero errors on the empty scaffolding.
- [ ] GitHub Actions pipeline runs to green on a push to `main`.
- [ ] `GET /healthz` on the API returns `{"status": "ok"}` within 500 ms.
- [ ] `http://localhost:3000` renders the Next.js shell without console errors.
- [ ] Temporal UI (`localhost:8233`) shows the dev server with no workflows.

**Tests:**
- Unit: none yet; testing framework bootstrapped (pytest configured, vitest configured).
- CI: `pytest --co` (collect-only) exits 0; `vitest run --reporter=verbose` exits 0.
- Manual smoke: engineer on a fresh machine runs `make dev` and confirms checklist above.

---

## Step 0.2 — Database schema & RLS

**Goal:** The full relational schema exists in Postgres and every user-scoped table enforces row-level security. A developer can run `make migrate` from scratch and get a clean, indexed database.

**Scope:**
- Alembic setup; migrations `0001` through `0012` (one per logical group from §6 of the implementation spec):
  - `0001_users` — users table
  - `0002_concept_graph` — concept_graph_versions, concepts, concept_edges
  - `0003_archetypes` — archetypes
  - `0004_questions` — question_groups, questions, question_concepts
  - `0005_mastery` — mastery, mastery_snapshots
  - `0006_sessions` — sessions, attempts
  - `0007_plans` — plans, plan_blocks
  - `0008_mocks` — mocks, mock_papers, mock_state, mock_calibration
  - `0009_review` — open_loops, debriefs, review_cards
  - `0010_events` — events (immutable append-only)
  - `0011_llm_calls` — llm_calls (cost log)
  - `0012_tutor_turns` — tutor_turns
- All indexes from §6 of impl spec.
- RLS policies on every user-scoped table (users, mastery, sessions, attempts, plans, mocks, open_loops, review_cards, debriefs, tutor_turns).
- A `packages/shared/schema.py` Pydantic models mirroring each table (used by both API and tests).

**Acceptance criteria:**
- [ ] `alembic upgrade head` against a fresh Postgres instance exits 0.
- [ ] `alembic downgrade base` then `alembic upgrade head` exits 0 (round-trip safe).
- [ ] `alembic check` shows no un-migrated changes after all migration files are applied.
- [ ] All 12 migrations are backward-compatible: old-code reads (SELECT) of new schema work (no NOT NULL columns added without defaults in a separate migration step).
- [ ] RLS: a service-role query with `app.user_id = 'user-A'` cannot see rows owned by `user-B` on any of the 10 protected tables.
- [ ] CI migration dry-run step passes.

**Tests:**
- Unit: Pydantic schema round-trips for every table model (instantiate from dict, serialize, re-parse — no exceptions).
- Integration (testcontainers): 
  - Run migrations on a fresh Postgres container; assert all tables exist with `information_schema.tables`.
  - Insert a row into `attempts` as user-A; connect as user-B; assert SELECT returns 0 rows.
  - Insert an event with `cause_event_id = NULL` for a non-entry-point kind; assert the application-level lint rule catches it (CI check, not DB constraint).
- CI: migration dry-run against staging-schema clone.

---

## Step 0.3 — Auth, API shell & observability baseline

**Goal:** A user can sign up and log in via Clerk. The API verifies JWTs, sets RLS context, and exposes `/me`. OpenTelemetry traces are visible in Honeycomb (or local Jaeger in dev).

**Scope:**
- Clerk: Next.js `ClerkProvider`, `middleware.ts` protecting `(app)/*` routes.
- API: `auth/` module — `clerk_verify(token)` → `UserContext(user_id, clerk_id)`.
- `POST /api/v1/auth/sync` — upsert user from Clerk JWT claims; returns user row.
- `GET /api/v1/me` — return profile + goals.
- `PATCH /api/v1/me` — update `exam_date`, `target_pct`, `hours_per_day`, `timezone`, `locale`.
- OpenTelemetry SDK wired into FastAPI (every request gets a trace). Langfuse client initialized (no LLM calls yet, just the SDK).
- Middleware sets `app.user_id` in Postgres connection per request.
- Error handler returning RFC 7807 `application/problem+json`.
- Rate limiter: 60 req/min per user in Redis.
- OpenAPI spec generated; `openapi-typescript` client generated into `packages/shared/api.ts`.

**Acceptance criteria:**
- [ ] Sign up via Clerk on the web; POST to `/auth/sync` upserts the user in Postgres; GET `/me` returns the user.
- [ ] A request with an expired or missing JWT returns `401` with proper problem+json body.
- [ ] `PATCH /me` with `exam_date: "2026-11-23"` persists and is returned in the next GET.
- [ ] Every request to `/api/v1/*` produces an OTel trace visible in the local Jaeger UI (or Honeycomb in staging).
- [ ] `openapi-typescript` client compiles without errors.
- [ ] Rate limit: 61st request within a minute returns `429`.

**Tests:**
- Unit: `clerk_verify()` with a mocked JWT (valid, expired, malformed).
- Unit: `PATCH /me` input validation — bad `exam_date` format returns `422`, target_pct > 100 returns `422`.
- Integration: Full flow — insert user via `POST /auth/sync`, fetch via `GET /me`, update via `PATCH /me`, verify Postgres row matches.
- Integration: RLS context — API sets `app.user_id`; a background query in the same transaction sees only that user's rows.
- E2E (Playwright): Sign up → land on dashboard → user row exists in DB.

---

## Step 0.4 — Concept graph v1

**Goal:** The full CAT concept graph (~450 nodes, ~700 edges across QA/VARC/DILR) is seeded into Postgres. A developer can query it and the API can resolve concept slugs.

**Scope:**
- Content work (pre-step, non-coding): curate `data/concept_graph_v1.csv` with columns `(slug, name, section, parent_slug, depth, weight_in_exam, half_life_days)` and `data/concept_edges_v1.csv` with `(parent_slug, child_slug, kind, weight)`. This is reviewed by at least one CAT SME before the seeding step runs.
- `make seed-graph` Temporal activity: `SeedConceptGraph(version=1, csv_path)` — idempotent upsert from CSVs.
- `GET /api/v1/concepts` — return full graph (versioned) as a JSON tree (used by frontend heatmap).
- `GET /api/v1/concepts/{slug}` — single concept with its prerequisite ancestors and child descendants.
- `packages/shared/concept_graph.py` — in-memory graph builder used by Planner and Analyst (loads once at startup).

**Acceptance criteria:**
- [ ] Seeding completes without errors; `SELECT COUNT(*) FROM concepts WHERE graph_version=1` ≥ 400.
- [ ] Every leaf concept in QA, VARC, and DILR has at least one `prereq` edge pointing to a parent.
- [ ] `GET /concepts` returns a valid JSON tree; every node has `section ∈ {QA, VARC, DILR}`.
- [ ] SME sign-off: a CAT-familiar reviewer reads the exported graph and confirms no major topic is missing and no prerequisite edge is backwards.
- [ ] `SeedConceptGraph` is idempotent: running it twice produces no duplicates.
- [ ] In-memory graph builder can answer "ancestors of slug X" in < 5 ms for any slug.

**Tests:**
- Unit: `concept_graph.ancestors("mixtures-replacement")` returns `["ratios", "arithmetic"]` in order.
- Unit: `concept_graph.descendants("arithmetic")` returns all QA leaf concepts beneath it.
- Unit: Graph has no cycles (DFS cycle detection).
- Integration: `GET /concepts/tsd-relative-motion` returns the node with correct `prereq` edges.
- Data validation: every `parent_slug` in the CSV exists as a `slug`; no slug appears twice; all `section` values are valid.

---

## Step 0.5 — PYQ ingestion pipeline

**Goal:** CAT 2015–2024 PYQs (all sections, all slots) are fully ingested, concept-tagged, and embedded in Qdrant. A `pyq_search` call returns semantically relevant questions.

**Scope:**
- Temporal workflow `IngestPaper(source_id)` with 10 activities:
  1. `fetch_pdf` — pull from R2.
  2. `parse_pdf` — pdfplumber + custom table extractor → `list[Page]`.
  3. `segment` — question boundary heuristics → `list[QuestionDraft]`.
  4. `detect_groups` — RC/DILR group detection.
  5. `extract_keys` — parse answer-key PDF.
  6. `tag_concepts` — Claude Opus structured output → `TaggerOutput` (concepts, archetype, difficulty_seed).
  7. `enqueue_review` — write first 100/section + 5% sample to `sme_review_queue` table.
  8. `embed` — Voyage `voyage-3-large` embeddings for stem + solution summary.
  9. `persist` — upsert into Postgres + Qdrant `pyq_questions` + `pyq_solutions` collections.
  10. `emit_event` — `pyq.ingested`.
- `rag/` module: `pyq_search(PyqQuery) -> list[QuestionRef]` — dense top-50 → MMR re-rank → exclude recent attempts.
- `sme_review_queue` table (simple: `id, question_id, status, reviewer_notes`).
- `GET /api/v1/admin/ingest` — trigger ingestion for a given source (admin role only).

**Acceptance criteria:**
- [ ] All CAT 2015–2024 papers (10 years × 2 slots × 3 sections) are ingested: `SELECT COUNT(*) FROM questions` ≥ 1500.
- [ ] Every ingested question has ≥ 1 `question_concepts` row with a valid concept slug from v1 graph.
- [ ] Every question has a non-null Qdrant vector ID (check `questions.embedding_id IS NOT NULL`).
- [ ] `pyq_search({concepts: [<mixtures-uuid>], section: "QA", k: 6})` returns 6 results in < 300 ms (p95).
- [ ] Tagger eval: on a 50-question spot sample, concept tags match SME labels with precision ≥ 0.75.
- [ ] `IngestPaper` is idempotent: running it twice on the same source produces no duplicate rows.
- [ ] Ingestion workflow handles a PDF parse failure gracefully (pauses, emits alert, does not persist partial paper).

**Tests:**
- Unit: `segment()` on a fixture HTML rendering of CAT 2019 S2 QA section — assert correct question boundaries.
- Unit: `TaggerOutput` Pydantic validation — `slug` not in concept graph raises `ValidationError`.
- Unit: `pyq_search` MMR re-rank — given mock dense results, assert diversity (no two results from same concept if more remain).
- Integration: Run `IngestPaper` on a 10-question fixture PDF (test corpus); assert all 10 questions appear in Postgres and Qdrant with correct metadata.
- Integration: `pyq_search` against the test corpus returns results with `concept_id` matching the query concepts.
- Integration: Second run of `IngestPaper` on the same fixture — no new rows in `questions`.
- Eval (manual): Tagger spot-check on 50 real questions against SME labels; record precision/recall per section.

---

# Phase 1 — Diagnostic loop

## Step 1.1 — BKT & mastery model core

**Goal:** The mastery engine can update, decay, and apply cross-node lift to a user's mastery vector. The `/mastery` endpoint returns current estimates with confidence intervals.

**Scope:**
- `mastery/bkt.py`: `bkt_update(p_known, alpha, beta, correct, p_slip, p_guess, p_learn) -> (p_next, alpha_next, beta_next)`.
- `mastery/decay.py`: `apply_decay(p_known, days_since, half_life_days) -> p_decayed` using the formula from §16.1.
- `mastery/lift.py`: `apply_cross_node_lift(user_id, concept_id, graph) -> list[MasteryUpdate]` (§16.2).
- `mastery/service.py`: `update_mastery(user_id, concept_id, correct)` — runs BKT, persists, emits `mastery.updated` event.
- `mastery/percentile.py`: Monte Carlo simulator from §17 — `predict_percentile_band(user_id) -> (low, mid, high)`.
- `GET /api/v1/mastery` — return `{concept_slug: {p, ci_low, ci_high, last_practiced_at, p_decayed}}` in < 120 ms.
- `GET /api/v1/mastery/{concept_slug}` — single concept detail.

**Acceptance criteria:**
- [ ] BKT update: correct answer on p_known=0.3 → p_next > 0.3; incorrect on p_known=0.8 → p_next < 0.8.
- [ ] CI: after 1 attempt, CI width > 0.4; after 20 attempts, CI width < 0.2.
- [ ] Decay: after 0 days, p_decayed = p_known; after `half_life_days`, p_decayed is within 0.01 of `0.5 + (p_known - 0.5) * 0.5`.
- [ ] Cross-node lift: mastering `mixtures-replacement` (p > 0.8) bumps `ratios` by ≤ 0.05 (edge weight dependent).
- [ ] `GET /mastery` returns within 120 ms for a user with 450 concepts.
- [ ] Monte Carlo: result band for a user with all p_known=0.5 is within the 50th–70th percentile (sanity check).

**Tests:**
- Unit: `bkt_update` — parametrize over (p_known, correct) × 6 combinations; assert monotonicity.
- Unit: `apply_decay` — 0 days → no change; 100 days on half_life=14 → p within 0.01 of formula.
- Unit: `predict_percentile_band` — seed a synthetic user with known mastery; assert band brackets expected percentile.
- Unit: CI computation — after N=1 attempt, `ci_high - ci_low > 0.4`; after N=30, `< 0.2`.
- Integration: `update_mastery(user_id, concept_id, correct=True)` × 5; GET `/mastery/{slug}`; assert p_known increased monotonically each step; assert `mastery.updated` events present in event log.
- Integration: `apply_cross_node_lift` — insert mastery rows for a leaf concept at p=0.85; assert parent p increases by correct delta.

---

## Step 1.2 — Diagnostician agent

**Goal:** A user can complete an adaptive CAT diagnostic (3 sections, ~60–90 min total) and receive a seeded mastery vector and a personalized post-test debrief.

**Scope:**
- `diagnostic/irt.py`: IRT item selection — max Fisher information at current θ̂, coverage constraint (≤2 items per concept until all areas touched), stopping rule (SE < 0.3 OR 25 items OR 35 min).
- `diagnostic/item_bank.py`: curate 80 items/section from CAT 2010–2018 (pre-2015 to avoid PYQ contamination); stored in Postgres with `source` field.
- `diagnostic/mastery_seed.py`: convert post-diagnostic θ̂ → initial mastery vector (§20.3 formula).
- `diagnostic/graph.py`: LangGraph state machine — `load_state → select_item → serve_item → receive_answer → update_irt → (stopping rule) → finalize → narrative`.
- `diagnostic/narrative.py`: Sonnet call with strict 4-section template (§20.4).
- API endpoints:
  - `POST /diagnostic/start` → `{session_id}`
  - `GET /diagnostic/{id}/next` → next question or `{status: "done"}`
  - `POST /diagnostic/{id}/answer` — `{question_id, response, time_ms}`
- Session state persists between sittings (pause + resume).

**Acceptance criteria:**
- [ ] Stopping rule fires: with all correct answers, diagnostic ends at or before 15 items/section (θ̂ rises quickly → SE drops).
- [ ] Coverage constraint: first 10 items span ≥ 6 distinct top-level concept areas per section.
- [ ] Post-diagnostic: `mastery` table has a row for every concept in the v1 graph (not just probed ones).
- [ ] Mastery seed sanity: user who answered 80% of QA items correctly has `avg(p_known) > 0.6` for QA concepts.
- [ ] Debrief: cites ≥ 2 specific `question_id`s in the "gaps" section; contains no generic filler ("great job!").
- [ ] Session pause/resume: user completes QA, closes browser, reopens — `GET /diagnostic/{id}/next` returns the first VARC item.
- [ ] End-to-end: full 3-section diagnostic completes and seeds mastery in < 100 min (timer check, not clock check).

**Tests:**
- Unit: `irt_select_item(theta=0.0, answered_ids=[], item_bank)` — returns item with `|b|` closest to 0.0.
- Unit: `irt_select_item` with coverage constraint active — after 2 items from `arithmetic`, next item is from a different area.
- Unit: `mastery_seed_from_theta(theta=1.5, section="QA")` — all probed concepts have `p_known > 0.6`.
- Unit: Stopping rule — after 25 items or SE < 0.3, `should_stop()` returns True.
- Integration: Run a scripted diagnostic (automated responses from fixture) for one section; assert mastery rows created; assert session status = `completed` after 3 sections.
- Integration: Pause after QA section; resume → next item is VARC item, not a repeat of QA.
- Eval (manual): Run diagnostic on 3 real users; compare debrief's stated gaps to their subsequent mock performance. Record correlation.

---

## Step 1.3 — Planner v1 (heuristic) + percentile prediction

**Goal:** After the diagnostic, the system generates a 7-day study plan using the heuristic slot-allocation algorithm. The plan is viewable via the API. Predicted percentile band is shown.

**Scope:**
- `planner/heuristic.py`: greedy slot allocation → 2-opt local search (§18.2). Inputs: mastery vector, days-to-exam, hours/day, FSRS-due cards (empty at this stage), open loops. Output: `list[PlanBlockOut]`.
- `planner/percentile.py`: already built in Step 1.1; wired here.
- `planner/service.py`: `generate_plan(user_id, cause) -> Plan` — runs heuristic, persists plan + blocks, emits `plan.generated` event.
- `GET /api/v1/plan/current` — return current plan with blocks and predicted_pct_band.
- `POST /api/v1/plan/regenerate` — enqueue regen (in Phase 1 this is synchronous; Temporal async in Phase 3).
- Heuristic constraints from §18.2: mock slot if days < 60, prereq ordering, 25% max per concept, spaced reviews first.

**Acceptance criteria:**
- [ ] Plan is generated within 5 seconds after diagnostic completes.
- [ ] Plan has 3–5 blocks per day, each with a clear goal string.
- [ ] Prerequisite constraint: if concept A has prereq B at < 0.6 mastery, at least one B block appears earlier in the same day before any A block.
- [ ] No single concept consumes > 25% of weekly slot minutes.
- [ ] `predicted_pct_band` is a tuple of three strictly increasing floats in [1, 99].
- [ ] Plan is idempotent on re-generate with the same inputs (no random variation).
- [ ] `GET /plan/current` returns within 200 ms.

**Tests:**
- Unit: `greedy_seed(mastery_vector, slots=14)` — top-3 weakest concepts by `expected_lift_per_minute` appear in first 3 slots.
- Unit: Prerequisite constraint — force concept B prereq mastery to 0.4; assert B block precedes A block in same day.
- Unit: 2-opt local search converges in < 2s for 14-slot input (time the call in pytest).
- Unit: `predict_percentile_band` is deterministic with fixed random seed.
- Integration: Complete a diagnostic for a test user; `generate_plan(user_id)`; assert `plans` table has 1 row and `plan_blocks` has 7 × [3..5] rows.
- Integration: `GET /plan/current` returns the plan; blocks reference valid `concept_id`s.
- Integration: Regenerate plan; assert `plans.superseded_at` is set on the old plan and a new plan row exists.

---

## Step 1.4 — Diagnostic & plan web UI

**Goal:** An external user can complete the full onboarding flow in the browser: sign up → goal-setting → diagnostic → see their mastery heatmap + first 7-day plan.

**Scope:**
- `app/(app)/dashboard/page.tsx` — landing after login; shows mastery heatmap + today's plan card.
- `app/(app)/diagnostic/page.tsx` — multi-section diagnostic UI with progress bar, per-section 2-line preview after completion.
- `app/(app)/plan/page.tsx` — 7-day plan with blocks, predicted percentile band, and rationale tooltips.
- `MasteryHeatmap` component — D3 force-directed layout; nodes colored by `p_known`, opacity by CI width. Sections (QA/VARC/DILR) have distinct clusters.
- `DiagnosticQuestion` component — renders MCQ + TITA questions with timer, handles answer submission.
- `PlanCard` component — per-block card with goal, duration, concept chips.
- Streaming hook: question delivery is instant (REST); after section completion, narrative streams via SSE.
- Responsive (mobile-web first — target 375px viewport).

**Acceptance criteria:**
- [ ] Sign up → goal-setting (exam date, target percentile, hours/day) → diagnostic UI loads in < 2s on 4G sim.
- [ ] Answering a diagnostic question and tapping submit sends `POST /diagnostic/{id}/answer` and loads the next item within 500ms.
- [ ] After completing all 3 sections, the debrief narrative streams token-by-token onto the screen.
- [ ] Mastery heatmap renders 450 nodes without layout thrash; dragging/panning is smooth at 60fps on desktop.
- [ ] Plan page shows today's blocks with correct concept names (matching Postgres slugs); predicted percentile band is visible.
- [ ] On mobile (375px), all above pages are usable without horizontal scroll or cut-off CTAs.
- [ ] LCP < 1.8s on the dashboard page (Lighthouse score).

**Tests:**
- Unit (vitest): `DiagnosticQuestion` renders MCQ options; clicking one calls `onAnswer` with correct payload.
- Unit: `MasteryHeatmap` renders without throwing given 450 mock nodes; a node with `p_known=0.9` has a green color class.
- Unit: `PlanCard` — truncates goal text > 80 chars with ellipsis; shows duration in "Xm" format.
- E2E (Playwright): `signup → complete diagnostic (scripted answers) → assert dashboard shows mastery heatmap with > 0 colored nodes → assert plan page shows ≥ 3 blocks for today`.
- E2E: On mobile viewport (375×812), diagnostic page — submit button is fully visible and tappable without scroll.
- Accessibility: axe-core scan on dashboard, diagnostic, and plan pages — zero critical violations.

---

# Phase 2 — Tutor loop

## Step 2.1 — Tutor agent + RAG + SSE streaming

**Goal:** A user can have an interactive, Socratic study session with the Tutor agent. The Tutor fetches relevant PYQs, streams responses with inline citations, and follows the move policy.

**Scope:**
- `agents/tutor/graph.py`: full LangGraph state machine (§22.3) — `load_context → decide_move → [execute_* nodes] → validate_citations → record_turn`.
- `agents/tutor/policy.py`: deterministic move decision (§22.2) with `LLM_FREE_CHOICE` fallback.
- `agents/tutor/prompts/`: prompt files for each execute node with frontmatter (`prompt_version`, `model`, `eval_suite`).
- `agents/tutor/validators.py`: citation post-stream validator — parse `[[cite:pyq:UUID]]` markers, verify each cited question exists in `questions` table, strip markers from visible text.
- Prompt prefix cache: system prompt + concept graph summary marked `cache_control: ephemeral` (§22.6).
- SSE protocol per §22.4: `token`, `citation`, `card`, `move`, `tool_call`, `error`, `done` events.
- `POST /sessions` — create session; `POST /sessions/{id}/messages` — SSE stream.
- Session state: last 8 turns loaded per request; `tutor_turns` persisted per turn.
- Locale support: `hi-en` addendum injected from `users.locale`.

**Acceptance criteria:**
- [ ] Tutor TTFB (first token to browser) < 800 ms at p95 on local (Sonnet 4.6, warm cache).
- [ ] Every streaming response that makes a factual claim includes ≥ 1 `citation` SSE event pointing to a valid `question_id`.
- [ ] Citation validator: a response with no citations on a factual sentence triggers one re-prompt and either succeeds or falls back to templated response (never sends uncited factual claim).
- [ ] Move policy: third consecutive incorrect attempt → `ESCAPE_WITH_WORKED_EXAMPLE` move (verifiable from event log `move` field).
- [ ] Second consecutive correct → `SHOW_HARDER_PYQ` fires if within first 60% of session duration.
- [ ] `tutor.turn.completed` event emitted after every turn with `citations`, `tokens`, `cost_usd`.
- [ ] Prompt cache: on the second request in the same session, `cached_tokens > 0` in `llm_calls` row.
- [ ] Hinglish locale: with `locale=hi-en`, tutor response code-switches (spot check).

**Tests:**
- Unit: `decide_move(state_with_3_consecutive_wrong)` returns `ESCAPE_WITH_WORKED_EXAMPLE`.
- Unit: `decide_move(state_past_60pct_time)` never returns `SHOW_HARDER_PYQ`.
- Unit: Citation validator — input text with `[[cite:pyq:UUID_valid]]` parses correctly; `UUID_invalid` raises `CitationNotFound`.
- Unit: Prompt builder inserts `hi-en` addendum only when `locale == "hi-en"`.
- Integration: Send 5 turns on a session; assert 5 `tutor_turns` rows; assert all have non-null `citations` JSON.
- Integration: Trigger `ESCAPE_WITH_WORKED_EXAMPLE` via scripted wrong answers; assert the turn's `move` field = `ESCAPE_WITH_WORKED_EXAMPLE` in `tutor_turns`.
- Integration: LLM stub (fixture reply) with missing citation; assert validator re-prompts; second stub reply includes citation; assert final turn stored with citation.
- Eval (CI fast, 50 cases): `tutor_grounding` suite — every factual claim has a plausible PYQ citation. Target: ≥ 0.85.

---

## Step 2.2 — Examiner agent (grade + generate)

**Goal:** Every attempt is graded: correct/incorrect immediately, with process grading (error type, method) asynchronously. The Examiner can generate parallel problems for QA archetypes.

**Scope:**
- `examiner/graders.py`:
  - `grade_mcq(question, response) -> GradeResult` (deterministic).
  - `grade_tita(question, response) -> GradeResult` (deterministic).
  - `process_grade(question, response, working_text, time_ms) -> ProcessGrade` (Sonnet, async, §23.1).
- `examiner/generators.py`:
  - `generate_templated(archetype_slug, difficulty_b) -> GeneratedQuestion` (template engine for QA archetypes).
  - `generate_llm(archetype_slug, section, difficulty_b) -> GeneratedQuestion` (Sonnet draft + Opus QA, §23.3).
- `POST /sessions/{id}/attempts` — insert attempt, return `GradeResult` stub immediately, trigger async process grading.
- Background: `grade_attempt_process` FastAPI BackgroundTask — runs process grading, emits `attempt.graded` event, updates `attempts.error_type`.
- All generated questions tagged `source = 'GEN_*'`; only used in drill mode until 95% quality threshold (§23.3).

**Acceptance criteria:**
- [ ] Correct MCQ answer: `is_correct=True` returned within 50 ms of POST.
- [ ] Incorrect MCQ: `is_correct=False`; process grading completes within 3s; `attempts.error_type` is populated.
- [ ] Process grading classifies error type correctly on 3 fixture cases: (1) wrong concept applied (→ `conceptual`), (2) arithmetic slip (→ `careless`), (3) correctly solved but ran out of time (→ `time`).
- [ ] Near-miss detection: an attempt on a trap option is flagged `near_miss=True`.
- [ ] Template generation: `generate_templated("tsd_relative_motion", 0.5)` produces a syntactically valid question with a numerically correct answer.
- [ ] LLM generation quality gate: `generate_llm` on 10 fixture archetypes — ≥ 9 pass the Opus QA check on first try.
- [ ] `attempt.graded` event always carries `cause_event_id` = the `attempt.created` event id.

**Tests:**
- Unit: `grade_mcq` — correct answer returns `is_correct=True`; wrong returns `is_correct=False`.
- Unit: `grade_tita` — numeric match with ±0.01 tolerance.
- Unit: Template generator for `tsd_relative_motion` — randomize vars 10 times; assert each produced answer matches manual calculation.
- Unit: `ProcessGrade` Pydantic model — `error_type` outside allowed literals raises `ValidationError`.
- Integration: POST attempt → immediate `GradeResult`; wait 3s; GET attempt; assert `error_type` is set.
- Integration: POST attempt with `near_miss=True` trigger condition; assert `attempts.near_miss = true`.
- Integration: `generate_llm` with LLM stub; Opus QA stub returns fail; assert retry happens (max 3); assert failed questions not persisted to `questions`.
- Eval (nightly, 200 cases): `examiner_grading` suite — exact match on `error_type` ≥ 0.80; edit distance on rationale ≤ 3.

---

## Step 2.3 — Analyst agent + PostSessionAnalysis workflow

**Goal:** After every session ends, the system: runs BKT updates for all attempted concepts, applies decay, detects regressions, and produces a specific session debrief visible to the user.

**Scope:**
- `analyst/graph.py`: LangGraph — `pull_attempts → bkt_batch_update → apply_decay → cross_node_lift → detect_regressions → detect_divergences → write_debrief → persist`.
- `analyst/detectors.py`: `detect_regressions(user_id, since) -> list[Regression]` — concept where `|Δp| > 0.10` with ≥3 graded attempts.
- `analyst/prompts/debrief.md`: strict template from §24.3, Sonnet 4.6, ≤ 250 words.
- Temporal workflow `PostSessionAnalysis(session_id)` with the 8 activities from §3.3.
- Signal: `RegeneratePlan` sent if regression detected or significant mastery delta (Δp > 0.10 on a high-weight concept).
- `GET /sessions/{id}/debrief` — SSE stream while workflow runs; falls back to polling.
- `debriefs` table row persisted with `mastery_delta` JSON.

**Acceptance criteria:**
- [ ] Session end → debrief visible in the UI within 30 seconds.
- [ ] Debrief headline cites the concept with the largest mastery delta and the before/after percentage.
- [ ] Regression detection: after 3 consecutive incorrect attempts on a concept whose p_known was 0.75, `mastery.regression` event is emitted.
- [ ] `RegeneratePlan` signal is sent to the Planner workflow after a regression event.
- [ ] Debrief "Wins" section cites ≥ 1 specific `question_id`.
- [ ] `PostSessionAnalysis` is idempotent: running it twice on the same `session_id` produces no duplicate `debriefs` rows.
- [ ] `session.analyzed` event has `cause_event_id` = the `session.ended` event id.

**Tests:**
- Unit: `bkt_batch_update([{concept_id, correct=True}, {concept_id, correct=False}])` — assert both rows in `mastery` table updated; assert ordering doesn't matter (commutative within a session).
- Unit: `detect_regressions` — create mastery row at p=0.80, run 3 incorrect attempts → function returns the concept.
- Unit: `detect_divergences` — planner predicted Δp=0.15 for a concept; actual Δp=0.03; function returns the pair.
- Integration: Complete a scripted session (5 correct, 3 wrong); end session; wait for workflow; assert `debriefs` row exists; assert `mastery.updated` events for all attempted concepts.
- Integration: End session twice (idempotency test); assert only 1 `debriefs` row.
- Integration: Regression path — 3 consecutive wrong; assert `mastery.regression` event; assert `RegeneratePlan` signal is sent (mock Temporal signal endpoint).
- E2E (Playwright): End a session → debrief page loads within 30s with a non-empty headline.

---

## Step 2.4 — Session web UI

**Goal:** The full study session is usable in the browser: see today's plan, start a session, chat with the Tutor, attempt questions with the working pad, see open loops, and read the debrief.

**Scope:**
- `app/(app)/session/[id]/page.tsx` — session UI.
- `TutorChat` component — streaming message bubbles, citation chips (hover to preview PYQ), question cards (MCQ + TITA), loading skeleton.
- `WorkingPad` component — plain text capture (canvas deferred to Phase 3); sent with attempt.
- `OpenLoopBanner` — surfaces flagged confusion items at top of session if resurfacing rule fires.
- `DebreifPage` — post-session debrief view with mastery delta visualization (up/down arrows per concept).
- `SessionHeader` — shows plan block goal, elapsed time, block progress.
- Streaming hook (`useTutorStream`) — wraps SSE with reconnect logic (Last-Event-ID), backpressure handling.
- `app/(app)/plan/page.tsx` — "Start session" button on each plan block calls `POST /plan/blocks/{id}/start` → navigates to `/session/{id}`.

**Acceptance criteria:**
- [ ] Clicking "Start session" on a plan block creates a session and navigates to the session page in < 1s.
- [ ] Tutor first token renders in < 900ms from page load (TTFB budget from §28.4).
- [ ] Citation chips appear inline after the sentence they annotate; hover shows PYQ question text preview.
- [ ] Submitting an attempt: correct/incorrect indicator appears instantly (< 100ms); process grade label (`conceptual`, `careless`, etc.) appears within 3s.
- [ ] Working pad text is sent with the attempt POST and stored in `attempts.response.working_text`.
- [ ] Post-session debrief page auto-navigates after `session.analyzed` SSE event; debrief is fully rendered.
- [ ] On mobile (375px), question cards and chat bubbles are fully readable; no horizontal overflow.

**Tests:**
- Unit (vitest): `useTutorStream` — mock SSE with `token`, `citation`, `done` events; assert state updates correctly.
- Unit: `TutorChat` — renders a `citation` chip after the sentence it annotates (index alignment test).
- Unit: `WorkingPad` — typing in the pad updates local state; calling `flush()` returns the text.
- E2E (Playwright): Start session → type a message → assert streaming response appears → attempt a question → assert correct/incorrect indicator shows → end session → assert debrief page loads.
- E2E: Disconnect SSE mid-stream; reconnect (simulate by closing/reopening EventSource); assert stream resumes from last token.
- Accessibility: axe-core on session page — zero critical violations.

---

# Phase 3 — Mocks & analytics

## Step 3.1 — Mock interface (xstate + timer)

**Goal:** Users can take a full-length CAT-faithful mock exam: 3 sections, sectional timers, question palette, keyboard navigation, scratchpad, mid-exam persistence, and crash recovery.

**Scope:**
- `app/(app)/mock/[id]/page.tsx` — the mock interface.
- `MockInterface` component built on xstate state machine (§29): states `idle → loading_paper → ready_to_start → in_section → submitted → crashed_recovery`.
- `QuestionPalette` — grid of question status dots (answered, marked-for-review, visited-not-answered, not-visited).
- `SectionTabs` — within-section flexible, between-section sequential (locked until current section complete or time expires).
- `Scratchpad` — plain-text scratch area per question (separate from WorkingPad; not submitted for grading).
- Timer: client-side 1s ticks + server reconciliation every 15s via `POST /mocks/{id}/state`.
- `IndexedDB` buffer: every answer + navigation written locally; synced to server on mutation.
- `POST /mocks/start`, `POST /mocks/{id}/state`, `POST /mocks/{id}/end`.
- On reload mid-mock: fetch server state → hydrate xstate → resume.

**Acceptance criteria:**
- [ ] Mock starts within 1s of clicking "Begin".
- [ ] Keypress → echo (selecting an option, navigating) < 100ms with no debounce.
- [ ] Section timer counts down correctly; when it reaches 0, the section is auto-submitted.
- [ ] Timer source of truth is the server: simulate clock drift (advance client clock +5min); on next 15s autosave, server's `time_remaining` overrides.
- [ ] Kill the browser mid-mock; reload; assert the mock resumes from the last saved state (IndexedDB → server fallback).
- [ ] All 3 sections complete → `POST /mocks/{id}/end` submitted → user navigated to "Grading in progress" screen.
- [ ] A mock started offline shows a friendly error; timer cannot start offline.
- [ ] xstate transitions are deterministic: replaying the same event sequence produces the same final state.

**Tests:**
- Unit (vitest): xstate machine — `ANSWER` event in `in_section` state transitions answer_buffer correctly.
- Unit: Timer guard — `section_time_remaining(state)` returns correct remaining seconds given a start time and elapsed ticks.
- Unit: `can_navigate_within_section` — returns true for questions within section, false for other sections.
- Unit: Reconcile timer — server `time_remaining = 1800`, client believes `2400`; after reconcile, client uses 1800.
- Integration: POST `/mocks/start` → assert `mocks` row + `mock_state` row created; POST state updates × 5 → assert `mock_state.state_blob` updated.
- Integration: POST `/mocks/{id}/end` → assert `mocks.status = 'completed'`; assert `PostMockAnalysis` workflow triggered (mock Temporal).
- E2E (Playwright): Full mock run on 9-question test paper (3 per section); assert all 3 sections complete; assert end submitted.
- E2E: Crash recovery — reload mid-mock; assert question palette shows correct answered/unanswered state.

---

## Step 3.2 — Mock grading + post-mock analytics + what-if simulator

**Goal:** After a mock, the user sees: sectional scores, predicted percentile band, error-type breakdown, per-question analysis, and the what-if simulator. The trends dashboard shows progress over time.

**Scope:**
- Temporal workflow `PostMockAnalysis(mock_id)` with activities: `grade_mock`, `predict_percentile`, `build_what_if`, `write_analysis`.
- `mocks/score.py`: CAT scoring rule (+3/-1 MCQ, +3/0 TITA), sectional scale, `mock_calibration` table lookup.
- What-if precomputation: for each attempted question, score if skipped (stored in analysis JSON).
- `GET /mocks/{id}/analysis` — return full analysis including per-question process grades.
- `app/(app)/mock/[id]/analysis/page.tsx`:
  - Sectional scores + predicted percentile band with CI.
  - Error-type donut chart (conceptual / procedural / careless / time / misread).
  - Per-question timeline: time spent vs. difficulty.
  - `WhatIfSimulator` — toggle questions on/off; client-side score recomputation from precomputed deltas.
- `app/(app)/analytics/page.tsx`:
  - `GET /analytics/trends?range=30d` returning per-day series.
  - Mock score trend chart (Recharts or Nivo).
  - Accuracy per section chart.
  - Error-type trend over time.
  - Mastery heatmap (same component as dashboard, but with delta overlays from last 7 days).

**Acceptance criteria:**
- [ ] Mock grades finish within 60s of submission for a 66-question paper.
- [ ] Predicted percentile band: on 10 historical mock papers (known scores), our predicted band brackets the official percentile 80% of the time (cold start: use 2024 CAT calibration table).
- [ ] What-if simulator: toggling off a question instantly recomputes the score (client-side, < 16ms).
- [ ] Error-type donut: categories sum to 100% of attempted questions.
- [ ] Side-by-side comparison: if user has ≥ 2 mocks, analytics page shows delta arrows (↑/↓) on each metric.
- [ ] `GET /analytics/trends?range=30d` returns within 300ms for a user with 500 attempts.

**Tests:**
- Unit: `score_section([+3, -1, +3, 0, +3]) = 9` (2 correct MCQ, 1 wrong MCQ, 1 unattempted MCQ, 1 correct TITA).
- Unit: `build_what_if([{id, score_delta}])` — toggling off question Q3 reduces score by `score_delta_Q3`.
- Unit: Percentile lookup — scaled score 120 on QA → calibration table returns percentile within [50, 100].
- Integration: Complete a scripted 9-question mock; submit; wait for workflow; GET analysis; assert `scaled_score` + `predicted_pct_band` present.
- Integration: `PostMockAnalysis` idempotency — run twice on same `mock_id`; assert no duplicate `mocks.scaled_score` writes (or same value).
- E2E (Playwright): Complete mock → navigate to analysis → what-if simulator visible → toggle a wrong answer off → score increases.
- Performance: Load analytics page for user with 30 mocks (seeded); assert LCP < 2s.

---

## Step 3.3 — Spaced review (FSRS) + BKT decay

**Goal:** Users have a daily spaced review queue surfacing their own weak/decayed concepts via FSRS. BKT decay runs nightly. The Planner allocates review blocks first.

**Scope:**
- `review/fsrs.py`: FSRS-4.5 algorithm — `schedule_card(card, rating) -> (new_stability, new_difficulty, new_state, due_at)`.
- `review/service.py`: `get_due_cards(user_id, cap=30) -> list[ReviewCard]`.
- Temporal `FSRSDailyTick()` workflow (nightly) — advance overdue cards into `relearning`.
- Temporal `DecaySweep()` (nightly) — `apply_decay` for all users with `last_practiced_at < now() - interval '7 days'`.
- `GET /review/due` — today's due cards (concept + question).
- `POST /review/answer` — `{card_id, rating: 1..4}` → update FSRS state.
- `app/(app)/review/page.tsx` — flash-card style review UI (question on front, answer on back).
- Planner integration: `generate_plan` now calls `get_due_cards` first and allocates review blocks before new-content blocks.

**Acceptance criteria:**
- [ ] After answering a card `rating=4` (easy), `due_at` is ≥ 3 days out.
- [ ] After answering `rating=1` (again), card state transitions to `relearning` and `due_at` is within 10 minutes.
- [ ] Daily review cap: `get_due_cards` returns at most 30 cards even if 100 are overdue.
- [ ] Planner: generated plan for a user with 5 due review cards always has ≥ 1 review block on day 1.
- [ ] Decay: a concept not practiced in 28 days (2 half-lives) has `p_decayed` within 0.01 of `0.5 + (p_known - 0.5) * 0.25`.
- [ ] DecaySweep runs in < 5 min for 1k users (CI load test or benchmark).

**Tests:**
- Unit: FSRS state transitions — `new → learning` after first review; `learning → review` after 2 correct reviews; `review → relearning` after `rating=1`.
- Unit: `due_at` for `rating=4` on a concept with stability=10 is ≈ `now() + 10 days` (±1 day tolerance).
- Unit: Decay formula — 0 days: no change; 14 days (1 half-life): `p_decayed ≈ 0.5 + (p - 0.5)*0.5`.
- Unit: Planner with due cards — mock `get_due_cards` returning 5 cards; assert plan has review block with those concept IDs before new-content blocks.
- Integration: Create 5 review cards; call `FSRSDailyTick`; assert overdue cards have `state=relearning`.
- Integration: `POST /review/answer {rating=4}` → assert `review_cards.due_at` updated; assert `mastery.updated` event emitted with `cause="spaced_review"`.
- E2E (Playwright): Review page → flip card → rate answer → card disappears from queue → queue count decreases.

---

## Step 3.4 — Planner v2 (LLM refinement + nightly Temporal sweep)

**Goal:** The Planner uses Claude Opus to refine heuristic plan skeletons into natural-language study plans. Nightly sweep runs for all active users. Plan re-triggers are wired to the Analyst signals.

**Scope:**
- `planner/refine.py`: Opus call with heuristic skeleton + last 7 days session logs + open loops + adherence. Output: `PlanOut` Pydantic validated (§18.3).
- Post-validator: enforce minute-budget invariant, FSRS-due reviews not dropped, prereq constraints not violated.
- Temporal workflow `RegeneratePlan(user_id, cause)` wiring `heuristic_skeleton → llm_refine → validate → persist → invalidate_cache`.
- Temporal workflow `NightlySweep()` — fan-out to `RegeneratePlan` for all users active in last 7 days (parallelism 200).
- `POST /plan/regenerate` — enqueues `RegeneratePlan` workflow; returns `{workflow_id}`.
- Stickiness rule: no re-generation within 6 hours of last regeneration (unless user-initiated).
- Triggers from Analyst: `RegeneratePlan` signal on `mastery.regression` and `2+ session.skipped` days.

**Acceptance criteria:**
- [ ] LLM-refined plan has more specific goal strings than heuristic (qualitative, verified in code review).
- [ ] Post-validator rejects a plan where the LLM dropped a FSRS-due review block (validator raises `PlanViolation`).
- [ ] Post-validator rejects a plan where the LLM exceeded the daily minute budget.
- [ ] Nightly sweep: 10k synthetic users processed in < 30 min (benchmark with 50 concurrent, extrapolate).
- [ ] Stickiness rule: two consecutive API calls to `POST /plan/regenerate` within 6h — second returns 429 with `{"code": "plan.regen_throttled"}` unless `force=true`.
- [ ] Signal from Analyst: `mastery.regression` event → `RegeneratePlan` workflow enqueued within 5s.

**Tests:**
- Unit: Post-validator — plan missing a due review block raises `PlanViolation("fsrs_review_dropped")`.
- Unit: Post-validator — plan with day total > `hours_per_day * 60` raises `PlanViolation("budget_exceeded")`.
- Unit: Stickiness — `should_regenerate(last_regen=now()-4h, user_initiated=False)` returns False.
- Unit: `should_regenerate(last_regen=now()-4h, user_initiated=True)` returns True.
- Integration: `POST /plan/regenerate`; assert `RegeneratePlan` workflow started in Temporal (mock Temporal client); assert `plans` row updated.
- Integration: Emit `mastery.regression` event; assert `RegeneratePlan` workflow enqueued within 5s (event-driven path).
- Integration: Two regenerations within 6h — second returns 429.
- Performance (benchmark): Run `RegeneratePlan` for 50 synthetic users in parallel; assert all complete within 60s.
- Eval (nightly, 50 cases): `planner_quality` suite — `predicted_pct_band` brackets the simulated outcome. Target: ≥ 80%.

---

# Phase 4 — Polish, retention & scale

## Step 4.1 — Platform hardening (observability, evals, security, cost)

**Goal:** The system is production-ready: full observability, all eval suites in CI, security controls enforced, cost guardrails active, and the entire test pyramid green.

**Scope:**
- Observability: OTel across API + workers + agents → Honeycomb. Langfuse spans for every LLM call. Prometheus metrics exported (RED per route, Tutor TTFB, mastery update rate, cost/user/day).
- Eval harness (`evals/`): all 5 suites from §33.3 wired to CI (fast suites on every PR, full suites nightly).
- Security: Doppler secrets integration; per-user cost circuit breakers (soft $1/day, hard $3/day); PII scrubber on working text before LLM egress; `minimum_age = 18` gate on signup.
- CI additions: eval fast suites on `agents/` or `prompts/` change; OpenAPI snapshot test; migration dry-run; cost-attribution lint (every LLM call tagged).
- Load test (k6): 50 concurrent Tutor SSE; 100 concurrent attempt POSTs; verify latency SLOs hold.
- Backup/DR: PITR verification script; Qdrant nightly snapshots to R2.

**Acceptance criteria:**
- [ ] Every Tutor turn has an OTel trace and a Langfuse span with tokens/cost/latency visible in the dashboard.
- [ ] `tutor_grounding` eval on 500 cases: ≥ 0.85 grounded responses (CI nightly).
- [ ] `examiner_grading` eval on 200 cases: `error_type` exact match ≥ 0.80 (CI nightly).
- [ ] `planner_quality` eval on 50 cases: ≥ 80% of predicted bands bracket simulated outcome (CI nightly).
- [ ] Cost circuit breaker: simulate user exceeding $1/day soft limit; assert subsequent Tutor calls use Sonnet-only mode.
- [ ] PII scrubber: working text containing `user@email.com` is stripped before being sent to Anthropic API.
- [ ] k6 load test: 50 concurrent Tutor SSE maintain p95 TTFB < 800ms; 100 concurrent attempts maintain p95 < 200ms.
- [ ] Cost-attribution lint: any LLM call without `user_id` + `cause_event_id` fails CI.

**Tests:**
- All existing unit/integration/E2E tests remain green after observability instrumentation.
- Unit: Cost circuit breaker logic — `soft_limit_exceeded(user_id, today_cost=1.01)` returns True.
- Unit: PII scrubber — `scrub("my email is foo@bar.com and I'm foo")` → `"my email is [REDACTED] and I'm foo"`.
- Integration: Make a Tutor turn with a mocked LLM; assert `llm_calls` row has non-null `user_id`, `agent`, `cost_usd`.
- Integration: Trigger hard circuit breaker; assert next Tutor call returns `{"code": "tutor.budget_exceeded"}`.
- Load (k6): Run `k6 run scripts/load_tutor.js`; assert p95 < 800ms at 50 VU.
- Eval: All 5 eval suites pass their thresholds on a single seeded run before marking step complete.

---

## Step 4.2 — Coach agent, streaks, social features (phase 4 content)

**Goal:** The Coach watches adherence and motivation signals; quality-minutes streaks are live; anonymous percentile leaderboards are available.

**Scope:**
- `agents/coach/` (gated behind GrowthBook feature flag `coach_agent_enabled`).
- Coach inputs: `session.*` events, mock scores, adherence stats (% of planned blocks completed last 7 days).
- Coach output: `{should_nudge, channel, content_template, target_time}` — at most one nudge per 24h per user.
- Nudge delivery: push (web-push via service worker) or email (Resend). All nudges are events.
- Quality-minutes: `sessions.metadata.quality_minutes` — minutes where attempt rate > 0 and accuracy > random chance (not streakable via opening app).
- Streak: computed nightly from `quality_minutes >= 15` per day.
- `GET /me/streak` — `{current_streak_days, longest_streak_days}`.
- Leaderboard: anonymous percentile buckets (not names) from last 30 days of mocks, opt-in only.

**Acceptance criteria:**
- [ ] Coach fires at most 1 nudge per 24h per user.
- [ ] Coach detects burnout signal: `declining accuracy + declining session_length + 2 skipped days` → nudge with a rest day suggestion.
- [ ] Quality-minutes: a session where user opened the app and answered 0 questions does not count toward streak.
- [ ] Streak: 15 quality-minutes/day for 5 days → streak = 5.
- [ ] Feature flag: with `coach_agent_enabled=false`, no Coach nudges are sent; Coach agent code is unreachable.
- [ ] Leaderboard: user who has not opted in does not appear in the leaderboard data.

**Tests:**
- Unit: Burnout signal detection — `detect_burnout(accuracy_trend=[-0.05, -0.04], session_length_trend=[-10, -5], skipped_days=2)` returns True.
- Unit: Quality minutes — session with 0 attempts → quality_minutes = 0.
- Unit: `should_nudge(last_nudge=now()-23h)` returns False; `last_nudge=now()-25h` returns True.
- Integration: Coach workflow with burnout signal → assert one nudge event emitted; assert second run within 24h emits no nudge.
- Integration: Quality-minutes streak — insert 5 session rows with quality_minutes ≥ 15; assert `GET /me/streak` returns `{current_streak_days: 5}`.
- E2E: Opt-in to leaderboard → complete 2 mocks → leaderboard page shows a percentile bucket with a count.

---

# Phase 5 — Generalization

## Step 5.1 — Abstract domain layer (GMAT / banking dogfood)

**Goal:** The concept graph and PYQ ingestion pipeline are parameterized by `domain`. A second domain (GMAT or banking) can be onboarded by providing a concept CSV and paper PDFs without touching agent code.

**Scope:**
- `concepts.domain` column (migration `0013_domains`); `questions.domain` column.
- `IngestPaper` workflow: `domain` parameter gating section checks and archetype taxonomy.
- Concept graph seed workflow: `SeedConceptGraph(domain, version, csv_path)`.
- Agent substrate: `domain` injected into all agent prompts via `shared_config`.
- API: `domain` query param on all knowledge-layer endpoints.
- Internal dogfood: ingest 1 year of GMAT OG questions, run a diagnostic, generate a plan — verify no CAT-specific logic fires.

**Acceptance criteria:**
- [ ] A second domain can be fully onboarded by running `make seed-graph domain=GMAT` + `IngestPaper(domain=GMAT, ...)` without any code changes.
- [ ] Tutor prompt does not mention "CAT" when `domain=GMAT`; it uses the correct exam name.
- [ ] Mastery, BKT, Planner, Analyst, Examiner all operate correctly with GMAT concept slugs.
- [ ] CAT users are completely unaffected by the GMAT domain addition (RLS + domain filter prevent bleed-over).
- [ ] `GET /concepts?domain=GMAT` returns only GMAT nodes.

**Tests:**
- Unit: Prompt builder — with `domain=GMAT`, no "CAT" string appears in rendered prompt.
- Integration: Seed a 10-node GMAT concept graph; ingest 5 GMAT questions; run `pyq_search({domain: "GMAT", ...})`; assert only GMAT questions returned.
- Integration: CAT user's mastery is not polluted by GMAT question attempts.
- Integration: Diagnostic for GMAT domain uses GMAT item bank (no CAT items served).
- E2E: End-to-end flow (signup → diagnostic → plan) for GMAT domain without errors.

---

# Summary table

| Step | Phase | Depends on | Key deliverable |
|---|---|---|---|
| 0.1 | 0 | — | Dev infra, CI green |
| 0.2 | 0 | 0.1 | Full DB schema + RLS |
| 0.3 | 0 | 0.2 | Auth, API shell, observability |
| 0.4 | 0 | 0.3 | Concept graph v1 seeded |
| 0.5 | 0 | 0.4 | PYQ corpus ingested + embedded |
| 1.1 | 1 | 0.5 | BKT + mastery model |
| 1.2 | 1 | 1.1 | Diagnostician agent |
| 1.3 | 1 | 1.2 | Planner v1 + percentile model |
| 1.4 | 1 | 1.3 | Diagnostic + plan web UI |
| 2.1 | 2 | 1.4 | Tutor agent + RAG + SSE |
| 2.2 | 2 | 2.1 | Examiner (grade + generate) |
| 2.3 | 2 | 2.2 | Analyst + PostSessionAnalysis workflow |
| 2.4 | 2 | 2.3 | Session web UI |
| 3.1 | 3 | 2.4 | Mock interface (xstate) |
| 3.2 | 3 | 3.1 | Mock grading + analytics dashboard |
| 3.3 | 3 | 3.2 | Spaced review (FSRS) + BKT decay |
| 3.4 | 3 | 3.3 | Planner v2 (LLM refinement + nightly sweep) |
| 4.1 | 4 | 3.4 | Platform hardening (observability, evals, security) |
| 4.2 | 4 | 4.1 | Coach, streaks, social |
| 5.1 | 5 | 4.2 | Multi-domain abstraction |

---

# Open questions before building

The following are unresolved at spec time. Each needs a decision before the relevant step starts.

1. **PYQ PDFs availability** (blocks Step 0.5): Do we have the raw PDF scans for CAT 2015–2024? If not, what's the acquisition plan?
2. **Concept graph SME review** (blocks Step 0.4 exit): Who is the SME reviewer, and what is the review turnaround?
3. **Working pad format** (blocks Step 2.4): Plain text only for v1, or include canvas drawing? Canvas doubles attempt payload size and adds a moderation surface.
4. **Diagnostic reset cadence** (blocks Step 1.2 exit criteria): Can users retake the diagnostic? Suggested rule: every 90 days or after 5 mocks completed — confirm.
5. **Free tier definition** (blocks Step 3.4): What does a free tier give? (Suggested: full diagnostic + 7 Tutor days + no mocks.) Needs product decision to wire feature gates.
6. **Process grade gold set** (blocks Step 4.1 eval): The `examiner_grading` eval needs 200 hand-labeled attempts. Who labels them, and by when?
