# Spec 0-1: Dev infrastructure & monorepo

**Phase:** 0
**Branch:** spec/0-1-dev-infrastructure-monorepo
**Depends on:** none

---

## Goal

Bootstrap the complete local development environment and CI pipeline so every engineer can clone the repo, run `make dev`, and have the full stack (Next.js 15, FastAPI, Postgres 16, Qdrant 1.9, Redis 7, Temporal dev server) running in under five minutes. At the end of this step the project has a healthy scaffolding: both apps compile, linters and type-checkers pass on empty code, the testing frameworks are wired and ready to receive tests, and the GitHub Actions pipeline is green on `main`. This step unblocks every subsequent step because all tooling, env-var contracts, and project structure are established here.

---

## Deliverables

- `turbo.json` — Turborepo workspace config at repo root
- `package.json` (root) — workspace definition, shared dev-dependency scripts
- `apps/web/` — Next.js 15 scaffold (App Router, TypeScript strict)
  - `apps/web/package.json`
  - `apps/web/next.config.ts`
  - `apps/web/tsconfig.json`
  - `apps/web/eslint.config.mjs`
  - `apps/web/app/layout.tsx`
  - `apps/web/app/page.tsx`
  - `apps/web/app/(app)/dashboard/page.tsx` — stub returning `null`
- `apps/api/` — FastAPI scaffold (Python 3.12, pyproject.toml)
  - `apps/api/pyproject.toml` — uv/pip-tools project file with all runtime + dev deps pinned
  - `apps/api/src/learngate/__init__.py`
  - `apps/api/src/learngate/config.py` — pydantic-settings `Settings` class
  - `apps/api/src/learngate/main.py` — FastAPI app factory with `/healthz` route
  - `apps/api/src/learngate/api/` — empty package
  - `apps/api/mypy.ini` — strict config
  - `apps/api/ruff.toml`
  - `apps/api/tests/__init__.py`
  - `apps/api/tests/conftest.py`
- `packages/shared/` — empty shared types package
  - `packages/shared/package.json`
  - `packages/shared/tsconfig.json`
  - `packages/shared/src/index.ts` — empty barrel export
  - `packages/shared/schema.py` — empty `__init__`; placeholder for Pydantic models added in Step 0.2
- `docker-compose.yml` — Postgres 16, Qdrant 1.9, Redis 7, Temporal dev server
- `Makefile` — targets: `dev`, `test`, `lint`, `seed`, `migrate`
- `.env.example` — all required variables with inline documentation
- `.pre-commit-config.yaml` — ruff, mypy, eslint, tsc hooks
- `.github/workflows/ci.yml` — lint → unit → build pipeline
- `README.md` — one-page quickstart

---

## Implementation plan

### 1. Repo root — Turborepo + workspace

Create `package.json` at repo root:
```json
{
  "name": "learngate-c",
  "private": true,
  "workspaces": ["apps/*", "packages/*"],
  "scripts": {
    "dev": "turbo run dev --parallel",
    "build": "turbo run build",
    "lint": "turbo run lint",
    "test": "turbo run test"
  },
  "devDependencies": {
    "turbo": "^2.x"
  }
}
```

Create `turbo.json`:
```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": { "dependsOn": ["^build"], "outputs": [".next/**", "dist/**"] },
    "dev":   { "cache": false, "persistent": true },
    "lint":  { "outputs": [] },
    "test":  { "outputs": [] }
  }
}
```

> Decision: Turborepo v2 is used (latest stable). The `apps/api` Python project does not participate in Turbo's JS pipeline but is listed in the Makefile targets directly.

### 2. `apps/web` — Next.js 15 scaffold

Bootstrap with `npx create-next-app@latest apps/web --typescript --tailwind --eslint --app --src-dir=false --import-alias="@/*"`.

Post-bootstrap changes:
- `tsconfig.json`: set `"strict": true`, `"noUncheckedIndexedAccess": true`.
- `eslint.config.mjs`: add `@typescript-eslint/recommended` and `import/order` rules; configure `no-console: "warn"`.
- `app/layout.tsx`: minimal root layout with `<html lang="en">`, no third-party deps yet.
- `app/page.tsx`: `export default function Home() { return <div>LearnGate-C</div>; }` — renders without console errors.
- `app/(app)/dashboard/page.tsx`: `export default function Dashboard() { return null; }` — stub only.

