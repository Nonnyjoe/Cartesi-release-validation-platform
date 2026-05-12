# ──────────────────────────────────────────────────────────────────────────────
# Cartesi RVP — Makefile
# ──────────────────────────────────────────────────────────────────────────────
.PHONY: help up down restart logs build build-base seed lint typecheck test \
        test-unit test-integration migrate shell-db shell-rabbit clean

COMPOSE  = docker compose
SERVICES = postgres rabbitmq redis orchestrator sandbox-manager test-runner \
           ai-agent github-watcher notifier dashboard

# Default target
help:
	@echo ""
	@echo "  Cartesi RVP — available targets"
	@echo "  ─────────────────────────────────────────────────────"
	@echo "  make up               Start all services (detached)"
	@echo "  make down             Stop and remove containers"
	@echo "  make restart          Down + up"
	@echo "  make logs [s=<svc>]   Tail logs  (e.g. make logs s=orchestrator)"
	@echo "  make build            Build all Docker images"
	@echo "  make build-base       Build sandbox-base image only"
	@echo "  make seed             Load test definitions into DB"
	@echo "  make migrate          Run Alembic migrations"
	@echo "  make lint             Ruff lint all Python services"
	@echo "  make typecheck        Mypy check all Python services"
	@echo "  make test             Run unit + integration tests"
	@echo "  make test-unit        Run unit tests only"
	@echo "  make test-integration Run integration tests only (needs Docker)"
	@echo "  make shell-db         psql into the RVP database"
	@echo "  make shell-rabbit     rabbitmqctl management shell"
	@echo "  make clean            Remove volumes + images"
	@echo ""

# ── Lifecycle ─────────────────────────────────────────────────────────────────
up:
	$(COMPOSE) up -d --remove-orphans

down:
	$(COMPOSE) down

restart: down up

logs:
ifdef s
	$(COMPOSE) logs -f $(s)
else
	$(COMPOSE) logs -f
endif

# ── Build ─────────────────────────────────────────────────────────────────────
build:
	$(COMPOSE) build

build-base:
	docker build -t cartesi-rvp/sandbox-base:latest ./sandbox-base

# ── Database ──────────────────────────────────────────────────────────────────
seed:
	@echo "Seeding test definitions…"
	$(COMPOSE) exec orchestrator python scripts/seed_tests.py

migrate:
	@echo "Running Alembic migrations…"
	$(COMPOSE) exec orchestrator alembic -c infra/migrations/alembic.ini upgrade head

shell-db:
	$(COMPOSE) exec postgres psql -U rvp_admin rvp

shell-rabbit:
	$(COMPOSE) exec rabbitmq rabbitmqctl status

# ── Quality ───────────────────────────────────────────────────────────────────
PYTHON_DIRS = services/orchestrator services/sandbox-manager services/test-runner \
              services/ai-agent services/github-watcher services/notifier shared

lint:
	ruff check $(PYTHON_DIRS)

typecheck:
	mypy $(PYTHON_DIRS) --ignore-missing-imports

test: test-unit

test-unit:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short -m integration

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	$(COMPOSE) down -v --rmi local
