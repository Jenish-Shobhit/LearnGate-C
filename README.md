# LearnGate-C ( Still in development) 

Agentic CAT-prep platform — adaptive diagnostics, personalized study plans, Socratic tutor, and PYQ-grounded learning.

## Prerequisites

| Tool | Version |
|---|---|
| Docker | 24+ |
| Node.js | 22+ |
| pnpm | 9+ |
| Python | 3.12+ |
| uv | 0.4+ |

## Quickstart

```bash
# 1. Clone and enter the repo
git clone <repo-url> && cd learngate-c

# 2. Copy environment variables
cp .env.example .env.local
# Edit .env.local — fill in CLERK_SECRET_KEY, ANTHROPIC_API_KEY, etc.

# 3. Install JS dependencies
pnpm install

# 4. Install Python dependencies
cd apps/api && uv sync --extra dev && cd ../..

# 5. Start everything
make dev
```

## Verify the stack is running

| Service | URL | Expected |
|---|---|---|
| API health | http://localhost:8000/healthz | `{"status":"ok"}` |
| Web app | http://localhost:3000 | "LearnGate-C" |
| Temporal UI | http://localhost:8233 | Dev server, no workflows |
| Qdrant dashboard | http://localhost:6333/dashboard | Collections page |

## Common tasks

```bash
make lint      # ruff + mypy (api), eslint + tsc (web)
make test      # pytest (api), vitest (web)
make migrate   # Alembic upgrade head (available from step 0.2)
make seed      # Seed concept graph + PYQ corpus (available from step 0.4)
```

## Project structure

```
apps/
  api/          FastAPI backend (Python 3.12)
  web/          Next.js 15 frontend (TypeScript)
packages/
  shared/       Shared types (TS + Python)
specs/          Step-level implementation specs
docker-compose.yml
Makefile
```
