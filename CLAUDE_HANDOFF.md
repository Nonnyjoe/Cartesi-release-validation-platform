# Cartesi RVP — Claude Code Handoff Brief

This document is a complete briefing for Claude Code to pick up debugging and fixing the Cartesi RVP platform. Read this entirely before touching any file.

---

## 1. What This Project Is

**Cartesi RVP** (Release Validation Platform) is an AI-powered automated testing system for the Cartesi rollups node. When a new GitHub release of `cartesi/rollups-node` is detected, it:

1. Spins up an ephemeral Docker sandbox (Anvil + Cartesi node)
2. Runs a battery of tests against it
3. Has an AI agent (Claude) analyse results and generate findings
4. Notifies via Discord
5. Optionally opens a GitHub PR with suggested fixes

The stack is Python microservices + React dashboard + RabbitMQ + PostgreSQL + Redis, all wired together via Docker Compose.

---

## 2. Project Structure

```
cartesi-rvp/
├── docker-compose.yml          # All services. Rebuilt images use per-service .env files.
├── Makefile                    # Full lifecycle commands incl. per-service targets
├── .env                        # Root env — used by docker compose for infra creds
├── .env.example
├── .gitignore
├── PLAN.md
├── README.md
├── logs.txt                    # Current error logs from docker compose logs
│
├── infra/
│   ├── postgres/
│   │   └── init.sql            # Schema init — creates all schemas/tables
│   ├── rabbitmq/
│   │   ├── definitions.json    # Exchanges, queues, bindings (NO users — see §4)
│   │   └── rabbitmq.conf       # Loads definitions.json on boot
│   └── migrations/
│       ├── alembic.ini
│       ├── env.py
│       └── versions/
│           └── 0001_initial_schema.py
│
├── sandbox-base/
│   ├── Dockerfile              # Base image: Ubuntu 22, Foundry, Cartesi CLI (npm), Python deps
│   ├── setup.sh
│   └── requirements.txt
│
├── shared/                     # Shared Python package — mounted read-only into every service
│   ├── constants.py            # Exchange/Queue/RoutingKey enums
│   └── message_schemas/
│       ├── ai.py
│       ├── notification.py
│       ├── sandbox.py
│       └── test.py
│
├── services/
│   ├── orchestrator/           # FastAPI — central API, WebSocket, DB writer
│   ├── sandbox-manager/        # Provisions/tears down Docker sandboxes
│   ├── test-runner/            # Executes test definitions against a sandbox
│   ├── ai-agent/               # Claude-powered analysis agent
│   ├── github-watcher/         # Polls GitHub Releases, triggers runs
│   ├── notifier/               # Sends Discord embeds
│   └── dashboard/              # React + TypeScript + Vite + Tailwind UI
│
└── tests/
    ├── definitions/            # YAML+MD test specs (5 tests)
    └── seed_definitions.py
```

### Per-service layout (Python services all follow this pattern):
```
services/<name>/
├── Dockerfile
├── requirements.txt
├── main.py                     # Entry point — asyncio.run(main())
├── .env                        # Real secrets (in .gitignore)
├── .env.example                # Template
├── consumers/                  # RabbitMQ consumers
├── publishers/                 # RabbitMQ publishers
└── <service-specific modules>
```

