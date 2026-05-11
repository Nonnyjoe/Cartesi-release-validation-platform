# Cartesi RVP — Release Validation Platform

> An AI-powered automated testing platform for the [Cartesi Rollups Node](https://github.com/cartesi/rollups-node).
> Replaces manual release validation with isolated sandbox environments, a structured test library, and a Claude-powered agent that can reason about, generate, and adapt tests in real time.

---

## The Problem

Every Cartesi rollups-node release is currently validated entirely by hand:
- Manually run the release Docker image
- Send transactions via CLI scripts
- Read logs manually
- Check outputs and vouchers on-chain

There are no formal test scripts — purely manual steps. This is slow, error-prone, and doesn't scale as releases ship faster.

---

## What Cartesi RVP Does

- **Automatically spins up isolated Docker sandbox environments** per test run (sub-5s, ephemeral, guaranteed teardown)
- **Executes a library of tests** against a specific node release image
- **Hot-reloads test definitions** from the database — add or modify tests with zero restarts
- **Uses Claude (Anthropic API)** as an AI agent that can reason about the node, generate payloads, call tools, and adapt tests mid-run *(Phase 3)*
- **Lets users interactively prompt the agent** to modify, reorder, or manually drive tests *(Phase 3)*
- **Compiles detailed reports** per run with per-assertion pass/fail detail
- **Notifies the team on Discord** on new releases and test completions *(Phase 5)*
- **Watches GitHub** for new releases and triggers test runs automatically *(Phase 5)*

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        CARTESI RVP                               │
│                                                                  │
│  ┌─────────────┐    REST/WS     ┌──────────────────────────┐    │
│  │  Dashboard  │◄──────────────►│   Orchestrator API       │    │
│  │  (React)    │                │   (FastAPI + WebSocket)  │    │
│  └─────────────┘                └──────────┬───────────────┘    │
│                                            │                     │
│                    ┌───────────────────────▼──────────────────┐  │
│                    │              RabbitMQ                    │  │
│                    │  rvp.releases    rvp.sandbox.queue       │  │
│                    │  rvp.sandbox.events   rvp.tests          │  │
│                    │  rvp.results    rvp.ai    rvp.notify     │  │
│                    └──┬──────┬────────┬──────┬──────┬────────┘  │
│                       │      │        │      │      │            │
│               ┌───────┘  ┌───┘    ┌───┘  ┌───┘  ┌───┘          │
│               ▼          ▼        ▼      ▼      ▼               │
│          ┌────────┐ ┌─────────┐ ┌──────┐ ┌────┐ ┌──────────┐   │
│          │ GitHub │ │ Sandbox │ │ Test │ │ AI │ │ Discord  │   │
│          │Watcher │ │ Manager │ │Runner│ │Agent│ │ Notifier │   │
│          └────────┘ └────┬────┘ └──────┘ └────┘ └──────────┘   │
│                          │                                       │
│          ┌───────────────▼─────────────────────────────────┐    │
│          │                 Sandbox Pool                    │    │
│          │  ┌──────────┐ ┌──────────┐ ┌──────────┐        │    │
│          │  │Sandbox 1 │ │Sandbox 2 │ │Sandbox 3 │  ...   │    │
│          │  │  Anvil   │ │  Anvil   │ │  Anvil   │        │    │
│          │  │  Node    │ │  Node    │ │  Node    │        │    │
│          │  └──────────┘ └──────────┘ └──────────┘        │    │
│          │  MAX_SANDBOXES = N (configurable, queue overflow)│    │
│          └─────────────────────────────────────────────────┘    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  PostgreSQL — per-service schemas, single instance        │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Orchestrator | Python / FastAPI | Async, WebSocket support, subprocess management |
| Sandbox Manager | Python + Docker SDK | Programmatic container lifecycle |
| Test Runner | Python | YAML+MD-driven test definitions, hot-reload from DB |
| AI Agent | Python + Anthropic Claude API | 200k context, tool use, streaming |
| Message Broker | RabbitMQ | Priority queues, dead letter queues, management UI |
| Database | PostgreSQL (single instance, per-service schemas) | Isolation without ops overhead |
| Frontend | React + TypeScript + TailwindCSS | Real-time WebSocket dashboard |
| Live Relay | Redis (pub/sub only) | Broadcasting logs to multiple browser tabs |
| Containerisation | Docker + Docker Compose | Single command to bring up the entire platform |
| Discord | Webhooks (v1) | Simple, no bot infrastructure needed |

---

## Project Structure

```
cartesi-rvp/
│
├── docker-compose.yml              # Full platform — one command
├── .env.example                    # Copy to .env and fill in secrets
├── README.md
│
├── services/
│   ├── orchestrator/               # FastAPI — central brain
│   │   ├── main.py                 # App + lifespan (consumers start here)
│   │   ├── db.py                   # Async SQLAlchemy engine + session
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── runs.py         # POST /runs, GET /runs, GET /runs/{id}
│   │   │   │   ├── sandboxes.py    # GET /sandboxes, GET /sandboxes/{id}
│   │   │   │   └── reports.py      # GET /reports/{run_id}
│   │   │   └── websocket.py        # WS /ws — Redis pub/sub → browser
│   │   ├── consumers/
│   │   │   ├── sandbox_events.py   # Sandbox READY → dispatch test commands
│   │   │   └── test_results.py     # Aggregate results → mark run complete
│   │   ├── publishers/
│   │   │   ├── sandbox_requests.py # Push to sandbox.queue (priority)
│   │   │   └── notifications.py    # Push to rvp.notify + Redis pub/sub
│   │   └── models/
│   │       ├── run.py              # ORM: orchestrator.runs + run_events
│   │       └── result.py           # ORM: tests.results (read-only)
│   │
│   ├── sandbox-manager/            # Manages sandbox pool lifecycle
│   │   ├── main.py
│   │   ├── pool.py                 # Slot tracker (MAX_SANDBOXES cap)
│   │   ├── provisioner.py          # Docker SDK — create network + containers
│   │   └── consumers/
│   │       └── sandbox_queue.py    # Priority queue consumer
│   │
│   ├── test-runner/                # YAML+MD-driven test executor
│   │   ├── main.py
│   │   ├── loader.py               # Hot-reload definitions from DB (30s interval)
│   │   ├── interpreter.py          # Parse YAML frontmatter + MD body
│   │   ├── executor.py             # Dispatch assertions, handle timeout
│   │   ├── executors/
│   │   │   ├── base.py             # Abstract base + SandboxContext
│   │   │   ├── graphql.py          # GraphQL query + JSON path assertion
│   │   │   ├── http.py             # HTTP status code assertion
│   │   │   ├── log.py              # Container log pattern assertion
│   │   │   ├── chain.py            # Send advance-state input
│   │   │   └── voucher.py          # Verify voucher via GraphQL
│   │   └── consumers/
│   │       └── test_commands.py    # Consume test commands, write results
│   │
│   ├── ai-agent/                   # Claude-powered agent (Phase 3)
│   │   ├── agent_loop.py
│   │   ├── session_manager.py
│   │   ├── tool_executor.py
│   │   ├── tools/                  # 10 tools: blockchain, node, graphql, etc.
│   │   └── context/                # Context assembler + Cartesi doc sources
│   │
│   ├── github-watcher/             # Polls GitHub for releases (Phase 5)
│   ├── notifier/                   # Discord webhooks (Phase 5)
│   └── dashboard/                  # React frontend (Phase 4)
│
├── sandbox-base/                   # Pre-built sandbox Docker image
│   ├── Dockerfile                  # Ubuntu 22 + Anvil + Cartesi CLI + Python
│   └── setup.sh                    # Environment health check
│
├── infra/
│   ├── rabbitmq/
│   │   ├── definitions.json        # Pre-declares all exchanges + queues on boot
│   │   └── rabbitmq.conf           # Enables definitions auto-load
│   └── postgres/
│       └── init.sql                # All schemas, roles, tables, indexes
│
├── shared/
│   ├── constants.py                # All queue/exchange names, priorities, statuses
│   └── message_schemas/            # Pydantic models for every MQ message
│       ├── sandbox.py              # SandboxRequest, SandboxEvent
│       ├── test.py                 # TestCommand, TestResult, AssertionResult
│       ├── ai.py                   # AISessionRequest, PRAnalysisRequest, etc.
│       └── notification.py         # NotificationMessage
│
└── tests/
    ├── definitions/                # Test definitions — YAML frontmatter + MD body
    │   ├── advance-state-basic.md
    │   ├── inspect-state.md
    │   ├── graphql-inputs-query.md
    │   ├── epoch-close.md
    │   └── voucher-execution.md
    └── seed_definitions.py         # Loads definitions into DB
```

---

## Getting Started

### Prerequisites

- Docker + Docker Compose v2
- An Anthropic API key (for Phase 3 AI agent)
- A GitHub personal access token with `repo:read` (for Phase 5 watcher)

### 1. Clone and configure

```bash
git clone https://github.com/your-org/cartesi-rvp
cd cartesi-rvp
cp .env.example .env
# Edit .env — fill in ANTHROPIC_API_KEY, GITHUB_TOKEN, DISCORD_WEBHOOK_URL
```

### 2. Bring up the platform

```bash
docker compose up --build
```

This starts in order: PostgreSQL → RabbitMQ → Redis → all application services.

Services available after boot:

| Service | URL |
|---|---|
| Orchestrator API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| RabbitMQ Management UI | http://localhost:15672 |
| Dashboard | http://localhost:3000 |

### 3. Seed the test definitions

On first run, load the built-in test definitions into the database:

```bash
docker compose exec test-runner python /app/../tests/seed_definitions.py
# or directly:
DATABASE_URL=postgresql://rvp:changeme@localhost:5432/rvp python tests/seed_definitions.py
```

### 4. Trigger a test run

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

### 5. Check the report

```bash
# List runs
curl http://localhost:8000/runs

# Get report for a run
curl http://localhost:8000/reports/{run_id}
```

---

## Database Design

Single PostgreSQL instance with per-service schema isolation. Each service has a dedicated role scoped only to its own schema. The only cross-schema access is the orchestrator's read-only grant on `tests.results` for compiling reports.

```
orchestrator.*   → runs, run_events
sandbox.*        → sandboxes
tests.*          → definitions, definition_versions, results
ai.*             → sessions, analyses, suggested_test_actions
github.*         → releases
notifications.*  → deliveries
```

---

## RabbitMQ Message Design

All messages share a standard envelope:

```json
{
  "event_id": "uuid-v4",
  "run_id":   "uuid-v4",
  "service":  "orchestrator",
  "ts":       "2026-05-01T12:00:00Z",
  "payload":  {}
}
```

Exchanges and queues pre-declared via `infra/rabbitmq/definitions.json`:

| Exchange | Type | Queues |
|---|---|---|
| `rvp.releases` | fanout | `releases.orchestrator`, `releases.ai-agent` |
| `rvp.sandbox` | direct | `sandbox.queue` (priority 0–10), `sandbox.events` |
| `rvp.tests` | direct | `tests.commands`, `tests.results` |
| `rvp.ai` | direct | `ai.requests`, `ai.results` |
| `rvp.notify` | fanout | `notify.discord`, `notify.dashboard` |
| `rvp.dlx` | direct | `sandbox.queue.dlq`, `tests.results.dlq` |

Sandbox requests use a **priority queue** (`x-max-priority: 10`):

| Priority | Source |
|---|---|
| 9 | Automated GitHub release trigger |
| 5 | User-triggered from dashboard |
| 1 | Scheduled / recurring |

---

## Test Definition Format

Tests are **data, not code** — stored in the database as YAML frontmatter + Markdown.
Add a new test by uploading an `.md` file. Zero restarts needed.

```yaml
---
id: advance-state-basic
name: Basic Advance State Input
version: 1
tags: [advance-state, core, smoke]
release_introduced: v1.4.0
component: dispatcher
priority: high
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node
  - graphql
assertions:
  - type: graphql
    query: |
      { inputs { edges { node { index payload } } } }
    expect:
      path: inputs.edges[0].node.payload
      value: "0xdeadbeef"
  - type: log_contains
    pattern: "input accepted"
  - type: http_status
    endpoint: /healthz
    expect: 200
---

## Description
Human-readable explanation of what this test covers.
```

### Assertion Types

| Type | What it does |
|---|---|
| `graphql` | Queries the node GraphQL API, asserts on a JSON path in the response |
| `http_status` | GET to an endpoint, checks HTTP status code |
| `log_contains` | Scans container logs for a regex pattern |
| `chain_tx` | Sends an advance-state input to the InputBox contract |
| `voucher` | Verifies vouchers appear via GraphQL with a valid proof |

Adding a new assertion type = one new Python file in `services/test-runner/executors/`.

---

## Sandbox Lifecycle

Each test run gets its own ephemeral Docker environment:

```
REQUESTED → QUEUED → PROVISIONING → READY → RUNNING → TEARDOWN → CLOSED
                                                         │
                                                    (on failure)
                                                     FAILED → DLQ
```

- Sub-5 second spin-up
- True process and network isolation (dedicated Docker network per sandbox)
- Resource caps via Docker (`SANDBOX_CPU_LIMIT`, `SANDBOX_MEMORY_LIMIT`)
- `MAX_SANDBOXES` cap enforced by the pool — overflow stays queued in RabbitMQ
- Guaranteed teardown on failure via `try/finally`

---

## Sandbox Base Image

`cartesi-rvp-sandbox:base` — pre-built with:
- Docker CLI (host socket mount for DinD)
- Anvil (Foundry) — local Ethereum chain
- Cartesi CLI
- Python test dependencies (httpx, gql, web3)

Build it once:

```bash
docker build -t cartesi-rvp-sandbox:base ./sandbox-base/
```

---

## Full Run Flow

```
POST /runs
  └─► orchestrator creates run (status=queued)
      └─► publishes SandboxRequest to sandbox.queue (with priority)
          └─► sandbox-manager consumes (respects MAX_SANDBOXES cap)
              └─► provisions Anvil + node containers
                  └─► publishes SandboxEvent(READY)
                      └─► orchestrator receives READY
                          └─► dispatches TestCommand for each active definition
                              └─► test-runner consumes each command
                                  └─► runs assertions against live sandbox
                                      └─► writes result to tests.results
                                          └─► publishes TestResult to tests.results queue
                                              └─► orchestrator aggregates
                                                  └─► computes pass_rate
                                                      └─► marks run completed/failed
                                                          └─► sandbox tears down
```

---

## Build Progress

### Phase 1 — Foundation ✅
- [x] Full repo scaffold — all folders and placeholder files
- [x] `docker-compose.yml` — all 10 services, networks, healthchecks
- [x] `infra/postgres/init.sql` — 6 schemas, 6 roles, 11 tables, indexes
- [x] `infra/rabbitmq/definitions.json` — 6 exchanges, 12 queues, all bindings
- [x] `shared/message_schemas/` — Pydantic models for all MQ messages
- [x] `shared/constants.py` — all queue/exchange names and status enums

### Phase 2 — Test Execution ✅
- [x] `sandbox-base/Dockerfile` — Ubuntu 22 + Anvil + Cartesi CLI
- [x] Orchestrator — FastAPI app, async SQLAlchemy, `/runs` + `/sandboxes` + `/reports` routes, WebSocket relay
- [x] Sandbox Manager — Docker SDK provisioner, pool tracker, priority queue consumer
- [x] Test Runner — YAML+MD parser, hot-reload loader, 5 assertion executors, RabbitMQ consumer/publisher
- [x] 5 seed test definitions (advance-state, inspect, GraphQL, epoch-close, voucher)
- [x] Full run flow: trigger → sandbox → tests → results → report → teardown

### Phase 3 — AI Agent 🔜
- [ ] Context assembler — inject Cartesi docs into Claude system prompt
- [ ] Agent loop — Claude tool-use agentic loop (observe → reason → act)
- [ ] 10 agent tools (blockchain, node, graphql, payload gen, time, reporting)
- [ ] 3 session modes: autonomous, collaborative, interactive
- [ ] Session streaming to dashboard WebSocket

### Phase 4 — Dashboard 🔜
- [ ] Runs list + run detail page (React + TypeScript + Tailwind)
- [ ] Live log stream via WebSocket
- [ ] Sandbox pool status view
- [ ] AI session UI — chat interface + live tool call stream
- [ ] Test definition editor (upload MD, preview, validate, save to DB)

### Phase 5 — GitHub + Discord 🔜
- [ ] GitHub Watcher — polling + webhook handler for new releases
- [ ] Auto-trigger run on new release (priority 9)
- [ ] Notifier — Discord embeds for run reports and release alerts

### Phase 6 — Future
- [ ] Adversarial / chaos mode (agent tries to break the node)
- [ ] Discord bot for interactive agent conversations
- [ ] Local model integration (Ollama) for cheap formatting tasks
- [ ] RAG pipeline for smaller-context local models
- [ ] Auto-PR: agent opens GitHub PR with new test definitions when gaps are found

---

## Environment Variables

Copy `.env.example` to `.env`:

```bash
# PostgreSQL
POSTGRES_USER=rvp
POSTGRES_PASSWORD=changeme
POSTGRES_DB=rvp

# RabbitMQ
RABBITMQ_USER=rvp
RABBITMQ_PASSWORD=changeme

# Sandbox limits
MAX_SANDBOXES=5
SANDBOX_CPU_LIMIT=2
SANDBOX_MEMORY_LIMIT=4g

# GitHub Watcher
GITHUB_TOKEN=ghp_xxxx
GITHUB_REPO=cartesi/rollups-node
POLL_INTERVAL_SECONDS=300

# AI Agent
ANTHROPIC_API_KEY=sk-ant-xxxx

# Discord Notifier
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxx/yyyy
```

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Sandbox isolation | Docker DinD per run | Fast spin-up, true isolation, easy teardown |
| Message broker | RabbitMQ | Priority queues, DLQ, management UI |
| DB architecture | Single Postgres, per-service schemas | Isolation without ops overhead |
| Test format | YAML frontmatter + MD body in DB | Tests as data, hot-reload, no restarts |
| AI provider | Claude (Anthropic) | Best reasoning, 200k context, tool use |
| RAG | Skipped in v1 | 200k context window makes it unnecessary |
| Context injection | Direct assembler into system prompt | Simple, zero extra infrastructure |
| Live streaming | Claude streaming API → WebSocket | Users see agent reasoning in real time |
| Redis role | Pub/sub only (dashboard broadcast) | Not inter-service messaging — that's RabbitMQ |

---

*Cartesi RVP — built for the Cartesi team, May 2026.*
