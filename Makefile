SHELL := /bin/sh

.PHONY: setup run stop down test lint typecheck format migrate migration migration-check frontend-build frontend-image backend-build audit validate openapi openapi-check seed

setup:
	./scripts/setup.sh

run:
	docker compose up --build

stop:
	docker compose stop

down:
	docker compose down

test:
	cd backend && uv run pytest
	cd frontend && npm test -- --run

lint:
	cd backend && uv run ruff check src tests
	cd backend && uv run ruff format --check src tests
	cd frontend && npm run format:check
	cd frontend && npm run lint
	git diff --check

typecheck:
	cd backend && uv run mypy src tests
	cd frontend && npm run typecheck

format:
	cd backend && uv run ruff check --fix src tests
	cd backend && uv run ruff format src tests
	cd frontend && npm run format

migrate:
	cd backend && uv run alembic upgrade head

migration:
	@test -n "$(name)" || (echo "usage: make migration name='description'" && exit 2)
	cd backend && uv run alembic revision --autogenerate -m "$(name)"

migration-check:
	cd backend && uv run alembic current --check-heads
	cd backend && uv run alembic check

frontend-build:
	cd frontend && npm run build

frontend-image:
	docker build --target runtime -t ownsis-frontend:local frontend

backend-build:
	docker build --target runtime -t ownsis-backend:local backend

audit:
	cd backend && uv run pip-audit
	cd frontend && npm audit --audit-level=high
	cd tools/openapi-contract && npm audit --audit-level=high

openapi:
	cd backend && uv run python ../scripts/export_openapi.py
	cd frontend && npm run generate:api

openapi-check:
	cd backend && uv run python ../scripts/export_openapi.py --check
	cd frontend && npm run check:api

seed:
	cd backend && PYTHONPATH=src uv run python ../scripts/seed_development.py

validate: openapi-check lint typecheck test frontend-build audit
	docker compose config --quiet
	docker build --target runtime -t ownsis-backend:validation backend
	docker build --target runtime -t ownsis-frontend:validation frontend
