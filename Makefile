# ══════════════════════════════════════════════════════════════════
#  IAFacturas — Makefile de operaciones comunes
#  Uso: make <comando>
# ══════════════════════════════════════════════════════════════════

# ── Producción ────────────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart api celery

logs:
	docker compose logs -f api

migrate:
	docker compose exec api alembic upgrade head

shell:
	docker compose exec api bash

# ── Staging ───────────────────────────────────────────────────────
stg-up:
	docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build

stg-down:
	docker compose -f docker-compose.staging.yml --env-file .env.staging down

stg-restart:
	docker compose -f docker-compose.staging.yml --env-file .env.staging restart api celery

stg-logs:
	docker compose -f docker-compose.staging.yml --env-file .env.staging logs -f api

stg-migrate:
	docker compose -f docker-compose.staging.yml --env-file .env.staging exec api alembic upgrade head

stg-shell:
	docker compose -f docker-compose.staging.yml --env-file .env.staging exec api bash

# Despliega staging: pull rama develop + rebuild + migrate
stg-deploy:
	git fetch origin
	git checkout develop
	git pull origin develop
	docker compose -f docker-compose.staging.yml --env-file .env.staging up -d --build
	docker compose -f docker-compose.staging.yml --env-file .env.staging exec api alembic upgrade head

# Pasa develop a main y despliega producción
prod-deploy:
	git checkout main
	git merge develop
	git push origin main
	docker compose up -d --build
	docker compose exec api alembic upgrade head

.PHONY: up down restart logs migrate shell \
        stg-up stg-down stg-restart stg-logs stg-migrate stg-shell \
        stg-deploy prod-deploy