### Dockerfile pattern (all Python services):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=shared / /app/shared/   # shared/ injected via additional_contexts
COPY . .
CMD ["python", "main.py"]           # or uvicorn for orchestrator
```

The `additional_contexts: shared: ./shared` in docker-compose.yml makes `./shared` available as a named build context so `COPY --from=shared / /app/shared/` works.

---

## 3. Environment Variables

### Root `.env` (repo root — used only for infra credentials by docker compose)
```
POSTGRES_USER=rvp
POSTGRES_PASSWORD=changeme
POSTGRES_DB=rvp
RABBITMQ_USER=rvp
RABBITMQ_PASSWORD=changeme
MAX_SANDBOXES=5
SANDBOX_CPU_LIMIT=2
SANDBOX_MEMORY_LIMIT=4g
GITHUB_TOKEN=<real token>
GITHUB_REPO=cartesi/rollups-node
POLL_INTERVAL_SECONDS=300
ANTHROPIC_API_KEY=<real key>
DISCORD_WEBHOOK_URL=<real webhook>
```

### Per-service `.env` files (in `services/<name>/.env`)
Each service has its own `.env` and `.env.example`. The docker-compose `env_file` points to the per-service file. The compose `environment:` block always overrides `DATABASE_URL`, `RABBITMQ_URL`, `REDIS_URL` with Docker service-name URLs (e.g. `@rabbitmq:5672`). The per-service `.env` files use `localhost` URLs — these are for running services directly outside Docker.

Services that need secrets in their `.env`:
- `ai-agent/.env` — `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`
- `github-watcher/.env` — `GITHUB_TOKEN`, `GITHUB_REPO`
- `notifier/.env` — `DISCORD_WEBHOOK_URL`

---

## 4. Known Issues — Fixed in Code, Still Failing in Runtime

### 4.1 RabbitMQ Authentication — ALL SERVICES CRASH-LOOPING ⚠️

**Root cause:** `infra/rabbitmq/definitions.json` originally contained:
```json
"users": [{ "name": "rvp", "password_hash": "", ... }]
```
When RabbitMQ loads `definitions.json` at boot, it creates/overwrites the `rvp` user with an empty password hash, completely overriding whatever `RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` env vars set. Every service then gets `ACCESS_REFUSED — PLAIN login refused: user 'rvp' — invalid credentials`.

**Fix applied to code:** The `users` and `permissions` sections were removed from `definitions.json`. RabbitMQ now creates the `rvp` user purely from the `RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` Docker env vars.

**Why it's STILL failing:** The `rabbitmq-data` Docker volume persists the old broken user to disk. Even with the fixed `definitions.json`, the volume's Mnesia database still has the broken user. **The volume must be wiped.**

**Required action:**
```bash
docker compose down
docker volume rm cartesi-rvp_rabbitmq-data
docker compose up --build
```

If you want to keep Postgres data (skip `-v` on compose down):
```bash
docker compose down
docker volume rm cartesi-rvp_rabbitmq-data
docker compose up --build
```

**Affected services:** orchestrator, sandbox-manager, test-runner, ai-agent, github-watcher, notifier (all 6 Python services).

---

### 4.2 Orchestrator — Bad Relative Imports (Fixed in Code)

**Files:** `services/orchestrator/api/routes/tests.py`, `services/orchestrator/api/routes/sessions.py`

**Error:**
```
ImportError: attempted relative import beyond top-level package
```

**Root cause:** These two route files were written with `from ...database import get_db` and `from ...publishers.ai import AIPublisher` — relative imports that go beyond the top-level package. All other route files correctly use absolute imports (`from db import get_db`, `from publishers.ai import AIPublisher`).

**Fix applied:**
- `tests.py`: changed `from ...database import get_db` → `from db import get_db`
- `sessions.py`: changed `from ...database import get_db` → `from db import get_db` AND `from ...publishers.ai import AIPublisher` → `from publishers.ai import AIPublisher`

**Note:** Note there is no `database.py` in the orchestrator — the file is `db.py`. The `get_db` function lives in `db.py`.

**Status:** Fixed in source. Will take effect after `docker compose up --build`.

---

### 4.3 AI Agent — Missing `import asyncio` in `session_manager.py` (Fixed in Code)

**File:** `services/ai-agent/session_manager.py`

**Error:**
```
NameError: name 'asyncio' is not defined. Did you forget to import 'asyncio'?
```

**Root cause:** `session_manager.py` uses `asyncio.Queue` as a type annotation in a method signature at class body parse time, but `import asyncio` was missing from the imports.

**Fix applied:** Added `import asyncio` at the top of `session_manager.py`.

**Status:** Fixed in source. Will take effect after `docker compose up --build`.

---

### 4.4 Missing Packages in `requirements.txt` (Fixed in Code)

Three services were missing packages that their code actually imports:

| Service | Missing Package | Where It's Used |
|---|---|---|
| `github-watcher` | `sqlalchemy[asyncio]`, `asyncpg` | `poller.py` — tracks seen releases in `github.releases` DB table |
| `notifier` | `sqlalchemy[asyncio]`, `asyncpg` | `discord.py` — logs delivery attempts to `notifications.deliveries` |
| `test-runner` | `docker>=7.1` | `executors/log.py` — reads container stdout via Docker SDK |

**Fix applied:** Added the missing packages to each service's `requirements.txt`.

**Status:** Fixed in source. Will take effect after `docker compose up --build` (forces pip reinstall inside container).

---

### 4.5 Docker Client Initialised at Module Import Time (Fixed in Code)

**Files:** `services/sandbox-manager/provisioner.py`, `services/test-runner/executors/log.py`

**Error:**
```
docker.errors.DockerException: Error while fetching server API version:
  FileNotFoundError: [Errno 2] No such file or directory (Docker socket)