Verify `tsc --noEmit` and `next build` both succeed on this empty scaffold.

### 3. `apps/api` — FastAPI scaffold

#### 3.1 `pyproject.toml`

```toml
[project]
name = "learngate-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "python-dotenv>=1.0",
  "httpx>=0.27",       # async HTTP client (used by auth module later)
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-asyncio>=0.23",
  "pytest-cov>=5.0",
  "mypy>=1.10",
  "ruff>=0.4",
  "httpx>=0.27",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

> Decision: `uv` is the package manager. `requirements.txt` is generated from `pyproject.toml` by `uv pip compile` in CI.

#### 3.2 `src/learngate/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    database_url: str
    redis_url: str
    qdrant_url: str
    temporal_host: str = "localhost:7233"
    clerk_secret_key: str = ""       # empty string is safe for local health-check only
    anthropic_api_key: str = ""
    voyage_api_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_public_key: str = ""
    honeycomb_api_key: str = ""
    environment: str = "local"
    log_level: str = "INFO"

settings = Settings()
```

All downstream modules import `from learngate.config import settings` — never `os.environ` directly.

#### 3.3 `src/learngate/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

def create_app() -> FastAPI:
    app = FastAPI(title="LearnGate API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app

app = create_app()
```

Run with: `uvicorn learngate.main:app --reload --host 0.0.0.0 --port 8000`.

#### 3.4 `mypy.ini`

```ini
[mypy]
strict = True
plugins = pydantic.mypy
exclude = tests/
```

#### 3.5 `ruff.toml`

```toml
[lint]
select = ["E", "F", "I", "UP", "B", "SIM", "ANN"]
ignore = ["ANN101", "ANN102"]
line-length = 100

[lint.isort]
known-first-party = ["learngate"]
```

### 4. `packages/shared`

```
packages/shared/
  package.json         (name: "@learngate/shared", version: "0.0.1")
  tsconfig.json        (extends ../../tsconfig.base.json)
  src/index.ts         (empty barrel: export {};)
  schema.py            (Python package init: # Pydantic models added in step 0.2)
```

`apps/web/package.json` should have `"@learngate/shared": "*"` as a workspace dependency so Turbo can resolve it.

### 5. `docker-compose.yml`

```yaml
version: "3.9"
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: learngate
      POSTGRES_PASSWORD: learngate
      POSTGRES_DB: learngate_dev
    ports: ["5432:5432"]
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "learngate"]
      interval: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  qdrant:
    image: qdrant/qdrant:v1.9.0
    ports: ["6333:6333", "6334:6334"]
    volumes: [qdrant_data:/qdrant/storage]

  temporal:
    image: temporalio/auto-setup:1.24
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=learngate
      - POSTGRES_PWD=learngate
      - POSTGRES_SEEDS=postgres
      - TEMPORAL_ADDRESS=temporal:7233
    ports: ["7233:7233"]
    depends_on:
      postgres:
        condition: service_healthy

  temporal-ui:
    image: temporalio/ui:2.29
    environment:
      - TEMPORAL_ADDRESS=temporal:7233
    ports: ["8233:8080"]
    depends_on: [temporal]

volumes:
  postgres_data:
  qdrant_data:
```

> Decision: Temporal uses Postgres as its backing store (same Postgres container) to keep local setup to one DB process. This is acceptable for dev only — production Temporal Cloud has its own storage.

### 6. `Makefile`

```makefile
.PHONY: dev test lint seed migrate

dev:
	docker compose up -d
	cd apps/api && uvicorn learngate.main:app --reload --host 0.0.0.0 --port 8000 &
	cd apps/web && pnpm dev

test:
	cd apps/api && pytest
	cd apps/web && pnpm vitest run --reporter=verbose

lint:
	cd apps/api && ruff check . && mypy src/
	cd apps/web && pnpm eslint . && pnpm tsc --noEmit

seed:
	@echo "Seed targets defined per-step (0.2+). Nothing to seed in step 0.1."

migrate:
	@echo "Alembic migrations defined in step 0.2. Nothing to migrate in step 0.1."
```

### 7. `.env.example`

```dotenv
# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://learngate:learngate@localhost:5432/learngate_dev

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379

# ── Qdrant ────────────────────────────────────────────────────────────────────
QDRANT_URL=http://localhost:6333

# ── Temporal ──────────────────────────────────────────────────────────────────
TEMPORAL_HOST=localhost:7233

# ── Auth (Clerk) ──────────────────────────────────────────────────────────────
# Get from https://dashboard.clerk.com → API Keys
CLERK_SECRET_KEY=sk_test_XXXX
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_XXXX

# ── LLM ───────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-XXXX
VOYAGE_API_KEY=pa-XXXX

# ── Observability ─────────────────────────────────────────────────────────────
HONEYCOMB_API_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=

# ── Runtime ───────────────────────────────────────────────────────────────────
ENVIRONMENT=local   # local | preview | staging | prod
LOG_LEVEL=INFO
```

Variables marked `NEXT_PUBLIC_*` are exposed to the browser; all others are server-only.

### 8. `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.10
    hooks:
      - id: ruff
        args: ["--fix"]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
        args: ["--config-file=apps/api/mypy.ini"]
        files: ^apps/api/
        additional_dependencies:
          - pydantic
          - pydantic-settings
  - repo: local
    hooks:
      - id: eslint
        name: eslint
        language: node
        entry: pnpm --filter @learngate/web eslint
        files: \.(ts|tsx)$
      - id: tsc
        name: tsc
        language: node
        entry: pnpm --filter @learngate/web tsc --noEmit
        pass_filenames: false
```

> Decision: pre-commit hooks run on staged files only (default). CI re-runs them on the full tree. Failing hook blocks the commit with a message showing how to fix.

### 9. `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with: { version: "0.4.x" }
      - uses: pnpm/action-setup@v3
        with: { version: "9" }
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: uv sync --project apps/api --extra dev
      - run: pnpm install --frozen-lockfile
      - run: cd apps/api && ruff check .
      - run: cd apps/api && mypy src/
      - run: pnpm --filter @learngate/web eslint .
      - run: pnpm --filter @learngate/web tsc --noEmit

  unit:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with: { version: "0.4.x" }
      - uses: pnpm/action-setup@v3
        with: { version: "9" }
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: uv sync --project apps/api --extra dev
      - run: pnpm install --frozen-lockfile
      - run: cd apps/api && pytest --co -q    # collect-only to confirm test framework wired
      - run: pnpm --filter @learngate/web vitest run --reporter=verbose

  build:
    runs-on: ubuntu-latest
    needs: unit
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v3
        with: { version: "9" }
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - run: pnpm install --frozen-lockfile
      - run: pnpm --filter @learngate/web build
```

No secrets needed in CI for Step 0.1 — the `apps/api` health-check route has no DB dependency.

### 10. `apps/api/tests/conftest.py`

```python
import pytest
from fastapi.testclient import TestClient
from learngate.main import app

@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
```

This is the only fixture file in Step 0.1. All DB-touching fixtures are introduced in Step 0.2.

### 11. Health-check smoke test

Create `apps/api/tests/test_healthz.py`:

```python
from fastapi.testclient import TestClient

def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

Create `apps/web/src/__tests__/home.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import Home from "../app/page";

test("renders root page without crashing", () => {
  render(<Home />);
  expect(document.body).toBeTruthy();
});
```

> Decision: `@testing-library/react` + `vitest` is the web testing stack. Add `@testing-library/react`, `@testing-library/jest-dom`, `vitest`, `@vitejs/plugin-react`, and `jsdom` to `apps/web` dev dependencies.

---

## Acceptance criteria

1. Running `cp .env.example .env.local && make dev` starts all five Docker containers (Postgres, Redis, Qdrant, Temporal, Temporal UI) and both apps (`apps/api` on port 8000, `apps/web` on port 3000) with zero additional manual steps on a clean machine that has Docker, Node 22, pnpm 9, Python 3.12, and uv installed.
2. `GET http://localhost:8000/healthz` returns `{"status": "ok"}` with HTTP 200 within 500 ms after `make dev` starts.
3. `http://localhost:3000` renders the Next.js shell (text "LearnGate-C") with zero browser console errors.
4. `http://localhost:8233` (Temporal UI) loads and shows the dev server with no active workflows.
5. `make lint` completes with exit code 0: `ruff check` passes, `mypy --strict` passes on `apps/api/src/`, `eslint` passes on `apps/web/`, `tsc --noEmit` passes on `apps/web/`.
6. `pytest --co` (collect-only) on `apps/api/tests/` exits 0 (at least `test_healthz.py` collected).
7. `vitest run --reporter=verbose` on `apps/web/` exits 0 (at least `home.test.tsx` passed).
8. GitHub Actions pipeline runs to green on a push to `main`: all three jobs (`lint`, `unit`, `build`) succeed.
9. `.env.example` contains entries for every variable referenced in `Settings` (verified by running `python -c "from learngate.config import Settings; Settings()"` with only `.env.example` values substituted — no `ValidationError` for required fields that have documented defaults).

---

## Out of scope

- Database schema (migrations, Alembic setup) — handled in Step 0.2.
- Row-level security policies — Step 0.2.
- Auth integration (Clerk, JWT verification) — Step 0.3.
- OpenTelemetry instrumentation — Step 0.3.
- Concept graph seeding — Step 0.4.
- PYQ ingestion — Step 0.5.
- Any LLM calls or agent code.
- Production deployment (Fly, Vercel, Supabase provisioning) — Step 0.3 sets up the API shell; full CD wiring is part of Step 4.1.
- `make seed` and `make migrate` targets are stubbed with informational messages; they become functional in Steps 0.2 and 0.4 respectively.

---

## Tests and validation

### T-01: Health endpoint returns `{"status": "ok"}`
- **Name:** `test_healthz`
- **Type:** unit
- **File:** `apps/api/tests/test_healthz.py`
- **Setup:** `TestClient(app)` fixture from `conftest.py`; no database required.
- **Action:** `client.get("/healthz")`
- **Expected outcome:** `status_code == 200`; `response.json() == {"status": "ok"}`

### T-02: Next.js home page renders without exceptions
- **Name:** `renders root page without crashing`
- **Type:** unit
- **File:** `apps/web/src/__tests__/home.test.tsx`
- **Setup:** Vitest + jsdom environment; no network.
- **Action:** `render(<Home />)`
- **Expected outcome:** No thrown exception; `document.body` is truthy.

### T-03: `make lint` exits 0 on scaffolding
- **Name:** lint clean baseline
- **Type:** integration (CI)
- **File:** `.github/workflows/ci.yml` → `lint` job
- **Setup:** Fresh checkout, `uv sync`, `pnpm install`.
- **Action:** Run `ruff check .`, `mypy src/`, `eslint .`, `tsc --noEmit` sequentially.
- **Expected outcome:** All four commands exit 0; no warnings treated as errors.

### T-04: `pytest --co` collects without errors
- **Name:** pytest collection baseline
- **Type:** integration (CI)
- **File:** `.github/workflows/ci.yml` → `unit` job
- **Setup:** `uv sync --extra dev`; no running services needed.
- **Action:** `pytest --co -q`
- **Expected outcome:** Exit 0; output contains `test_healthz.py::test_healthz`.

### T-05: `vitest run` exits 0 on empty web scaffold
- **Name:** vitest baseline
- **Type:** integration (CI)
- **File:** `.github/workflows/ci.yml` → `unit` job
- **Setup:** `pnpm install`.
- **Action:** `pnpm vitest run --reporter=verbose`
- **Expected outcome:** Exit 0; `home.test.tsx` reports passed.

### T-06: `next build` succeeds on empty scaffold
- **Name:** web build succeeds
- **Type:** integration (CI)
- **File:** `.github/workflows/ci.yml` → `build` job
- **Setup:** `pnpm install`.
- **Action:** `pnpm --filter @learngate/web build`
- **Expected outcome:** Exit 0; no TypeScript or ESLint errors during build.

### T-07: Manual smoke — full `make dev` on a fresh machine
- **Name:** dev stack smoke test
- **Type:** manual
- **File:** n/a — checklist in README
- **Setup:** Machine with Docker, Node 22, pnpm 9, Python 3.12, uv installed. Repo cloned fresh. `cp .env.example .env.local`.
- **Action:** `make dev` (single command).
- **Expected outcome:**
  - Docker containers healthy (check `docker compose ps`).
  - `curl http://localhost:8000/healthz` → `{"status": "ok"}` within 500 ms.
  - `http://localhost:3000` renders "LearnGate-C" in browser, zero console errors.
  - `http://localhost:8233` Temporal UI shows dev server, no workflows.
