# LearnGate-C — Master Specification

**Version:** 0.1 (founding draft)
**Owner:** Jenish
**Last updated:** 2026-04-29
**Status:** Ideation → Spec

---

## 1. One-line pitch

LearnGate-C is an agentic CAT-prep platform that figures out what *you* don't know, builds a study plan around it, teaches you using the actual past-year question (PYQ) corpus as ground truth, and keeps re-planning as your performance changes — so two students never get the same course.

---

## 2. Why this exists

Modern LMSs (Coursera, Udemy, BYJU's, Unacademy CAT modules, even most "AI tutors") share one fundamental flaw: **the course is the unit of learning, not the learner**. You authenticate, you unlock a syllabus, you grind through fixed lectures and fixed quizzes. The platform doesn't actually know you. It can't tell whether you bombed Geometry because of weak fundamentals, careless arithmetic, or a misread of the question stem — and it certainly can't change the next 30 days of your prep based on that distinction.

The original web — pre-LMS — was actually closer to good learning. A motivated student would hop between Khan Academy, a forum thread, a Stack Exchange answer, and a YouTube playlist, *self-routing* based on what felt unclear. That worked, but only for students with the metacognition to self-route. It excluded everyone who didn't already know how to learn.

The thesis of LearnGate-C: **an agent can do that self-routing for you, continuously, with better data than you have about yourself.** It can watch your timing, your error types, your re-read patterns, your confidence calibration, and route you to the next best thing to study, the next best question to attempt, and the next concept to revisit before it decays.

We are building this specifically for **CAT** because:

- The exam has a finite, well-defined surface area (three sections, ~25 years of PYQs, recurring question archetypes).
- The PYQ corpus is rich enough to ground a RAG system that genuinely teaches, not just retrieves.
- The student population is high-intent, score-obsessed, and willing to pay for an edge.
- Sectional cutoffs + percentile scoring make personalized weakness-targeting *measurably* valuable.

---

## 3. Target user

Primary: A first- or second-time CAT aspirant, age 21–26, currently studying 2–6 hours/day with 4–10 months until exam day. They are stuck on at least one of three failure modes:
1. **The plateau** — mocks have stagnated at the same percentile for 4+ weeks.
2. **The blind spot** — they don't know which sub-topics are dragging them down.
3. **The plan vacuum** — they have material but no idea what to do *today*.

Secondary: Working professionals doing CAT alongside a job who need ruthless prioritization (they have 90 minutes a day, what should they do with it?).

Out of scope for v1: GMAT, GRE, banking exams, JEE, school-age learners. The architecture should generalize, but the wedge is CAT.

---

## 4. Core principles

These are the design commitments that should win every product argument:

1. **Diagnose before teaching.** No content is shown until the system has a working model of the learner. Even the diagnostic itself adapts.
2. **The PYQ is the textbook.** Every concept is anchored to the actual questions that have appeared in CAT. Theory is taught *to explain a question*, not the other way around.
3. **Plans are disposable.** The study plan is regenerated as often as the data justifies — daily if needed. A plan from two weeks ago is not sacred.
4. **Feedback loops over content libraries.** We are not winning by having more videos. We win by having tighter loops between *attempt → diagnosis → intervention → re-test*.
5. **Explainability over magic.** The student should always be able to ask "why am I doing this right now?" and get a real answer grounded in their own data.
6. **Mastery is probabilistic, not binary.** A topic is never "done." It has a current mastery estimate that decays with time and recovers with practice.
7. **Time is the scarcest resource.** Every feature is judged on minutes-of-study saved or percentile-points-per-hour gained.

---

## 5. The agent system

LearnGate-C is structured as a **multi-agent system** rather than a monolithic chatbot. Each agent has a narrow job, its own tools, and its own context. They coordinate through a shared learner state.

### 5.1 The agents

**Diagnostician**
- Runs on first signup and on demand (e.g., post-mock).
- Administers an adaptive diagnostic (Item Response Theory-style — easier questions if you fail, harder if you pass).
- Outputs a **mastery vector** across the concept graph (see §7.2) and a **error-type profile** (conceptual gap vs. application gap vs. silly mistake vs. timing pressure).

**Planner**
- Consumes the mastery vector, target percentile, exam date, and available study hours/day.
- Outputs a study plan: today's session, this week's arc, this month's milestones.
- Re-runs nightly. Re-runs immediately after any "significant" event (mock attempt, big swing in a topic's accuracy, missed days).

**Tutor**
- The agent the student actually talks to during a study session.
- Teaches Socratically: leads with a question, doesn't dump theory.
- Has tools to: pull a relevant PYQ, generate a parallel problem, fetch a video segment, draw a diagram, mark a confusion to revisit.
- Does *not* decide what to teach — that's the Planner's job. The Tutor executes a session prescribed by the Planner.

**Examiner**
- Generates and grades problem sets and full mocks.
- Crucially, it grades *process*, not just answer — was the method right, was the time reasonable, was the wrong answer a near-miss or a misconception?
- Calibrates question difficulty against the IRT model and against PYQ benchmarks.

**Analyst**
- The retrospective agent. Runs after every session and every mock.
- Updates the mastery vector. Detects regressions. Flags when the Planner's predictions are diverging from reality.
- Writes the **session debrief** the student sees ("here's what changed about you today").

**Coach** (stretch goal — phase 2)
- Watches motivation and adherence patterns.
- Nudges, reschedules, or recommends a rest day.
- Detects burnout signals (declining accuracy + declining session length + skipped days) before they cascade.

### 5.2 How they coordinate

There is no agent-to-agent free-for-all. They share a single **Learner State** (see §6) and operate in a **fixed orchestration**:

```
[Session start]
  Planner → reads Learner State → emits today's session plan
  Tutor    → executes session, emits per-question telemetry
[Session end]
  Examiner → grades, scores, compares to PYQ baselines
  Analyst  → updates mastery vector + writes debrief
  Planner  → (overnight) regenerates next day's plan
```

Each agent's output is a typed artifact written to the Learner State. No agent calls another directly — they communicate by mutating shared state. This makes the system inspectable (you can replay any day from the state log) and testable (each agent can be evaluated in isolation against fixtures).

---

## 6. The Learner State (the central data object)

This is the single most important object in the system. Everything else exists to read or update it.

A Learner State contains:

- **Identity & goals** — name, target percentile, exam date, hours/day available, weakness self-report.
- **Mastery vector** — for every node in the concept graph: current mastery probability (0–1), confidence interval, last-attempted timestamp, decay rate.
- **Error-type profile** — running distribution across {conceptual, procedural, careless, time-pressured, misread}.
- **Attempt log** — every question ever attempted: question id, response, time taken, was-flagged, confidence rating, final answer change count.
- **Session log** — every study session: planned vs. actual, what got skipped, subjective difficulty rating.
- **Mock log** — full mocks with sectional/overall scores, predicted percentile, deltas from previous mock.
- **Plan history** — every plan the Planner has produced (kept for replay/audit).
- **Open loops** — questions/concepts the student flagged as confusing and hasn't resolved.

Storage: a relational core (Postgres) for structured logs + a vector store for embeddings of free-text artifacts (notes, doubts, debriefs). Keep the schema migration-friendly — this object will evolve every week in early phases.

---

## 7. The CAT knowledge layer

### 7.1 The PYQ RAG

The defining asset of LearnGate-C. We ingest:
- ~25 years of CAT papers + answer keys + official solutions where available.
- IIM mock papers and major coaching mocks (TIME, IMS, CL) where licensable, otherwise our own.
- Top-rated solution explanations from the open web (with proper attribution).

For each question:
- Question text, options, correct answer, year, slot, section.
- **Concept tags** (multi-label, mapped to the concept graph).
- **Difficulty rating** (calibrated via IRT once we have enough user data; bootstrapped from official sources).
- **Question archetype** — the recurring template it belongs to (e.g., "Para-jumble with thematic anchor", "TSD with relative motion").
- **Solution embeddings** — for semantic retrieval ("show me questions where the trick is similar to this one").

The RAG is used by:
- The Tutor — to fetch the most pedagogically relevant PYQ for the current micro-topic.
- The Examiner — to generate "in the style of" problems and to ground difficulty.
- The Analyst — to find historical questions where this student previously failed in a similar way.

### 7.2 The Concept Graph

A directed graph of CAT concepts with prerequisite edges. Example slice:

```
Arithmetic → Ratios → Mixtures & Alligations
Arithmetic → Percentages → Profit/Loss → Discounts
Algebra → Quadratic Equations → Roots & Discriminant
RC → Inference questions → "Author's tone" subtype
```

Why a graph and not a flat tag list: when a student fails on Mixtures, the system needs to know whether to drill Mixtures itself, fall back to Ratios, or fall back further to fractions. The graph lets the Planner decide.

The graph is hand-curated initially (CAT's surface area is small enough to make this tractable — likely <500 nodes) and refined via data ("students who fail X disproportionately also fail Y → add edge").

### 7.3 Mastery estimation

We use **Bayesian Knowledge Tracing** (BKT) per concept node, with two modifications:
- Decay: mastery drops over time without practice (half-life tuned per concept).
- Cross-node lift: success on a downstream concept lifts the prior on its prerequisites.

This is what powers the mastery vector in the Learner State.

---

## 8. Feature set

Organized by user-visible surface, not by phase. Phasing is in §11.

### 8.1 Onboarding & diagnostic
- Goal-setting interview (target percentile, exam date, hours/day, prior prep).
- Adaptive diagnostic test (~60–90 min, IRT-driven).
- First mastery vector visualized as a heatmap across the concept graph.
- "Your first study plan" — the Planner's first output, explained.

### 8.2 Daily study session
- Today's plan card: 3–5 blocks, each with a clear purpose ("close the gap on Time-Speed-Distance", "spaced review of Para-completion").
- Tutor session — interactive, Socratic, anchored to PYQs.
- Per-block debrief: what changed in your mastery vector, what's next.

### 8.3 Practice & problem sets
- "Drill mode" — high-volume practice on a chosen sub-topic, difficulty auto-adjusts.
- "Mixed mode" — randomized across weak areas.
- "PYQ mode" — practice actual past papers, year by year or shuffled.
- Every wrong answer triggers a Tutor pop-in: "want to debug this now or save for later?"

### 8.4 Mocks
- Full-length CAT mocks with the real interface (3 sections, sectional timers, scratchpad).
- Post-mock analysis is the centerpiece: per-question time, per-concept accuracy, error-type breakdown, percentile prediction with confidence interval.
- "What if" simulator: "if you'd skipped Q14 and Q22, your VARC score would have been +6."
- Side-by-side comparison with all your previous mocks.

### 8.5 Analytics dashboard
- Mastery heatmap (concept graph, color-coded).
- Trend charts (accuracy, speed, percentile over time).
- Error-type pie chart with drill-down to actual questions.
- Time allocation: planned vs. actual study hours.
- Predicted percentile band with the assumptions visible.

### 8.6 Doubt resolution
- Ask the Tutor anything mid-session.
- Persistent "open loops" inbox — confusing questions you flagged, surfaced again at the right time.
- Long-form explainers generated on demand, grounded in the PYQ corpus (not freeform LLM hallucination).

### 8.7 Spaced review
- Automatic resurfacing of weak/decayed concepts.
- Anki-style flashcards generated from your own mistakes (your mistakes, not generic ones).

### 8.8 Social / accountability (phase 2)
- Anonymous percentile leaderboards by study cohort.
- Study streaks, but with a twist — the streak counts *quality minutes*, not raw minutes (you can't streak by opening the app for 30 seconds).
- Optional study buddy matching by mastery profile.

---

## 9. Technical architecture

### 9.1 High-level

```
[ Web client (Next.js) ]
        │
        ▼
[ API gateway (FastAPI) ] ──► [ Auth (Clerk/NextAuth) ]
        │
        ├──► [ Agent orchestrator (LangGraph) ]
        │         │
        │         ├──► [ LLM (Claude Sonnet/Opus) ]
        │         ├──► [ Tools: PYQ retrieve, problem gen, grader ]
        │         └──► [ Learner State R/W ]
        │
        ├──► [ Postgres (learner state, attempts, plans) ]
        ├──► [ Vector DB (Qdrant) — PYQ + solutions + notes ]
        ├──► [ Object store (S3) — papers, audio, video clips ]
        └──► [ Analytics warehouse (DuckDB/ClickHouse) ]
```

### 9.2 Tech stack (proposed, opinionated)

- **Frontend:** Next.js (App Router), React, Tailwind, shadcn/ui. Heavy use of streaming for Tutor responses.
- **Backend:** Python 3.12, FastAPI for HTTP, Celery or Temporal for background jobs (overnight planner re-runs).
- **Agent framework:** LangGraph (typed state, easy to inspect). Avoid LangChain abstractions where possible.
- **LLMs:** Claude Sonnet for the Tutor (latency + cost), Claude Opus for the Planner and Analyst (deeper reasoning, runs less often). Allow swap to other providers behind an interface.
- **Vector DB:** Qdrant (self-hostable, good filters). Pinecone if we want to skip ops.
- **Relational DB:** Postgres (Supabase for managed + auth).
- **Cache:** Redis for session state, short-term LLM responses.
- **Auth:** Clerk for v1 (fast). Move to NextAuth + custom if needed.
- **Hosting:** Vercel (web), Railway/Fly (backend), managed Postgres.
- **Observability:** OpenTelemetry → Honeycomb. Specific LLM tracing via Langfuse or custom.
- **Feature flags:** Statsig or GrowthBook.

### 9.3 Why these choices
- **Python over Node for backend:** the agent + ML ecosystem is in Python. Don't fight it.
- **LangGraph over autonomous frameworks (AutoGPT-style):** we want deterministic orchestration, not emergent agent chatter. The agent topology is fixed.
- **Postgres + Qdrant, not a single multimodal DB:** structured data and vectors have different access patterns. Don't conflate them.
- **Claude over GPT-4 default:** stronger long-context reasoning for the Planner; better at refusing to hallucinate when grounded in RAG.

### 9.4 Critical non-functional requirements
- **Tutor first-token latency: <800ms.** Anything slower kills the Socratic feel.
- **Mock interface latency: <100ms input echo.** The real CAT is responsive, ours has to be too.
- **Plan regeneration: nightly batch, <5 min per user.**
- **PYQ retrieval: <300ms p95.**
- **Cost per active student per month:** target <$5 in inference at v1, <$2 at scale. Caching and aggressive use of Sonnet over Opus get us there.

---

## 10. The data flywheel

This is the long-term moat. Every student attempt is a labeled data point: question + their state + outcome. Over time:

- Difficulty calibration gets sharper (real IRT, not bootstrapped).
- The concept graph gets refined from co-failure patterns.
- The Tutor gets better at predicting which intervention works for which error-type.
- The Planner's predictions ("if you do X, your percentile goes up by Y") become trustworthy.

We should explicitly design for this from day one: every agent decision logs its rationale, every prediction logs what it predicted vs. what happened, every intervention logs the before/after mastery delta. This is the difference between a product that gets smarter with users and one that just adds users.

---

## 11. Roadmap

### Phase 0 — Foundations (weeks 0–4)
- Concept graph v1 (hand-curated).
- PYQ corpus ingested, tagged, embedded for at least 2015–2024.
- Learner State schema + Postgres setup.
- Auth + basic web shell.
- *Exit criteria:* a developer can log in and see a static dashboard backed by real data.

### Phase 1 — The diagnostic loop (weeks 4–8)
- Diagnostician agent (adaptive test).
- Mastery vector v1 (BKT, no decay yet).
- First Planner output (rule-based, not LLM-generated).
- *Exit criteria:* a user can take a diagnostic and get a 7-day study plan they could actually follow.

### Phase 2 — The tutor loop (weeks 8–14)
- Tutor agent integrated with PYQ RAG.
- Per-question telemetry capture.
- Examiner agent for grading + parallel problem generation.
- Analyst agent producing session debriefs.
- *Exit criteria:* a user can complete a full study session end-to-end with the agents in the loop.

### Phase 3 — Mocks & analytics (weeks 14–20)
- Full-length mock interface.
- Post-mock analytics with what-if simulator.
- Trend dashboard.
- Spaced review.
- *Exit criteria:* the product is genuinely useful as a sole CAT-prep tool for at least one cohort.

### Phase 4 — Polish, retention, scale (weeks 20+)
- Coach agent, streak/adherence systems.
- Social features (carefully).
- Mobile (likely PWA first, native later).
- Cost optimization pass.

### Phase 5 — Generalize beyond CAT
- Abstract the concept graph + PYQ ingestion pipeline.
- GMAT, GRE, banking exams as next domains.
- Open the platform to "bring your own exam" for educators.

---

## 12. Success metrics

**Learning outcomes (the only ones that ultimately matter):**
- Mock percentile delta from week 1 to exam week, vs. a matched control.
- Mastery vector improvement curves.
- Self-reported confidence, pre vs. post.

**Engagement (leading indicators):**
- DAU / WAU.
- Avg. quality study minutes per active day.
- Session completion rate (planned vs. actual).
- Streak length distribution.

**Product health:**
- Tutor response latency p50/p95.
- Plan adherence rate (did the user do what was prescribed?).
- Plan accuracy (did the predicted mastery delta match the actual?).
- Cost per active user per month.

---

## 13. Risks & mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinates wrong CAT solutions | Tutor is RAG-grounded; every claim must cite a PYQ or vetted source; eval suite of 500+ questions where the Tutor must not fabricate. |
| Diagnostic feels like an exam, drives users away | Make it conversational, break into 3 sittings, visible progress, surface insight after each block. |
| Concept graph is wrong | Treat it as a living document; instrument co-failure patterns to find missing edges; coaching SME review monthly. |
| Inference cost explodes | Aggressive Sonnet-first routing, response caching for identical contexts, batch overnight planner runs. |
| Students cheat the system to game streaks/scores | Quality-minutes over raw minutes; surface predicted percentile rather than vanity scores; align metrics with exam outcomes. |
| Content licensing for PYQs | Use only post-2010 official CAT papers (publicly available); generate mocks ourselves; license coaching mocks selectively. |
| Privacy of attempt data | Per-user encryption at rest; clear data export + delete; never train shared models on identifying data without consent. |

---

## 14. Open questions (to resolve before building)

1. **Pricing model.** Subscription? Pay-per-mock? Free tier with paid tutor? Indian CAT market is price-sensitive — we need a model that doesn't require ₹15k/year to break even.
2. **Mobile-first or web-first?** Indian students study heavily on mobile. PWA might not be enough.
3. **Video content — produce, license, or skip?** The thesis is feedback loops over content libraries, but some students will demand video. Decide what minimum bar is acceptable.
4. **Solo founder build vs. team?** Some of the agent work is ~unbounded R&D. Need to scope ruthlessly to ship Phase 1.
5. **Tutor language.** Hinglish? English only? Code-switching is common in Indian CAT prep YouTube — does our Tutor do it?
6. **Anti-cheating in mocks.** Do we proctor? Webcam? Or trust the student because the data only matters to them?
7. **Concept graph ownership.** Open-source the graph for credibility, or keep proprietary as a moat?

---

## 15. North-star vignette

> It's 7:00 AM. Riya opens LearnGate-C. The dashboard says: "Yesterday you closed the gap on Time-Speed-Distance — accuracy up from 54% to 71%. Today: 40 minutes on Para-completion (your VARC drag), 25 minutes on a fresh PYQ set from CAT 2019 Slot 2, 15 minutes spaced review on Mixtures."
>
> She taps in. The Tutor opens with: "Here's a 2018 RC passage. Read it once, then I'll show you the question — don't read the question first. I want to see how you build the mental map."
>
> Forty minutes later, the Analyst has updated her mastery vector. Para-completion is up. But her time-per-question on RC inference questions has been creeping up for three days. The Planner notices. Tomorrow's plan will spend less time on Para-completion and more on building RC reading speed under timer.
>
> No human did this. No course was bought. No syllabus was followed. Riya is being taught by a system that knows her better, by Saturday, than any tutor would in a month.

That's the product.

---

## Appendix A — Glossary

- **PYQ:** Previous Year Question.
- **Mastery vector:** Per-concept estimate of student proficiency, 0–1 with confidence intervals.
- **Concept graph:** Directed graph of CAT topics with prerequisite edges.
- **BKT:** Bayesian Knowledge Tracing.
- **IRT:** Item Response Theory.
- **Learner State:** Single source of truth for everything the system knows about a student.
- **Open loop:** A flagged confusion the student hasn't resolved yet.

## Appendix B — What this spec is *not*

- It is not a UI design doc. Wireframes come later.
- It is not an engineering implementation plan. Tickets come from the roadmap, not from this doc.
- It is not a business plan. Pricing, GTM, hiring are out of scope here.
- It is not final. Treat every section as a v0.1 — challenge any of it as we learn more.
