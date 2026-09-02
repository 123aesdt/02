SHELL := /bin/sh

.PHONY: check lint test frontend-lint frontend-test frontend-build up down docs-check

check: docs-check lint test frontend-lint frontend-test frontend-build

lint:
	@python -m ruff check backend

test:
	@python -m pytest backend/tests -v

frontend-lint:
	@cd frontend && npm run lint

frontend-test:
	@cd frontend && npm test

frontend-build:
	@cd frontend && npm run build

docs-check:
	@! find . -path './.git' -prune -o -type f -name '*.md' -print | xargs grep -nE 'TODO|TBD' && exit 1 || exit 0
	@test -f docs/design.md
	@test -f docs/implementation-plan.md
	@test -f docs/superpowers/specs/2026-08-21-countyflow-design.md
	@test -f docs/superpowers/plans/2026-08-21-countyflow-implementation.md

up:
	@docker compose --env-file .docker.env up -d --build

down:
	@docker compose --env-file .docker.env down
