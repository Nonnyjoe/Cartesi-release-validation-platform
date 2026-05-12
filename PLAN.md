# Cartesi RVP — Build Plan

> Living document tracking the full build of the Cartesi Release Validation Platform.
> Updated as each task is completed. Check items off as you go.

**Legend:**
- ✅ Complete
- 🔲 Not started
- 🏗️ In progress

---

## Phase 1 — Foundation ✅

> Goal: Everything needed to bring the platform up with `docker compose up --build`, with all infrastructure pre-configured and all inter-service contracts defined.

### Repo & Infrastructure
- ✅ Full repo folder structure scaffolded — all 74 files across all 7 services
- ✅ `.gitignore` — Python, Node, `.env`, editor files, build artifacts
- ✅ `docker-compose.yml` — all 10 services, `rvp-internal`/`rvp-public` networks, healthchecks with `depends_on` conditions, Docker socket mount for sandbox-manager, all port mappings
- ✅ `.env.example` — all required environment variables documented

### Database
- ✅ `infra/postgres/init.sql`
  - ✅ 6 schemas: `orchestrator`, `sandbox`, `tests`, `ai`, `github`, `notifications`
  - ✅ 6 scoped DB roles with `ALTER DEFAULT PRIVILEGES` per schema
  - ✅ 11 tables: `runs`, `run_events`, `sandboxes`, `definitions`, `definition_versions`, `results`, `sessions`, `analyses`, `suggested_test_actions`, `releases`, `deliveries`
  - ✅ Indexes on all frequently queried columns
  - ✅ Cross-schema read grant: orchestrator → `tests.results`
  - ✅ Shared enum types for all status fields

### Message Broker
- ✅ `infra/rabbitmq/definitions.json` — pre-declares all topology on boot
  - ✅ 6 exchanges: `rvp.releases` (fanout), `rvp.sandbox` (direct), `rvp.tests` (direct), `rvp.ai` (direct), `rvp.notify` (fanout), `rvp.dlx` (dead-letter)
  - ✅ 12 queues including `sandbox.queue` (`x-max-priority: 10`, TTL 30min), both DLQs
  - ✅ All bindings wired correctly
- ✅ `infra/rabbitmq/rabbitmq.conf` — auto-loads definitions on first boot

### Shared Library
- ✅ `shared/constants.py` — `Exchange`, `Queue`, `RoutingKey`, `Priority`, `Service`, `SandboxStatus`, `RunStatus`, `TestStatus`, `AIMode`, `AISessionStatus`, `AgentLimits` as typed classes
- ✅ `shared/message_schemas/sandbox.py` — `SandboxRequest`, `SandboxEvent`, `SandboxEventType`
- ✅ `shared/message_schemas/test.py` — `TestCommand`, `TestResult`, `AssertionResult`
- ✅ `shared/message_schemas/ai.py` — `AISessionRequest`, `AISessionEvent`, `PRAnalysisRequest`, `PRAnalysisResult`
- ✅ `shared/message_schemas/notification.py` — `NotificationMessage`, `NotificationEventType`
- ✅ All 9 Pydantic models import and instantiate cleanly

---

## Phase 2 — Test Execution ✅

> Goal: Full end-to-end run flow — trigger a run via API, spin up a sandbox, execute tests, write results, tear down.

### Sandbox Base Image
- ✅ `sandbox-base/Dockerfile` — Ubuntu 22.04 + Foundry (Anvil, Cast) + Cartesi CLI + Docker CLI + Python deps
- ✅ `sandbox-base/setup.sh` — environment health check script
- ✅ `sandbox-base/requirements.txt` — `httpx`, `gql`, `web3`, `pydantic`, `aiofiles`