```

**Root cause:** Both files called `docker.from_env()` inside `__init__`, which runs at import time (since a module-level instance was created). In the sandbox this fails because the Docker socket isn't present.

**Fix applied:**
- `provisioner.py`: Changed `self._client = docker.from_env()` in `__init__` to `self._client = None`, added a `@property def client(self)` that lazy-initialises on first use.
- `executors/log.py`: Same pattern — `self._docker = None` in `__init__`, lazy `@property def docker(self)`.

**Status:** Fixed in source.

---

### 4.6 Dashboard — TypeScript Compilation Errors (Fixed in Code)

**Files:** `services/dashboard/src/`

Multiple TypeScript errors prevented `npm run build` from completing:

| File | Error | Fix |
|---|---|---|
| `vite-env.d.ts` | Missing entirely — `import.meta.env` had no types | Created file with `/// <reference types="vite/client" />` |
| `components/StatusBadge.tsx` | `AIMode` type not in `Status` union | Added `\| AIMode` to union, added `chaos` colour |
| `components/SandboxPool.tsx` | `import.meta.env` TS2339 | Safe optional chaining with fallback |
| `pages/RunDetail.tsx` | `loadRun` return type `"" \| Promise<void>` not assignable | Rewrote as `if (runId) { ... }` block |
| `pages/Sandboxes.tsx` | `historical` declared but never read (TS6133) | Removed unused variable |
| `pages/Session.tsx` | `wsSend` declared but never read; `loadSession` return type | Removed `send: wsSend` from destructure; rewrote as `if` block |

**Status:** All fixed in source. `tsc --noEmit` passes with zero errors.

---

### 4.7 Docker Compose `shared` Build Context Error (Fixed in Config)

**Error:**
```
failed to resolve source metadata for docker.io/library/shared:latest
```

**Root cause:** `COPY --from=shared / /app/shared/` was interpreted as a Docker Hub image reference because the Dockerfiles in `github-watcher` and `notifier` were missing the `additional_contexts` declaration in docker-compose.yml. Other Dockerfiles used `COPY ../../shared /app/shared` which is invalid when the build context doesn't include parent directories.

**Fix applied:** Added `additional_contexts: shared: ./shared` to ALL 6 Python service build blocks in `docker-compose.yml`. Standardised all Dockerfiles to use `COPY --from=shared / /app/shared/`.

---

### 4.8 `DATABASE_URL` Missing `+asyncpg` Driver (Fixed in Config)

**Symptom:** SQLAlchemy async operations fail with driver errors.

**Root cause:** The `docker-compose.yml` originally set `DATABASE_URL: postgresql://...` which defaults to the sync psycopg2 driver. All services use `asyncpg` for async operations.

**Fix applied:** All `DATABASE_URL` values in docker-compose.yml updated to `postgresql+asyncpg://...`.

---

### 4.9 `test-runner` Missing Docker Socket Mount (Fixed in Config)

**Symptom:** `LogContainsExecutor` can't connect to Docker even though Docker SDK is installed.

**Root cause:** The `test-runner` service in `docker-compose.yml` was missing the `/var/run/docker.sock` volume mount, even though it uses the Docker SDK to read container logs.

**Fix applied:** Added `- /var/run/docker.sock:/var/run/docker.sock` to `test-runner` volumes in docker-compose.yml.

---

## 5. Current State of Each Service

