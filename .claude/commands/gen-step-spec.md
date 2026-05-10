Generate a detailed individual spec file for one build step from build_plan.md, then create and switch to a matching git branch.

## Input

`$ARGUMENTS` is a step identifier in `X.Y` format matching the "Step" column in build_plan.md (e.g. `0.1`, `1.3`, `2.4`, `3.2`).

## What to do

### 1. Parse the step number

Accept `$ARGUMENTS` as a string like `0.1` or `2.3`. If the input is a bare integer (e.g. `1`) treat it as a phase number and tell the user to supply a sub-step (e.g. `1.1`).

Derive naming tokens from the step identifier:
- **Padded id**: replace `.` with `-` (e.g. `0.1` → `0-1`, `2.3` → `2-3`).
- **Slug**: read the step's heading from build_plan.md, lowercase it, replace all spaces and non-alphanumeric characters with underscores, collapse consecutive underscores, strip leading/trailing underscores. (e.g. "Dev infrastructure & monorepo" → `dev_infrastructure_monorepo`).
- **Spec file path**: `specs/<padded-id>_<slug>_spec.md` (e.g. `specs/0-1_dev_infrastructure_monorepo_spec.md`).
- **Branch name**: `spec/<padded-id>-<slug-with-dashes>` where underscores become dashes (e.g. `spec/0-1-dev-infrastructure-monorepo`).

### 2. Read the source documents

Read `build_plan.md` in full. Locate the section whose heading matches `## Step <X.Y>`. Extract:
- Step heading (the `##` line title after the step number)
- Goal paragraph
- Scope bullet list (the "What you build" items)
- Acceptance criteria checklist
- Tests section

Also read `implementation_spec.md` and `master_spec.md` for additional implementation detail relevant to this step (architectural decisions, schemas, algorithms, prompts, API contracts, performance budgets). Use these to **expand** the spec well beyond what build_plan.md alone contains — the goal is a self-contained document a developer can implement from without reading anything else.

### 3. Write the spec file

Create `specs/<padded-id>_<slug>_spec.md` with the structure below. Every section must be fully expanded — do not copy the build_plan.md text verbatim. Infer concrete file paths, function signatures, Pydantic models, SQL, CLI commands, and edge cases from the source documents. If something is genuinely ambiguous, make a defensible v1 decision and call it out with `> Decision:`.

```
# Spec <padded-id>: <Step heading>

**Phase:** <phase number>
**Branch:** <branch-name>
**Depends on:** <comma-separated list of step ids this step requires to be done first, or "none">

---

## Goal

One paragraph. What ships at the end of this step, why it unblocks the next step, and what user-observable behaviour becomes possible.

---

## Deliverables

Bulleted list of every file, module, CLI command, migration file, or UI route that must exist and work when this step is declared done. Include full relative paths from the repo root.

---

## Implementation plan

Numbered sub-steps. Each sub-step must name the exact file(s) to create or edit and describe the logic to implement in enough detail that a developer can start typing without guessing. Include:

- Function signatures with argument types and return types (Python type hints or TypeScript).
- Pydantic model definitions or TypeScript interfaces where a data shape is introduced.
- SQL DDL or Alembic migration snippets where the database changes.
- External library calls with import paths (e.g. `from langchain_core.runnables import RunnablePassthrough`).
- Error cases and how each is handled (raise, degrade, return 4xx, emit event, etc.).
- Environment variables and config keys introduced.
- For frontend work: component prop interfaces and state shapes.

---

## Acceptance criteria

Numbered list. Each criterion is a concrete, independently verifiable statement:
- "Running `X` produces output matching `Y`."
- "`Z` returns `HTTP 422` when field `foo` is missing."
- "Query `SELECT ...` returns `N` rows after seeding."

Derive from build_plan.md but expand with concrete values, thresholds, and commands.

---

## Out of scope

Bulleted list. Name what this step explicitly does NOT implement. For each item, name the step number that will handle it (if known).

---

## Tests and validation

For each test provide:
- **Name** — short descriptive name.
- **Type** — `unit`, `integration`, `e2e`, `eval`, or `manual`.
- **File** — path inside `tests/` (e.g. `tests/unit/mastery/test_bkt.py`).
- **Setup** — what state/fixtures are needed.
- **Action** — what is called or run.
- **Expected outcome** — exact return value, exception type, HTTP status, or database state.

Include at least:
- 3–5 unit tests covering the core algorithm or transformation.
- 2–3 integration tests covering the happy path and one failure/edge path.
- 1 E2E or manual smoke test confirming the deliverable works end-to-end.
- Any eval suite criteria from implementation_spec.md §33 that belong to this step.
```

### 4. Create and switch to the git branch

Run:
```
git checkout -b <branch-name>
```

If the branch already exists, run:
```
git checkout <branch-name>
```

Report which action was taken (created new vs. switched to existing).

### 5. Confirm to the user

Output exactly:
```
Spec file : specs/<padded-id>_<slug>_spec.md
Branch    : <branch-name> (<created|already existed — switched>)
Summary   : <one sentence describing what this step implements>
```