### Orchestrator (FastAPI)
- ✅ `services/orchestrator/main.py` — FastAPI app with lifespan-managed consumers, CORS middleware
- ✅ `services/orchestrator/db.py` — async SQLAlchemy engine, `AsyncSessionLocal`, `get_db` dependency
- ✅ `services/orchestrator/models/run.py` — ORM: `orchestrator.runs`, `orchestrator.run_events`
- ✅ `services/orchestrator/models/result.py` — read-only ORM: `tests.results`
- ✅ `services/orchestrator/api/routes/runs.py` — `POST /runs`, `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/cancel`
- ✅ `services/orchestrator/api/routes/sandboxes.py` — `GET /sandboxes`, `GET /sandboxes/{id}`
- ✅ `services/orchestrator/api/routes/reports.py` — `GET /reports/{run_id}` with cross-schema join
- ✅ `services/orchestrator/api/websocket.py` — `WS /ws`, Redis pub/sub → browser fan-out
- ✅ `services/orchestrator/consumers/sandbox_events.py` — READY event → dispatches `TestCommand` per active definition
- ✅ `services/orchestrator/consumers/test_results.py` — aggregates results, computes `pass_rate`, marks run complete
- ✅ `services/orchestrator/publishers/sandbox_requests.py` — publishes to `sandbox.queue` with priority
- ✅ `services/orchestrator/publishers/notifications.py` — publishes to `rvp.notify` + Redis pub/sub

### Sandbox Manager
- ✅ `services/sandbox-manager/pool.py` — asyncio slot tracker, `acquire()` / `release()` / `wait_for_slot()`
- ✅ `services/sandbox-manager/provisioner.py` — Docker SDK: creates network, starts Anvil + node containers, resource limits
- ✅ `services/sandbox-manager/consumers/sandbox_queue.py` — priority queue consumer, blocks on pool slot before ACKing, teardown in `finally`
- ✅ `services/sandbox-manager/main.py` — entry point

### Test Runner
- ✅ `services/test-runner/loader.py` — polls DB every 30s, in-memory definition cache, zero restarts to add tests
- ✅ `services/test-runner/interpreter.py` — YAML frontmatter + Markdown body parser with validation
- ✅ `services/test-runner/executor.py` — assertion dispatcher with `asyncio.timeout`, overall status aggregation
- ✅ `services/test-runner/executors/base.py` — `AssertionExecutor` ABC, `AssertionResult`, `SandboxContext`
- ✅ `services/test-runner/executors/graphql.py` — GraphQL query + dotted JSON path assertion
- ✅ `services/test-runner/executors/http.py` — HTTP GET status code assertion
- ✅ `services/test-runner/executors/log.py` — Docker container log regex pattern assertion
- ✅ `services/test-runner/executors/chain.py` — advance-state input via HTTP bridge
- ✅ `services/test-runner/executors/voucher.py` — voucher count + existence via GraphQL
- ✅ `services/test-runner/consumers/test_commands.py` — consumes commands, writes pending result, runs test, publishes `TestResult`
- ✅ `services/test-runner/main.py` — entry point (hot-reload + consumer run concurrently)

### Seed Test Definitions
- ✅ `tests/definitions/advance-state-basic.md` — 4 assertions: `chain_tx` → `graphql` → `log_contains` → `http_status`
- ✅ `tests/definitions/inspect-state.md` — 3 assertions: inspect REST endpoint + healthz + log
- ✅ `tests/definitions/graphql-inputs-query.md` — 5 assertions: 3× `chain_tx` → `graphql` totalCount=3 → `http_status`
- ✅ `tests/definitions/epoch-close.md` — 4 assertions: input → epoch CLOSED in GraphQL → 2× `log_contains`
- ✅ `tests/definitions/voucher-execution.md` — 4 assertions: input → `voucher` count → `graphql` proof → `log_contains`
- ✅ `tests/seed_definitions.py` — asyncpg upsert script, idempotent, reads from `tests/definitions/`

---

## Phase 3 — AI Agent ✅

> Goal: A Claude-powered agentic engine that can autonomously validate the node, work collaboratively with an engineer, or serve as an interactive AI terminal.

### Service Scaffolding
- ✅ `services/ai-agent/Dockerfile` — Python 3.12-slim + Docker CLI + all deps
- ✅ `services/ai-agent/requirements.txt` — `anthropic`, `aio-pika`, `asyncpg`, `sqlalchemy`, `redis`, `httpx`, `docker`, `pyyaml`
- ✅ `services/ai-agent/main.py` — entry point, starts session + PR analysis consumers concurrently

