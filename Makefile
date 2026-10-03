# Keel: two components (backend/, frontend/) + Postgres. See README for first-time setup.
.PHONY: setup db migrate seed api worker web dev test e2e lint typecheck build openapi langfuse langfuse-services langfuse-down

setup:            ## install backend + frontend dependencies
	cd backend && uv sync --extra ocr --extra observability
	cd frontend && pnpm install

db:               ## start Postgres 17 + pgvector in Docker (skip if you run Postgres yourself)
	docker compose up -d postgres

migrate:          ## apply migrations (as the owner role)
	cd backend && uv run keel migrate

seed:             ## demo tenant: owner@demo.keel / keel-demo-2026
	cd backend && uv run keel seed

api:
	cd backend && uv run keel api --reload

worker:
	cd backend && uv run keel worker

web:
	cd frontend && pnpm dev

dev:              ## api + worker + web together (Ctrl-C stops all)
	@trap 'kill 0' INT; (cd backend && uv run keel api --reload) & (cd backend && uv run keel worker) & (cd frontend && pnpm dev) & wait

LANGFUSE = docker compose -f docker-compose.yml -f docker-compose.langfuse.yml

langfuse:         ## whole stack in Docker + self-hosted Langfuse on :3001, Keel pre-wired to trace
	docker compose up -d --wait postgres
	docker compose exec -T postgres psql -q -U postgres -v ON_ERROR_STOP=1 < backend/scripts/langfuse-db.sql
	$(LANGFUSE) up -d --build
	@echo "Keel http://localhost:3000 · Langfuse http://localhost:3001 (admin@keel.local / keel-langfuse-local)"

langfuse-services: ## only Langfuse (+ its Postgres/ClickHouse/Redis/MinIO) for use with `make dev`
	docker compose up -d --wait postgres
	docker compose exec -T postgres psql -q -U postgres -v ON_ERROR_STOP=1 < backend/scripts/langfuse-db.sql
	$(LANGFUSE) up -d langfuse-web langfuse-worker
	@echo "Add to backend/.env: LANGFUSE_BASE_URL=http://localhost:3001 LANGFUSE_PUBLIC_KEY=pk-lf-keel-local LANGFUSE_SECRET_KEY=sk-lf-keel-local"

langfuse-down:    ## stop everything started by `make langfuse` (data volumes are kept)
	$(LANGFUSE) down

openapi:          ## regenerate the typed frontend client from the backend's OpenAPI spec
	cd backend && uv run keel openapi > ../openapi.json
	cd frontend && pnpm exec openapi-ts

lint:
	cd backend && uv run ruff check keel tests migrations && uv run ruff format --check keel tests migrations
	cd frontend && pnpm exec eslint .

typecheck:
	cd backend && uv run mypy keel
	cd frontend && pnpm exec tsc --noEmit

test:             ## backend integration tests against Postgres (keel_test database)
	cd backend && uv run pytest -q

e2e:              ## browser test against a running stack (make dev first)
	cd frontend && pnpm exec playwright test

build:
	cd frontend && pnpm build
