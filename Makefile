.PHONY: setup dev seed test lint format benchmark docker-up docker-down migrate revision mcp-smoke

setup:
	cd apps/api && uv sync
	cd apps/web && pnpm install

dev:
	docker compose up --build

seed:
	cd apps/api && python -m app.scripts.seed

test:
	cd apps/api && pytest
	cd apps/web && pnpm test -- --run

lint:
	cd apps/api && ruff check app
	cd apps/api && mypy app
	cd apps/web && pnpm lint
	cd apps/web && pnpm typecheck

format:
	cd apps/api && ruff format app
	cd apps/web && pnpm format

benchmark:
	curl -X POST http://localhost:8000/api/benchmarks/run

docker-up:
	docker compose up --build

docker-down:
	docker compose down

migrate:
	cd apps/api && alembic upgrade head

revision:
	cd apps/api && alembic revision --autogenerate -m "$(name)"

mcp-smoke:
	cd apps/api && python -m app.mcp_servers.common --smoke