### Context Assembler
- ✅ `services/ai-agent/context/assembler.py` — builds full system prompt from sources + release context
- ✅ `services/ai-agent/context/sources/architecture.md` — Cartesi node architecture reference (components, ports, contracts, epoch lifecycle)
- ✅ `services/ai-agent/context/sources/graphql_schema.graphql` — full node GraphQL schema
- ✅ `services/ai-agent/context/sources/inspect_api.yaml` — OpenAPI spec for inspect-state REST endpoint
- ✅ `services/ai-agent/context/sources/component_map.json` — container name patterns, log keywords, failure indicators per component
- ✅ `services/ai-agent/context/templates/autonomous.py` — goal-driven solo agent prompt
- ✅ `services/ai-agent/context/templates/collaborative.py` — human-in-the-loop, propose → approve → execute
- ✅ `services/ai-agent/context/templates/interactive.py` — AI-assisted terminal persona

### Agent Tools (all 10 implemented)
- ✅ `services/ai-agent/tools/__init__.py` — `AGENT_TOOLS` list in Claude API `input_schema` format
- ✅ `services/ai-agent/tools/blockchain.py` — `send_advance_input`, `run_cast_command`, `verify_voucher`
- ✅ `services/ai-agent/tools/node.py` — `read_logs` (Docker SDK), `get_node_state`
- ✅ `services/ai-agent/tools/graphql.py` — `query_graphql`, `call_inspect`
- ✅ `services/ai-agent/tools/payload_gen.py` — `generate_payload` (6 modes: random, zero, boundary, malformed, structured, empty)
- ✅ `services/ai-agent/tools/time.py` — `advance_time` (batched `anvil_mine`, 7200 blocks = 1 epoch)
- ✅ `services/ai-agent/tools/reporting.py` — `report_finding` (in-memory accumulator, persisted at session close)

### Agent Core
- ✅ `services/ai-agent/tool_executor.py` — dispatches Claude `tool_use` blocks to Python functions, injects sandbox context
- ✅ `services/ai-agent/agent_loop.py` — Claude streaming API loop, hard limits (50/200 tool calls, 600/3600s), context compression at 80% window
- ✅ `services/ai-agent/session_manager.py` — `run_autonomous()`, `run_collaborative()`, `run_interactive()`, persists to `ai.sessions`

### Consumers & Publishers
- ✅ `services/ai-agent/consumers/session_requests.py` — consumes `ai.requests`, dispatches to correct session mode, manages `asyncio.Queue` per live session
- ✅ `services/ai-agent/consumers/pr_analysis.py` — consumes `releases.ai-agent`, analyses PRs/changelog with Claude, saves gaps + suggestions to DB
- ✅ `services/ai-agent/publishers/session_events.py` — dual publish: RabbitMQ `ai.results` (durable) + Redis pub/sub (live dashboard)

---

## Phase 4 — Dashboard ✅

> Goal: A React + TypeScript + TailwindCSS single-page application that gives the team full visibility into runs, sandboxes, test results, and AI sessions in real time.

### 4.1 — Project Setup
- ✅ `services/dashboard/package.json` — full deps: React 18, TypeScript, Vite, TailwindCSS, React Router, Recharts, `clsx`
- ✅ `services/dashboard/vite.config.ts` — Vite config, proxy `/api` → orchestrator:8000, `/ws` → ws:8000
- ✅ `services/dashboard/tsconfig.json` — strict TypeScript config
- ✅ `services/dashboard/tailwind.config.js` — dark mode, custom palette (`rvp-*` colours)
- ✅ `services/dashboard/postcss.config.js`
- ✅ `services/dashboard/index.html` — Vite entry HTML
- ✅ `services/dashboard/src/main.tsx` — React root, `<App />` mount
- ✅ `services/dashboard/src/App.tsx` — React Router layout: sidebar nav + `<Outlet>`
- ✅ `services/dashboard/src/types.ts` — shared TypeScript interfaces matching DB/API shapes (`Run`, `Sandbox`, `TestResult`, `AISession`, `Finding`)
- ✅ `services/dashboard/src/api.ts` — typed fetch wrappers for all orchestrator REST endpoints
- ✅ `services/dashboard/Dockerfile` — multi-stage: Node build → Nginx serve, `nginx.conf` with SPA fallback