| Service | Code Status | Known Remaining Issue |
|---|---|---|
| **orchestrator** | ✅ Imports clean, tsc passes | Needs rebuild + RabbitMQ volume wipe |
| **sandbox-manager** | ✅ Imports clean | Needs RabbitMQ volume wipe |
| **test-runner** | ✅ Imports clean | Needs rebuild (docker dep added) + RabbitMQ volume wipe |
| **ai-agent** | ✅ Imports clean | Needs rebuild (asyncio fix) + RabbitMQ volume wipe |
| **github-watcher** | ✅ Imports clean | Needs rebuild (sqlalchemy dep added) + RabbitMQ volume wipe |
| **notifier** | ✅ Imports clean | Needs rebuild (sqlalchemy dep added) + RabbitMQ volume wipe |
| **dashboard** | ✅ `tsc --noEmit` passes | Rollup native binary mismatch (macOS node_modules on Linux sandbox — fine in Docker build) |

---

## 6. How to Verify a Service is Working

### Step 1 — Wipe the RabbitMQ volume and rebuild:
```bash
docker compose down
docker volume rm cartesi-rvp_rabbitmq-data
docker compose up --build -d
```

### Step 2 — Check individual service logs:
```bash
make logs-orchestrator
make logs-sandbox-manager
make logs-test-runner
make logs-ai-agent
make logs-github-watcher
make logs-notifier
```

### Step 3 — Expected healthy log lines:
- **orchestrator**: `INFO: Uvicorn running on http://0.0.0.0:8000`
- **sandbox-manager**: `Sandbox Manager ready — consuming sandbox.queue`
- **test-runner**: `Test Runner starting...` then waits
- **ai-agent**: `AI Agent ready — consuming ai.requests and releases.ai-agent`
- **github-watcher**: `Poller starting — repo=cartesi/rollups-node interval=300s`
- **notifier**: `Notifier ready — consuming notify.discord + notify.dashboard`

### Step 4 — Health check:
```bash
curl http://localhost:8000/healthz
```
Expected: `{"status": "ok", "db": "ok", "rabbitmq": "ok"}`

---

## 7. Architecture: Message Flow

```
github-watcher
    │  publishes to: rvp.releases (fanout)
    │                sandbox.queue (direct, priority 9)
    ▼
orchestrator ◄──── releases.orchestrator queue
sandbox-manager ◄── sandbox.queue
    │  publishes to: rvp.sandbox exchange → sandbox.events queue
    ▼
orchestrator ◄──── sandbox.events (updates sandbox status in DB)
    │  publishes to: rvp.tests exchange → tests.commands queue
    ▼
test-runner ◄────── tests.commands
    │  publishes to: rvp.tests exchange → tests.results queue
    ▼
orchestrator ◄──── tests.results (writes results, updates run)
    │  publishes to: rvp.notify (fanout) → notify.discord + notify.dashboard
    │                rvp.ai exchange → ai.requests queue
    ▼
notifier ◄─────── notify.discord
ai-agent ◄──────── ai.requests (also: releases.ai-agent for PR analysis)
    │  publishes to: rvp.notify (findings), rvp.ai (results)
    ▼
orchestrator ◄──── ai.results (updates session in DB)
dashboard ◄─────── WebSocket /ws/{channel_id} (orchestrator broadcasts events)
```

---

## 8. RabbitMQ Exchange/Queue Reference

| Exchange | Type | Queues Bound |
|---|---|---|
| `rvp.releases` | fanout | `releases.orchestrator`, `releases.ai-agent` |
| `rvp.sandbox` | direct | `sandbox.queue` (rk: sandbox.queue), `sandbox.events` (rk: sandbox.events) |
| `rvp.tests` | direct | `tests.commands` (rk: tests.commands), `tests.results` (rk: tests.results) |
| `rvp.ai` | direct | `ai.requests` (rk: ai.requests), `ai.results` (rk: ai.results) |
| `rvp.notify` | fanout | `notify.discord`, `notify.dashboard` |
| `rvp.dlx` | direct | `sandbox.queue.dlq`, `tests.results.dlq` |

---

## 9. PostgreSQL Schema Reference

Schemas and key tables (defined in `infra/postgres/init.sql`):

