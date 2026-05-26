# Cartesi RVP — Local Setup Guide

Step-by-step instructions for getting the full Cartesi Release Validation Platform running on your local machine, from a fresh clone to a live test run.

---

## Contents

- [Prerequisites](#prerequisites)
- [Step 1 — Clone the repository](#step-1--clone-the-repository)
- [Step 2 — Configure environment variables](#step-2--configure-environment-variables)
- [Step 3 — Build the sandbox base image](#step-3--build-the-sandbox-base-image)
- [Step 4 — Start the platform](#step-4--start-the-platform)
- [Step 5 — Run database migrations](#step-5--run-database-migrations)
- [Step 6 — Seed test definitions](#step-6--seed-test-definitions)
- [Step 7 — Verify all services are healthy](#step-7--verify-all-services-are-healthy)
- [Step 8 — Trigger a test run](#step-8--trigger-a-test-run)
- [Step 9 — View results](#step-9--view-results)
- [Optional — Build the Cartesi test app snapshot](#optional--build-the-cartesi-test-app-snapshot)
- [Service URLs quick-reference](#service-urls-quick-reference)
- [Common make targets](#common-make-targets)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

The following tools must be installed before you begin.

### Docker Desktop

Download and install from [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop).

Verify Docker Compose v2 is available (the `docker compose` subcommand, not the legacy `docker-compose` binary):

```bash
docker --version
docker compose version   # must show v2.x
```

> **macOS note:** Docker Desktop must be fully started (whale icon in the menu bar, not spinning) before running any `docker` command. If Docker Desktop fails to start, see [Troubleshooting — Docker Desktop won't start](#docker-desktop-wont-start).

### Git

```bash
git --version
```

### Node.js and npm _(optional — only needed to build the Cartesi test app snapshot)_

```bash
node --version   # 18 or later recommended
npm --version
```

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/Nonnyjoe/Cartesi-release-validation-platform
cd cartesi-rvp
```

All subsequent commands in this guide assume you are in the `cartesi-rvp/` root directory unless stated otherwise.

---

## Step 2 — Configure environment variables

The platform uses two layers of environment configuration:

- **Root `.env`** — sets shared infrastructure credentials (Postgres, RabbitMQ) and global feature flags. Used by `docker-compose.yml`.
- **Per-service `.env`** — each service in `services/<name>/` has its own `.env` with service-specific settings.

### 2a — Root `.env`

```bash
cp .env.example .env
```

Open `.env` and fill in the values marked with `xxxx`:

```dotenv
# ── PostgreSQL ────────────────────────────────────────────
POSTGRES_USER=rvp
POSTGRES_PASSWORD=changeme          # change for anything non-local
POSTGRES_DB=rvp

# ── RabbitMQ ──────────────────────────────────────────────
RABBITMQ_USER=rvp
RABBITMQ_PASSWORD=changeme

# ── Sandbox limits ────────────────────────────────────────
MAX_SANDBOXES=5                     # max concurrent sandbox containers
SANDBOX_CPU_LIMIT=2                 # CPUs per sandbox
SANDBOX_MEMORY_LIMIT=4g             # RAM per sandbox

# ── GitHub Watcher ────────────────────────────────────────
GITHUB_TOKEN=ghp_xxxx               # PAT with repo:read scope
GITHUB_REPO=cartesi/rollups-node
POLL_INTERVAL_SECONDS=300

# ── AI Agent ──────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-xxxx       # from console.anthropic.com

# ── Discord Notifier ──────────────────────────────────────
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxx/yyyy
```

**Minimum required secrets for a working local stack:**

| Variable              | Where to get it                                                                     |
| --------------------- | ----------------------------------------------------------------------------------- |
| `ANTHROPIC_API_KEY`   | [console.anthropic.com](https://console.anthropic.com) — create an API key          |
| `GITHUB_TOKEN`        | GitHub → Settings → Developer settings → Personal access tokens → `repo:read` scope |
| `DISCORD_WEBHOOK_URL` | Discord server → Settings → Integrations → Webhooks → New Webhook                   |

You can leave `DISCORD_WEBHOOK_URL` blank if you don't need Discord notifications — the notifier service will log a warning but won't crash.

### 2b — Per-service `.env` files

Run the init helper to copy all `.env.example` files at once:

```bash
make init-envs
```

This creates `services/<name>/.env` for every service that doesn't already have one. Output:

```
  Created services/orchestrator/.env
  Created services/sandbox-manager/.env
  Created services/test-runner/.env
  Created services/ai-agent/.env
  Created services/github-watcher/.env
  Created services/notifier/.env

  Done. Edit each services/<name>/.env to fill in real secrets.
```

Now open each file and fill in the secrets. The critical ones per service are:

**`services/orchestrator/.env`**

```dotenv
DATABASE_URL=postgresql+asyncpg://rvp:changeme@localhost:5432/rvp
RABBITMQ_URL=amqp://rvp:changeme@localhost:5672/
REDIS_URL=redis://localhost:6379
GITHUB_TOKEN=ghp_xxxx              # same token as root .env
CLI_GITHUB_REPO=cartesi/cli
CONTRACTS_GITHUB_REPO=cartesi/rollups-contracts
```

**`services/ai-agent/.env`**

```dotenv
DATABASE_URL=postgresql+asyncpg://rvp:changeme@localhost:5432/rvp
RABBITMQ_URL=amqp://rvp:changeme@localhost:5672/
REDIS_URL=redis://localhost:6379
MODEL_PROVIDER=anthropic           # or "ollama" for local model
ANTHROPIC_API_KEY=sk-ant-xxxx      # same key as root .env
AUTO_PR_ENABLED=false
GITHUB_TOKEN=ghp_xxxx
GITHUB_REPO=cartesi/rollups-node
```

**`services/github-watcher/.env`**

```dotenv
DATABASE_URL=postgresql+asyncpg://rvp:changeme@localhost:5432/rvp
RABBITMQ_URL=amqp://rvp:changeme@localhost:5672/
GITHUB_TOKEN=ghp_xxxx
GITHUB_REPO=cartesi/rollups-node
CLI_GITHUB_REPO=cartesi/cli
CONTRACTS_GITHUB_REPO=cartesi/rollups-contracts
POLL_INTERVAL_SECONDS=300
CLI_POLL_ENABLED=true
RATE_LIMIT_FLOOR=20
GITHUB_WEBHOOK_SECRET=your_node_webhook_secret
CLI_GITHUB_WEBHOOK_SECRET=your_cli_webhook_secret
```

**`services/notifier/.env`**

```dotenv
DATABASE_URL=postgresql+asyncpg://rvp:changeme@localhost:5432/rvp
RABBITMQ_URL=amqp://rvp:changeme@localhost:5672/
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxx/yyyy
```

`services/sandbox-manager/.env` and `services/test-runner/.env` only need the `DATABASE_URL` and `RABBITMQ_URL` values, which are already correct in the example files.

> **Password consistency:** The passwords in the per-service `DATABASE_URL` and `RABBITMQ_URL` must match the values set in the root `.env`. If you change `POSTGRES_PASSWORD` in the root `.env`, update every service `.env` accordingly.

---

## Step 3 — Build the sandbox base image

The sandbox manager spins up ephemeral Docker containers for each test run. Those containers are built from the `cartesi-rvp-sandbox:base` image, which must be built once before the first run.

```bash
make build-base
```

This builds `sandbox-base/Dockerfile` — an Ubuntu 22.04 image containing Foundry (Anvil, Cast, Forge) and the Python test dependencies. Takes 3–8 minutes on first run (Foundry downloads ~200 MB of binaries).

Confirm it was built successfully:

```bash
docker image ls cartesi-rvp-sandbox
```

Expected output:

```
REPOSITORY             TAG     IMAGE ID       CREATED         SIZE
cartesi-rvp-sandbox    base    <id>           X minutes ago   ~1.2GB
```

---

## Step 4 — Start the platform

Bring up the full stack (infrastructure + all application services) with a single command:

```bash
make up
# equivalent to: docker compose up -d --remove-orphans
```

On first run this builds all 7 service images before starting them. Subsequent `make up` calls reuse cached images and start in seconds.

Docker Compose starts services in dependency order:

1. **Infrastructure** (postgres, rabbitmq, redis) — waits for healthchecks to pass
2. **Application services** (orchestrator, sandbox-manager, test-runner, ai-agent, github-watcher, notifier, dashboard) — start after infrastructure is healthy

Expected output tail:

```
Container cartesi-rvp-postgres-1   Healthy
Container cartesi-rvp-rabbitmq-1   Healthy
Container cartesi-rvp-redis-1      Healthy
Container cartesi-rvp-sandbox-manager-1  Started
Container cartesi-rvp-test-runner-1      Started
Container cartesi-rvp-notifier-1         Started
```

---

## Step 5 — Run database migrations

The `init.sql` script creates all schemas and tables automatically on first Postgres boot. For subsequent schema changes (new columns, new tables added in later versions), run Alembic migrations:

```bash
make migrate
```

To apply every migration in order from a blank database (safe to re-run on an existing database — all migrations are idempotent):

```bash
make migrate-all
```

This runs migrations `0001` through `0008` in sequence:

| Migration | What it adds                                          |
| --------- | ----------------------------------------------------- |
| 0001      | Base schemas via `init.sql`                           |
| 0002      | `sdk_version`, `node_major_version` columns           |
| 0003      | `cli_version` column                                  |
| 0004      | `cli_catalog` and `sdk_catalog` tables                |
| 0005      | `contracts_catalog`, `devnet` and `contracts` columns |
| 0006      | BCNF normalization of version chain                   |
| 0007      | Application registry                                  |
| 0008      | Persistent run logs                                   |

---

## Step 6 — Seed test definitions

Load the built-in test definitions into the database. This is required before the first test run — without it the test-runner has no tests to execute.

```bash
make seed
```

This runs `scripts/seed_tests.py` inside the orchestrator container, which upserts the 5 built-in definitions:

| Definition             | What it tests                                           |
| ---------------------- | ------------------------------------------------------- |
| `advance-state-basic`  | Send an input, verify it appears in GraphQL, check logs |
| `inspect-state`        | Inspect REST endpoint + healthz + log assertion         |
| `graphql-inputs-query` | Send 3 inputs, verify `totalCount=3` via GraphQL        |
| `epoch-close`          | Send input, verify epoch transitions to CLOSED          |
| `voucher-execution`    | Send input, verify voucher count and GraphQL proof      |

Seeding is idempotent — safe to re-run at any time.

---

## Step 7 — Verify all services are healthy

Check that all 10 containers are running:

```bash
docker compose ps
```

Expected output — every service should show `Up` with no `Exit` or `Restarting` entries:

```
NAME                            STATUS              PORTS
cartesi-rvp-ai-agent-1          Up
cartesi-rvp-dashboard-1         Up                  0.0.0.0:3000->80/tcp
cartesi-rvp-github-watcher-1    Up (healthy)
cartesi-rvp-notifier-1          Up
cartesi-rvp-orchestrator-1      Up                  0.0.0.0:8000->8000/tcp
cartesi-rvp-postgres-1          Up (healthy)        0.0.0.0:5432->5432/tcp
cartesi-rvp-rabbitmq-1          Up (healthy)        0.0.0.0:5672->5672/tcp, 0.0.0.0:15672->15672/tcp
cartesi-rvp-redis-1             Up (healthy)        0.0.0.0:6379->6379/tcp
cartesi-rvp-sandbox-manager-1   Up
cartesi-rvp-test-runner-1       Up
```

Verify the orchestrator API is reachable:

```bash
curl http://localhost:8000/healthz
# Expected: {"status":"ok"}
```

Check the API docs are loading:

```bash
open http://localhost:8000/docs
```

Check the RabbitMQ management UI:

```bash
open http://localhost:15672
# Login: rvp / changeme  (or whatever you set in .env)
```

---

## Step 8 — Trigger a test run

Trigger a run against a specific Cartesi rollups-node release image:

```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "release_tag": "v1.5.0",
    "image_tag": "ghcr.io/cartesi/rollups-node:v1.5.0",
    "priority": 5,
    "triggered_by": "user"
  }'
```

**Field reference:**

| Field          | Description                                                            |
| -------------- | ---------------------------------------------------------------------- |
| `release_tag`  | Human-readable version label (e.g. `v1.5.0`)                           |
| `image_tag`    | Full Docker image reference the sandbox will pull                      |
| `priority`     | Queue priority 1–10. `9` = auto-triggered, `5` = user, `1` = scheduled |
| `triggered_by` | Free-text label for the run history (e.g. `user`, `github-watcher`)    |

The response contains the `run_id`:

```json
{
  "id": "3f2a1c4d-...",
  "status": "queued",
  "release_tag": "v1.5.0",
  ...
}
```

To watch the run progress in real time:

```bash
make logs s=orchestrator
# or tail all logs:
make logs
```

---

## Step 9 — View results

### Via the dashboard

Open the dashboard in your browser:

```
http://localhost:3000
```

The Runs page shows all runs with live status badges. Click a run to see:

- Per-test pass/fail breakdown
- Assertion-level detail (expected vs actual values)
- Live log stream while the run is in progress
- Final pass rate

### Via the API

List all runs:

```bash
curl http://localhost:8000/runs
```

Get the full report for a specific run:

```bash
curl http://localhost:8000/reports/<run_id>
```

The report includes:

```json
{
  "run_id": "3f2a1c4d-...",
  "release_tag": "v1.5.0",
  "status": "completed",
  "pass_rate": 0.8,
  "results": [
    {
      "test_name": "advance-state-basic",
      "status": "passed",
      "assertions": [
        { "type": "chain_tx", "passed": true },
        { "type": "graphql", "passed": true },
        { "type": "log_contains", "passed": true },
        { "type": "http_status", "passed": true }
      ]
    },
    ...
  ]
}
```

---

## Optional — Build the Cartesi test app snapshot

The v2.x sandbox tests use a pre-built Cartesi machine snapshot of a simple echo dApp. This is needed only if you intend to run sandbox tests that target the Cartesi v2.x node format.

**Prerequisites for this step:**

```bash
npm install -g @cartesi/cli@2.0.0-alpha.27
cartesi --version
```

Build and load the snapshot:

```bash
make build-test-app
```

This:

1. Runs `cartesi build` inside `test-app/` — builds the echo dApp into a RISC-V machine image
2. Creates the Docker volume `rvp-test-snapshot`
3. Copies the machine image into the volume

The sandbox-manager mounts this volume into each v2.x sandbox at provision time. The volume name can be overridden with the `TEST_SNAPSHOT_VOLUME` environment variable in `services/sandbox-manager/.env`.

---

## Service URLs quick-reference

| Service                | URL                        | Credentials                  |
| ---------------------- | -------------------------- | ---------------------------- |
| Dashboard              | http://localhost:3000      | —                            |
| Orchestrator API       | http://localhost:8000      | —                            |
| API Docs (Swagger)     | http://localhost:8000/docs | —                            |
| RabbitMQ Management UI | http://localhost:15672     | `rvp` / `changeme`           |
| PostgreSQL             | localhost:5432             | `rvp` / `changeme` db: `rvp` |
| Redis                  | localhost:6379             | —                            |

---

## Common make targets

```bash
# Lifecycle
make up                    # Start all services (detached)
make down                  # Stop and remove all containers
make restart               # down + up
make build                 # Rebuild all Docker images

# Logs
make logs                  # Tail all service logs
make logs s=orchestrator   # Tail a specific service

# Per-service control
make up-orchestrator       # Start infra + orchestrator only
make down-sandbox-manager  # Stop sandbox-manager (keeps infra running)
make restart-test-runner   # Restart test-runner

# Setup
make init-envs             # Copy .env.example -> .env for all services
make build-base            # Build cartesi-rvp-sandbox:base image
make build-test-app        # Build Cartesi echo dapp + load snapshot volume
make migrate               # Run Alembic migrations
make migrate-all           # Run ALL migrations in order (idempotent)
make seed                  # Seed test definitions into the DB

# Database / broker shells
make shell-db              # psql into the RVP database
make shell-rabbit          # rabbitmqctl status

# Quality
make lint                  # Ruff lint all Python services
make typecheck             # Mypy check all Python services
make test                  # Run unit tests
make test-integration      # Run integration tests (requires Docker)

# Cleanup
make clean                 # Remove volumes + local images (destructive)
```

---

## Troubleshooting

### Docker Desktop won't start

If Docker Desktop is stuck or hanging, force-kill all Docker processes and relaunch:

```bash
killall -9 "Docker Desktop" com.docker.backend com.docker.vmnetd \
  com.docker.dev-envs com.docker.extensions com.docker.sbom-cli 2>/dev/null || true
open -a "Docker Desktop"
```

Wait ~30 seconds, then confirm Docker is responsive:

```bash
docker info
```

If Docker Desktop still won't start after the force-kill, try a factory reset:
Docker Desktop → Settings (gear icon) → Troubleshoot → Reset to factory defaults.

> **Warning:** Factory reset removes all local images, containers, and volumes. Re-run Steps 3–6 after resetting.

### A service container keeps restarting

Check the logs for the failing service:

```bash
make logs s=<service-name>
# e.g. make logs s=orchestrator
```

Common causes:

| Symptom in logs                          | Cause                            | Fix                                                                                              |
| ---------------------------------------- | -------------------------------- | ------------------------------------------------------------------------------------------------ |
| `could not connect to server`            | Postgres not yet healthy         | Wait for `make logs s=postgres` to show `ready to accept connections`, then `make restart-<svc>` |
| `CONNECTION_REFUSED amqp://`             | RabbitMQ not yet healthy         | Same — wait for RabbitMQ healthcheck, then restart the service                                   |
| `ANTHROPIC_API_KEY not set`              | Missing secret in service `.env` | Add the key to `services/ai-agent/.env` and restart                                              |
| `permission denied /var/run/docker.sock` | Docker socket not accessible     | Ensure Docker Desktop is running and your user has socket access                                 |

### Port already in use

If a port is already bound on your host, the corresponding service will fail to start. Find and stop the conflicting process:

```bash
lsof -i :8000   # orchestrator
lsof -i :5432   # postgres
lsof -i :5672   # rabbitmq
lsof -i :6379   # redis
lsof -i :3000   # dashboard
```

Then either stop the conflicting process or change the host port in `docker-compose.yml` (e.g. `"8080:8000"` to move the orchestrator to port 8080).

### Database schema errors on first boot

If you see errors like `relation "orchestrator.runs" does not exist`, the init SQL did not run on Postgres startup. This can happen if the `postgres-data` volume was created from a previous broken state.

Wipe the volume and restart:

```bash
make down
docker volume rm cartesi-rvp_postgres-data
make up
make migrate-all
make seed
```

### RabbitMQ queues not pre-declared

The RabbitMQ topology (exchanges, queues, bindings) is loaded automatically from `infra/rabbitmq/definitions.json` on first boot. If services log errors about missing queues, the definitions file may not have loaded. Check the RabbitMQ management UI at http://localhost:15672 → Queues and verify that `sandbox.queue`, `tests.commands`, and `ai.requests` exist.

If they don't, force a reload:

```bash
make restart
```

On a completely fresh volume, the definitions always load on first boot.

### `make build-base` fails with "foundryup: command not found"

The sandbox base image builds Foundry inside the Docker build context, not on your host. If the build fails, it is likely a network issue during the `curl | bash` step. Retry:

```bash
docker build --no-cache -t cartesi-rvp-sandbox:base ./sandbox-base/
```

The `--no-cache` flag forces a fresh download of the Foundry installer.

### `make seed` fails with "connection refused"

The seed script connects to Postgres from **inside the orchestrator container**, so it uses the service name `postgres` as the hostname. If this fails, the orchestrator container is not running or Postgres is not healthy:

```bash
docker compose ps postgres          # must show (healthy)
docker compose ps orchestrator      # must show Up
make logs s=orchestrator            # look for startup errors
```

Once both are healthy, re-run `make seed`.