### 4.2 — WebSocket Hook
- ✅ `services/dashboard/src/hooks/useWebSocket.ts`
  - Connects to `WS /ws` on mount, auto-reconnects with exponential backoff
  - Parses incoming JSON events and dispatches to typed callbacks
  - Exposes `{ connected, lastEvent, send }` to consumers

### 4.3 — Runs Pages
- ✅ `services/dashboard/src/pages/Runs.tsx`
  - Table of all runs: release tag, status badge (colour-coded), priority, triggered by, queued time, pass rate progress bar
  - Auto-refreshes every 10s and on WebSocket `run.*` events
  - Filter by status (queued / running / completed / failed)
  - "Trigger Run" button → modal with `release_tag`, `image_tag`, priority selector → `POST /runs`
- ✅ `services/dashboard/src/pages/RunDetail.tsx`
  - Run header: release tag, status, triggered by, duration, pass rate (large dial)
  - Per-test result table: test name, status icon, duration, assertion breakdown on expand
  - Live log pane (updates via WebSocket while status = running)
  - "Cancel Run" button (active when queued or running)
  - Link to AI session if one was run for this run

### 4.4 — Sandboxes Page
- ✅ `services/dashboard/src/pages/Sandboxes.tsx`
  - Pool capacity bar: active / MAX_SANDBOXES
  - Cards for each active sandbox: ID, run link, status, ports, container IDs, uptime
  - Historical list of closed/failed sandboxes with failure reasons
  - Auto-refreshes on WebSocket `sandbox.*` events

### 4.5 — AI Session Pages
- ✅ `services/dashboard/src/pages/Session.tsx`
  - Split-pane layout: left = chat / right = tool call stream
  - Mode selector: Autonomous | Collaborative | Interactive
  - Autonomous: shows goal input, "Start Session" button, streams agent thinking live
  - Collaborative: chat input enabled, agent proposes → user types approval/redirect
  - Interactive: full chat input, agent executes commands and explains
  - Tool call cards: name, input, output, duration — rendered as they arrive
  - Findings panel: collapsible list of `report_finding` calls with severity badges
  - Session summary card when `session_completed` event arrives
- ✅ `services/dashboard/src/pages/AISuggestions.tsx`
  - Table of `ai.suggested_test_actions` with status (pending / approved / rejected)
  - Expand row to preview the full YAML+MD definition
  - "Approve" → writes definition to DB, makes it active (calls new `POST /tests/definitions` route)
  - "Reject" → marks as rejected with optional reason

### 4.6 — Shared Components
- ✅ `services/dashboard/src/components/LiveLogs.tsx`
  - Virtualised log viewer (react-virtual or similar) for large log streams
  - Auto-scrolls to bottom, "pause scroll" toggle
  - Syntax highlighting for log levels (ERROR=red, WARN=yellow, INFO=gray)
  - Filter input (regex)
- ✅ `services/dashboard/src/components/TestResultCard.tsx`
  - Expandable card: test name, status icon, duration
  - Assertion breakdown table inside: type, passed/failed, expected vs actual, detail
- ✅ `services/dashboard/src/components/QueueStatus.tsx`
  - Mini widget showing RabbitMQ queue depths: sandbox.queue, tests.commands, ai.requests
  - Pulls from new `GET /queues` orchestrator endpoint
- ✅ `services/dashboard/src/components/SandboxPool.tsx`
  - Visual capacity bar + mini cards for each active sandbox
  - Used both standalone on /sandboxes and embedded in the run detail page
- ✅ `services/dashboard/src/components/AgentStream.tsx`
  - Renders streamed AI agent events in real time
  - Text deltas appear as they stream (typewriter effect)
  - Tool call events render as collapsible cards with JSON input/output
  - Finding events render as highlighted alert cards

### 4.7 — Supporting Orchestrator Routes (needed for dashboard)
- ✅ `services/orchestrator/api/routes/tests.py`
  - `GET /tests/definitions` — list all active definitions
  - `POST /tests/definitions` — upsert a definition (used by AI suggestions approval)
  - `GET /tests/definitions/{slug}` — single definition detail
- ✅ `services/orchestrator/api/routes/sessions.py`
  - `POST /sessions` — create a new AI session (autonomous or collaborative)
  - `GET /sessions/{id}` — session detail + findings
  - `POST /sessions/{id}/message` — inject a user message into a live session
  - `GET /sessions/{id}/suggestions` — list suggested test actions from this session
