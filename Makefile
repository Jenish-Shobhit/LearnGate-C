.PHONY: dev test lint seed migrate migrate-down migrate-check

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
	@test -f .env.local || (echo "Missing .env.local — run: cp .env.example .env.local" && exit 1)
	cd apps/api && set -a && source ../../.env.local && set +a && alembic upgrade head

migrate-down:
	@test -f .env.local || (echo "Missing .env.local — run: cp .env.example .env.local" && exit 1)
	cd apps/api && set -a && source ../../.env.local && set +a && alembic downgrade base

migrate-check:
	@test -f .env.local || (echo "Missing .env.local — run: cp .env.example .env.local" && exit 1)
	cd apps/api && set -a && source ../../.env.local && set +a && alembic check
