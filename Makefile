# ──────────────────────────────────────────────────────────────────────────────
# Cartesi RVP — Makefile
# ──────────────────────────────────────────────────────────────────────────────
.PHONY: help \
        up down restart logs build build-base \
        up-infra \
        up-orchestrator up-sandbox-manager up-test-runner \
        up-ai-agent up-github-watcher up-notifier up-dashboard \
        down-orchestrator down-sandbox-manager down-test-runner \
        down-ai-agent down-github-watcher down-notifier down-dashboard \
        restart-orchestrator restart-sandbox-manager restart-test-runner \
        restart-ai-agent restart-github-watcher restart-notifier restart-dashboard \
        logs-orchestrator logs-sandbox-manager logs-test-runner \
        logs-ai-agent logs-github-watcher logs-notifier logs-dashboard \
        build-orchestrator build-sandbox-manager build-test-runner \
        build-ai-agent build-github-watcher build-notifier build-dashboard \
        init-envs seed migrate migrate-sdk migrate-cli migrate-catalogs migrate-contracts migrate-normalize build-test-app lint typecheck test test-unit test-integration \
        shell-db shell-rabbit clean

COMPOSE  = docker compose
INFRA    = postgres rabbitmq redis

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Cartesi RVP — available make targets"
	@echo "  ─────────────────────────────────────────────────────────────────"
	@echo ""
	@echo "  FULL STACK"
	@echo "    make up               Start all services (detached)"
	@echo "    make down             Stop and remove all containers"
	@echo "    make restart          Down + up"
	@echo "    make logs [s=<svc>]   Tail all logs (or a specific service)"
	@echo "    make build            Build all Docker images"
	@echo ""
	@echo "  INFRASTRUCTURE ONLY"
	@echo "    make up-infra         Start postgres + rabbitmq + redis only"
	@echo ""
	@echo "  PER-SERVICE  (replace <svc> with service name)"
	@echo "    make up-<svc>         Start infra + one service"
	@echo "    make down-<svc>       Stop one service (keep infra running)"
	@echo "    make restart-<svc>    Restart one service"
	@echo "    make logs-<svc>       Tail logs for one service"
	@echo "    make build-<svc>      Rebuild image for one service"
	@echo ""
	@echo "  Services: orchestrator  sandbox-manager  test-runner"
	@echo "            ai-agent  github-watcher  notifier  dashboard"
	@echo ""
	@echo "  SETUP"
	@echo "    make init-envs        Copy .env.example -> .env for all services"
	@echo "    make build-base       Build the sandbox-base Docker image"
	@echo "    make build-test-app   Build Cartesi echo dapp + load snapshot volume"
	@echo "    make seed             Seed test definitions into the DB"
	@echo "    make migrate          Run Alembic migrations"
	@echo "    make migrate-sdk      Run migration 0002 (sdk_version) on live DB"
	@echo "    make migrate-cli      Run migration 0003 (cli_version) on live DB"
	@echo "    make migrate-catalogs  Run migration 0004 (cli_catalog + sdk_catalog) on live DB"
	@echo "    make migrate-contracts  Run migration 0005 (contracts_catalog + devnet/contracts cols)"
	@echo "    make migrate-normalize  Run migration 0006 (BCNF normalization of version chain)"
	@echo ""
	@echo "  QUALITY"
	@echo "    make lint             Ruff lint all Python services"
	@echo "    make typecheck        Mypy check all Python services"
	@echo "    make test             Run unit tests"
	@echo "    make test-unit        Run unit tests only"
	@echo "    make test-integration Run integration tests (needs Docker)"
	@echo ""
	@echo "  SHELLS"
	@echo "    make shell-db         psql into the RVP database"
	@echo "    make shell-rabbit     rabbitmqctl status"
	@echo ""
	@echo "  CLEANUP"
	@echo "    make clean            Remove volumes + local images"
	@echo ""

# ── Full stack lifecycle ───────────────────────────────────────────────────────
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

build:
	$(COMPOSE) build

# ── Infrastructure only ───────────────────────────────────────────────────────
up-infra:
	$(COMPOSE) up -d $(INFRA)

# ── Per-service: up (brings infra up first, then the one service) ─────────────
up-orchestrator:
	$(COMPOSE) up -d $(INFRA) orchestrator

up-sandbox-manager:
	$(COMPOSE) up -d $(INFRA) sandbox-manager

up-test-runner:
	$(COMPOSE) up -d $(INFRA) test-runner

up-ai-agent:
	$(COMPOSE) up -d $(INFRA) ai-agent

up-github-watcher:
	$(COMPOSE) up -d $(INFRA) github-watcher

up-notifier:
	$(COMPOSE) up -d $(INFRA) notifier

up-dashboard:
	$(COMPOSE) up -d $(INFRA) orchestrator dashboard

# ── Per-service: down (stops only that service, leaves infra running) ─────────
down-orchestrator:
	$(COMPOSE) stop orchestrator
	$(COMPOSE) rm -f orchestrator

down-sandbox-manager:
	$(COMPOSE) stop sandbox-manager
	$(COMPOSE) rm -f sandbox-manager

down-test-runner:
	$(COMPOSE) stop test-runner
	$(COMPOSE) rm -f test-runner

down-ai-agent:
	$(COMPOSE) stop ai-agent
	$(COMPOSE) rm -f ai-agent