- ✅ `services/orchestrator/api/routes/queues.py`
  - `GET /queues` — returns RabbitMQ queue depths via management API

---

## Phase 5 — GitHub Watcher + Discord Notifier ✅

> Goal: Automatically detect new Cartesi rollups-node releases and trigger test runs, then notify the team on Discord with rich embedded reports.

### 5.1 — GitHub Watcher
- ✅ `services/github-watcher/requirements.txt` — `aio-pika`, `httpx`, `pydantic`, `pydantic-settings`
- ✅ `services/github-watcher/Dockerfile`
- ✅ `services/github-watcher/main.py` — starts both poller and webhook handler
- ✅ `services/github-watcher/poller.py`
  - Polls `GET /repos/{GITHUB_REPO}/releases/latest` every `POLL_INTERVAL_SECONDS`
  - Compares against `github.releases` table to detect new tags
  - On new release: fetches PR list, extracts summaries, writes to `github.releases`
  - Publishes to `rvp.releases` (fanout) with `run_triggered=false`
  - Triggers a run by publishing a `SandboxRequest` with `priority=9`
  - Updates `github.releases.run_triggered = true` and `run_id`
- ✅ `services/github-watcher/webhook_handler.py`
  - FastAPI app on port `8001` (internal only)
  - `POST /webhook` — handles `release` GitHub webhook events
  - Validates `X-Hub-Signature-256` HMAC signature
  - Same publish flow as the poller on valid `published` action
  - Faster trigger path than polling (immediate vs every 5min)

### 5.2 — Notifier
- ✅ `services/notifier/requirements.txt` — `aio-pika`, `httpx`, `pydantic`
- ✅ `services/notifier/Dockerfile`
- ✅ `services/notifier/main.py` — consumes `notify.discord` and `notify.dashboard`
- ✅ `services/notifier/formatters.py`
  - `format_release_detected(release)` → Discord embed: release tag, changelog snippet, auto-run triggered
  - `format_run_queued(run)` → Discord embed: release, priority, triggered by
  - `format_run_completed(run, report)` → Discord embed: pass rate dial (emoji bars), per-test breakdown, duration, link to dashboard
  - `format_run_failed(run)` → Discord embed: failure reason, sandbox log excerpt, link to report
  - `format_ai_finding(finding)` → Discord embed: severity badge, component, description, evidence snippet
  - All formatters return Discord embed JSON (`embeds` array) with colour-coded by severity/status
- ✅ `services/notifier/discord.py`
  - `send_embed(webhook_url, embed)` — POST to Discord webhook with retry (3×, exponential backoff)
  - Writes delivery record to `notifications.deliveries`
  - Handles Discord rate limiting (`retry_after` from 429 response)

---

## Phase 6 — Future Enhancements ✅

> These are planned but not committed to a timeline. Each is a self-contained feature that can be built independently.

### 6.1 — Adversarial / Chaos Mode
- ✅ New agent mode: `chaos` — agent intentionally tries to break the node
  - Sends malformed inputs (malformed payloads, extreme sizes, invalid hex, empty)
  - Rapid-fire inputs without waiting for confirmation
  - Concurrent inputs from multiple goroutines
  - Mid-epoch restart of the node container (via Docker SDK)
  - Network partition simulation (pause Anvil container, resume, check recovery)
- ✅ New `generate_payload` modes: `max_size`, `all_zeros_large`, `repeated_pattern`
- ✅ New tool: `restart_component(component)` — stops and restarts a named container
- ✅ New tool: `pause_network(duration_seconds)` — disconnects Anvil from node network temporarily
- ✅ New chaos prompt template: `context/templates/chaos.py`

### 6.2 — Discord Bot (Interactive Agent via Discord)
- 🔲 Replace Discord webhook notifier with a full Discord bot using `discord.py`
- 🔲 `/validate <release_tag>` slash command — triggers a run from Discord
- 🔲 `/status` — shows current queue + active sandbox count
- 🔲 `/ask <question>` — routes question to a live interactive agent session
- 🔲 Agent streams responses back to the Discord thread in real time
- 🔲 Bot DMs the triggering user when their run completes

