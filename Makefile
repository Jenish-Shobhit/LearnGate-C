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