down-github-watcher:
	$(COMPOSE) stop github-watcher
	$(COMPOSE) rm -f github-watcher

down-notifier:
	$(COMPOSE) stop notifier
	$(COMPOSE) rm -f notifier

down-dashboard:
	$(COMPOSE) stop dashboard
	$(COMPOSE) rm -f dashboard

# ── Per-service: restart ──────────────────────────────────────────────────────
restart-orchestrator:
	$(COMPOSE) restart orchestrator

restart-sandbox-manager:
	$(COMPOSE) restart sandbox-manager

restart-test-runner:
	$(COMPOSE) restart test-runner

restart-ai-agent:
	$(COMPOSE) restart ai-agent

restart-github-watcher:
	$(COMPOSE) restart github-watcher

restart-notifier:
	$(COMPOSE) restart notifier

restart-dashboard:
	$(COMPOSE) restart dashboard

# ── Per-service: logs ─────────────────────────────────────────────────────────
logs-orchestrator:
	$(COMPOSE) logs -f orchestrator

logs-sandbox-manager:
	$(COMPOSE) logs -f sandbox-manager

logs-test-runner:
	$(COMPOSE) logs -f test-runner

logs-ai-agent:
	$(COMPOSE) logs -f ai-agent

logs-github-watcher:
	$(COMPOSE) logs -f github-watcher

logs-notifier:
	$(COMPOSE) logs -f notifier

logs-dashboard:
	$(COMPOSE) logs -f dashboard

# ── Per-service: build ────────────────────────────────────────────────────────
build-orchestrator:
	$(COMPOSE) build orchestrator

build-sandbox-manager:
	$(COMPOSE) build sandbox-manager

build-test-runner:
	$(COMPOSE) build test-runner

build-ai-agent:
	$(COMPOSE) build ai-agent

build-github-watcher:
	$(COMPOSE) build github-watcher

build-notifier:
	$(COMPOSE) build notifier

build-dashboard:
	$(COMPOSE) build dashboard

build-base:
	docker build -t cartesi-rvp-sandbox:base ./sandbox-base

build-test-app:
	@echo "Building Cartesi test application (echo dapp)..."
	@command -v cartesi >/dev/null 2>&1 || { echo "  ERROR: cartesi CLI not found. Install with: npm install -g @cartesi/cli@2.0.0-alpha.27"; exit 1; }
	cd test-app && cartesi build
	@echo "Loading machine snapshot into Docker volume rvp-test-snapshot..."
	docker volume create rvp-test-snapshot
	docker run --rm \
		-v $(PWD)/test-app/.cartesi/image:/src:ro \
		-v rvp-test-snapshot:/dst \
		alpine sh -c "cp -r /src/. /dst/ && echo 'Snapshot loaded.'"
	@echo "Done — rvp-test-snapshot is ready for v2.x sandboxes."

# ── Setup ─────────────────────────────────────────────────────────────────────

# Copy .env.example -> .env for every service that doesn't already have one
init-envs:
	@for svc in orchestrator sandbox-manager test-runner ai-agent github-watcher notifier; do \
	  src=services/$$svc/.env.example; \
	  dst=services/$$svc/.env; \
	  if [ -f "$$src" ] && [ ! -f "$$dst" ]; then \
	    cp "$$src" "$$dst"; \
	    echo "  Created $$dst"; \
	  elif [ -f "$$dst" ]; then \
	    echo "  Skipped $$dst (already exists)"; \
	  else \
	    echo "  Warning: $$src not found"; \
	  fi; \
	done
	@echo ""
	@echo "  Done. Edit each services/<name>/.env to fill in real secrets."

seed:
	@echo "Seeding test definitions..."
	$(COMPOSE) exec orchestrator python scripts/seed_tests.py

migrate:
	@echo "Running Alembic migrations..."
	$(COMPOSE) exec orchestrator alembic -c infra/migrations/alembic.ini upgrade head

migrate-sdk:
	@echo "Running migration 0002 (sdk_version + node_major_version)..."
	$(COMPOSE) exec postgres psql -U rvp rvp \
	  -f /dev/stdin < infra/postgres/migrations/0002_add_sdk_version.sql
	@echo "Done."

migrate-cli:
	@echo "Running migration 0003 (cli_version)..."
	$(COMPOSE) exec postgres psql -U rvp rvp \
	  -f /dev/stdin < infra/postgres/migrations/0003_add_cli_version.sql
	@echo "Done."

migrate-catalogs:
	@echo "Running migration 0004 (cli_catalog + sdk_catalog tables)..."
	$(COMPOSE) exec postgres psql -U rvp rvp \
	  -f /dev/stdin < infra/postgres/migrations/0004_cli_sdk_catalogs.sql
	@echo "Done."

migrate-contracts:
	@echo "Running migration 0005 (contracts_catalog + devnet/contracts columns)..."
	$(COMPOSE) exec postgres psql -U rvp rvp \
	  -f /dev/stdin < infra/postgres/migrations/0005_contracts_devnet.sql
	@echo "Done."

migrate-normalize:
	@echo "Running migration 0006 (BCNF normalization of version chain)..."
	$(COMPOSE) exec postgres psql -U rvp rvp \
	  -f /dev/stdin < infra/postgres/migrations/0006_normalize_version_chain.sql
	@echo "Done."

# ── Shells ────────────────────────────────────────────────────────────────────
shell-db:
	$(COMPOSE) exec postgres psql -U rvp rvp

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