### 6.3 — Local Model Integration (Ollama)
- ✅ Add `OLLAMA_BASE_URL` env var and `MODEL_PROVIDER` (`anthropic` | `ollama`) switch
- ✅ Abstract `AgentLoop` behind a `ModelClient` interface
  - `AnthropicClient` — current implementation
  - `OllamaClient` — calls Ollama API, maps tool use to function calling format
- ✅ Use local model for cheap tasks: log summarisation, payload formatting, report markdown generation
- ✅ Reserve Claude for reasoning-heavy tasks: autonomous sessions, PR analysis, finding assessment

### 6.4 — RAG Pipeline (for local models)
> Not needed for Claude (200k context window). Required when local models with smaller windows are added.

- 🔲 Vector database: `pgvector` extension on existing PostgreSQL instance
- 🔲 Embedding pipeline: chunks Cartesi docs into 512-token segments, embeds with `nomic-embed-text`
- 🔲 `context/retriever.py` — cosine similarity search, returns top-k relevant chunks
- 🔲 `context/assembler.py` — fallback path: if `MODEL_PROVIDER=ollama`, use RAG instead of full injection
- 🔲 Re-embed when source docs are updated (file watcher or manual trigger)

### 6.5 — Auto-PR: Agent Creates Test Definitions
- ✅ After PR analysis, if Claude suggests new tests and confidence is high, automatically:
  1. Create a new branch in the `cartesi-rvp` repo: `auto-test/v1.x.x-suggestions`
  2. Write the suggested definition `.md` files to `tests/definitions/`
  3. Open a GitHub PR with a description summarising the gap analysis
  4. Tag the PR with `ai-suggested` and `needs-review`
- ✅ New tool: `create_github_pr(branch, files, title, body)` using GitHub API
- ✅ Human reviews and merges → triggers seed script automatically via CI

---

## Supporting Tasks (Cross-Phase)

### Testing & Quality
- ✅ Unit tests for `interpreter.py` (malformed YAML, missing fields, valid parsing)
- ✅ Unit tests for each assertion executor (mock httpx, mock Docker SDK)
- ✅ Unit tests for `pool.py` (concurrent acquire/release, capacity enforcement)
- ✅ Integration test: full run flow with a real Docker sandbox (CI only)
- ✅ `pytest` + `pytest-asyncio` test suite in `tests/unit/` and `tests/integration/`

### CI/CD
- ✅ `.github/workflows/ci.yml`
  - On PR: lint (ruff), type check (mypy), unit tests (pytest)
  - On merge to `main`: build Docker images, push to GHCR
- ✅ `.github/workflows/release-test.yml`
  - Triggered by `rvp.releases` webhook → spins up RVP platform, runs full suite
  - Posts results back to the GitHub release as a comment

### Operations
- ✅ `Makefile` — common commands: `make up`, `make down`, `make seed`, `make logs`, `make build-base`
- ✅ Health check endpoint improvements — orchestrator `/healthz` to include RabbitMQ + DB ping
- ✅ Metrics endpoint — Prometheus `/metrics` on orchestrator (run counts, queue depths, sandbox pool usage)
- ✅ Log structured formatting — JSON logs with `run_id`, `sandbox_id`, `session_id` fields for easy filtering
- ✅ Alembic migrations — replace raw `init.sql` with versioned Alembic migrations for schema evolution

---

## Quick Reference — What To Build Next

The next immediate priority is **Phase 6 (optional enhancements)**, starting with:

1. `services/dashboard/package.json` — project dependencies
2. `services/dashboard/vite.config.ts` — build config + API proxy
3. `services/dashboard/src/App.tsx` — routing shell
4. `services/dashboard/src/hooks/useWebSocket.ts` — live data hook
5. `services/dashboard/src/pages/Runs.tsx` — primary view
6. `services/dashboard/src/pages/RunDetail.tsx` — run + test results
7. `services/dashboard/src/components/AgentStream.tsx` — live AI output
8. `services/dashboard/src/pages/Session.tsx` — AI session UI
9. Supporting orchestrator routes (`/tests`, `/sessions`, `/queues`)
10. Dockerfile + Nginx config

---

*Last updated: Phases 1–6 complete. Platform fully implemented. 6.2 (Discord bot) and 6.4 (RAG) are optional future additions.*