- `public.runs` — validation run records
- `public.run_events` — event log per run
- `public.sandboxes` — sandbox instance records
- `tests.definitions` — test specs (seeded from `tests/definitions/*.md`)
- `tests.results` — per-test pass/fail results
- `tests.reports` — aggregated run report
- `ai.sessions` — AI agent session records
- `ai.findings` — findings generated by the agent
- `ai.suggestions` — auto-generated fix suggestions
- `github.releases` — tracked GitHub releases
- `notifications.deliveries` — Discord notification log

---

## 10. Makefile Quick Reference

```bash
make up                    # Start everything
make down                  # Stop everything
make build                 # Rebuild all images
make up-orchestrator       # Start infra + orchestrator only
make up-ai-agent           # Start infra + ai-agent only
# (same pattern for all 7 services)
make logs-orchestrator     # Tail orchestrator logs
make restart-notifier      # Restart just the notifier
make build-github-watcher  # Rebuild just github-watcher image
make init-envs             # Copy .env.example → .env for all services
make shell-db              # psql into postgres
make clean                 # Remove all volumes + images
```

---

## 11. Priority Fix Order for Claude Code

1. **[CRITICAL]** Wipe `rabbitmq-data` volume, rebuild all images, verify all 6 services start and connect to RabbitMQ without auth errors.

2. **[VERIFY]** Confirm orchestrator responds at `http://localhost:8000/healthz` with `db: ok` and `rabbitmq: ok`.

3. **[VERIFY]** Confirm the dashboard builds and serves at `http://localhost:3000`.

4. **[INVESTIGATE]** If any service is still crash-looping after the RabbitMQ fix, check its logs individually with `docker compose logs -f <service-name>` and fix whatever the new top-level error is.

5. **[TEST]** Manually trigger a run by POST-ing to the orchestrator:
   ```bash
   curl -X POST http://localhost:8000/runs \
     -H "Content-Type: application/json" \
     -d '{"node_version": "1.5.0", "triggered_by": "manual"}'
   ```
   Watch `make logs-sandbox-manager` and `make logs-test-runner` to confirm the pipeline activates.

---

## 12. Files Modified During This Debugging Session

| File | What Changed |
|---|---|
| `infra/rabbitmq/definitions.json` | Removed `users` + `permissions` sections (empty password hash was overriding env-var user) |
| `docker-compose.yml` | Added `additional_contexts` to all 6 services; fixed `DATABASE_URL` to use `+asyncpg`; switched `env_file` to per-service files; added Docker socket mount to `test-runner` |
| `Makefile` | Full rewrite — added `up/down/restart/logs/build-<service>` targets for all 7 services + `init-envs` + `up-infra` |
| `services/orchestrator/api/routes/tests.py` | `from ...database import get_db` → `from db import get_db` |
| `services/orchestrator/api/routes/sessions.py` | `from ...database import get_db` → `from db import get_db`; `from ...publishers.ai import AIPublisher` → `from publishers.ai import AIPublisher` |
| `services/ai-agent/session_manager.py` | Added `import asyncio` |
| `services/sandbox-manager/provisioner.py` | Made Docker client lazy (`@property client`) |
| `services/test-runner/executors/log.py` | Made Docker client lazy (`@property docker`) |
| `services/test-runner/requirements.txt` | Added `docker>=7.1` |
| `services/github-watcher/requirements.txt` | Added `sqlalchemy[asyncio]>=2.0`, `asyncpg>=0.29` |
| `services/notifier/requirements.txt` | Added `sqlalchemy[asyncio]>=2.0`, `asyncpg>=0.29` |
| `services/dashboard/src/vite-env.d.ts` | Created — adds Vite's `ImportMeta.env` types |
| `services/dashboard/src/components/StatusBadge.tsx` | Added `AIMode` to `Status` union; added `chaos` colour |
| `services/dashboard/src/components/SandboxPool.tsx` | Safe `import.meta.env?.VITE_MAX_SANDBOXES` access |
| `services/dashboard/src/pages/RunDetail.tsx` | Fixed `loadRun`/`loadResults` return types |
| `services/dashboard/src/pages/Sandboxes.tsx` | Removed unused `historical` variable |
| `services/dashboard/src/pages/Session.tsx` | Removed unused `wsSend`; fixed `loadSession` return type |
| `services/<all 6>/.env.example` | Created per-service env templates |
| `services/<all 6>/.env` | Created from templates with real secrets filled in |
