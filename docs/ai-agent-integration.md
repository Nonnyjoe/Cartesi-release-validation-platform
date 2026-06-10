# AI Agent Integration — Operational Log

This document is a working record of the AI Session / Agent integration: what it should do,
how it is wired into the rest of the platform, what has been tried, what currently works, and
what is still broken or open. Update this as you iterate.

---

## 1. Goal

Allow a user to start an **AI Session** from the dashboard's `AI Sessions` sidebar entry. The
session must connect to Anthropic Claude via a **per-session API key supplied by the user** and
let the agent **operate the running Cartesi platform end-to-end**, including:

- Running **whitelisted test definitions** (`ai_allowed: true` on the YAML frontmatter) with
  **inputs decided by the agent** (parameter overrides — payloads, expectations, repeat counts,
  etc.).
- Performing **manual operations** outside the test runner:
  - Sending arbitrary inputs to a sandbox's Anvil chain (via `chain_tx`-style submission and
    cast commands).
  - Calling the sandbox's **v2.x JSON-RPC API** (`cartesi_*` methods at
    `http://<sandbox-host>:<jsonrpc-port>/rpc`).
  - Running arbitrary commands against the sandbox's CLI tools (`cartesi-rollups-cli`, `cast`,
    `forge`) via `docker exec` against the `rvp-cli-<short_sandbox_id>` container.
  - Reading container logs (`advancer`, `claimer`, `validator`, `jsonrpc`, `evm-reader`,
    `anvil`, `cli`, `db`).
  - **Read-only** queries against this project's Postgres (the orchestrator/test/sandbox
    schemas) using the restricted `ai_reader` DB role.
  - Provisioning / tearing down sandboxes (by triggering or cancelling runs via the
    orchestrator's `/runs` API).
- Reasoning over a deep, **Cartesi-aware knowledge bundle**: the official Cartesi Skills repo
  (10 skills, ~4400 lines) plus this suite's project-specific docs (executor reference, test
  catalog, sandbox topology, contract addresses, JSON-RPC quickref, dApp behaviour).

The end user should be able to:
1. Open the dashboard, click `+ New Session`.
2. Paste their Anthropic API key, pick a model, optionally bind to an existing run/sandbox, and
   write a goal.
3. Watch the agent stream tokens, tool calls, and findings live (WebSocket).
4. See an audit log of every tool invocation persisted in `ai.tool_invocations` and surfaced in
   a collapsible panel on the Session detail page.
5. See the session itself appear in the Sessions list **without reloading the page** (live
   WebSocket update).

---

## 2. What this is NOT

- **NOT a chat-only assistant.** The agent's value is taking actions in the sandbox/test
  runner — pure conversational answers are out of scope.
- **NOT multi-tenant / multi-user-secure.** There is one shared `ai_reader` DB role with a
  static password; API keys are encrypted at rest with one shared symmetric key
  (`AI_SESSION_KEY`) but anyone with orchestrator DB access can decrypt them.
- **NOT a replacement for the test-runner.** The agent invokes the test-runner via the existing
  `tests.commands` RabbitMQ queue; it does not implement its own executor.
- **NOT yet able to provision its own sandbox autonomously and reliably.** The tool exists
  (`provision_sandbox`) and works mechanically, but sandbox provisioning takes 2-3 minutes and
  is flaky on a freshly-restarted Docker daemon, so demos depend on having a sandbox already
  `ready` when the session starts.
- **NOT supporting non-Anthropic providers.** Decided up-front with the user.
- **NOT performing AES-GCM encryption in the current running images.** The code requests
  `cryptography>=42.0` but PyPI was unreachable during builds; the runtime falls back to
  base64 (NOT secure). Re-build when PyPI is available to enable real encryption.

---

## 3. Platform hookup

### 3.1 Services involved

| Service              | Role in the AI flow                                                  |
|---|---|
| `dashboard`          | UI: Sessions list, NewSessionModal, Session detail, tool audit panel, Tests page "AI" toggle |
| `orchestrator`       | REST API: `POST /sessions` (encrypts key, persists, publishes), `GET /sessions`, `GET /sessions/{id}/tools`, `PATCH /tests/{id}` (toggle `ai_allowed`), `GET /tests?ai_allowed=true`. Also publishes `ai.session_created` to Redis pub/sub. |
| `ai-agent`           | Consumes `ai.requests` from RabbitMQ. Decrypts the session's API key. Builds the Claude system prompt (project knowledge + Skills summary). Drives the observe→reason→act loop. Publishes streaming events. |
| `test-runner`        | Consumes `tests.commands`. Detects AI-triggered messages (presence of `session_id`/`parameter_overrides`/`definition_parsed_override`) and applies overrides before executing. |
| `sandbox-manager`    | Consumes `sandbox.queue`. Provisions docker-compose stacks. Same flow as ordinary runs. |
| `postgres`           | `ai.sessions` (with encrypted key columns + `model_id`), `ai.tool_invocations` (audit log), `tests.definitions.ai_allowed`. Role `ai_reader` with `SELECT` on the read tables. |
| `redis`              | Pub/sub channel `rvp:live` — broadcast hub for live events. |
| `rabbitmq`           | Queues: `ai.requests`, `ai.results`, `tests.commands`, `sandbox.queue`. |

### 3.2 Live-update path

```
dashboard (WS /ws[?channel=session_id])
  ↑
orchestrator (websocket.py — broadcasts to global + run_id + session_id channels)
  ↑
Redis pub/sub  (channel: rvp:live)
  ↑
publishers (ai-agent: session_events.py; orchestrator: notifications.py + sessions.py)
```

`POST /sessions` emits an `ai.session_created` event so the list updates instantly. The agent
emits `session_started`, `ai.token`, `ai.tool_call`, `ai.tool_result`, `ai.finding`,
`session_completed`. Both the Sessions list page and the Session detail page receive these.

### 3.3 Knowledge bundle

The agent builds its system prompt from three layered sources, ~25–30k tokens total:

1. **Operator persona + rules** (inline in `templates/<mode>.py`): "you are a Cartesi node
   operator, never invent addresses, prefer trigger_test for known scenarios".
2. **Project knowledge** at `services/ai-agent/context/sources/project/`:
   - `executor-reference.md` — every test-runner executor + the override leaves the agent can
     pass to `trigger_test`.
   - `test-catalog.md` — auto-generated list of `ai_allowed` tests (slug, name, override keys).
     Run `scripts/build_test_catalog.py` to refresh.
   - `sandbox-topology.md` — container names + ports + which tool to use for which service.
   - `contracts-devnet.md` — pinned addresses (InputBox, portals, factories).
   - `cartesi-jsonrpc-quickref.md` — the 14+ `cartesi_*` methods with shapes.
   - `test-app-behavior.md` — the echo dApp's behaviour.
3. **Cartesi Skills summary** — top section of each of these mounted skills:
   `cartesi-l1-contracts`, `cartesi-jsonrpc`, `cartesi-local-dev`, `cartesi-debug`. The full
   skill text is reachable on demand via the `lookup_skill` tool.

Skills are bind-mounted from `/Users/idogwuchi/Documents/Cartesi/cartesi-skills` into the
ai-agent container at `/app/knowledge/cartesi-skills` (`docker-compose.yml`).

### 3.4 Per-session credentials

1. `POST /sessions` accepts `anthropic_api_key` (string ≥20 chars) and `model_id`.
2. The orchestrator's `api/crypto.py` calls `encrypt_key(plain)` → `(ciphertext, nonce)` and
   stores both in `ai.sessions.anthropic_key_ciphertext` / `anthropic_key_nonce`. The plaintext
   key is **never** put on the RabbitMQ message — only the `session_id` is.
3. When the ai-agent consumer picks up the request, `SessionManager._load_credentials()` reads
   the row, calls `crypto.decrypt_key(...)`, and constructs a per-session
   `anthropic.AsyncAnthropic(api_key=...)` client.
4. `AgentLoop(api_key, model=...)` is initialised per session — the global `ANTHROPIC_API_KEY`
   env var remains as a fallback only.

Both `crypto.py` files fall back to base64 if `cryptography` isn't installed — they log
`AI session keys decoded base64 only (INSECURE)`. To get real AES-GCM, uncomment
`cryptography>=42.0` in both `requirements.txt` files (orchestrator + ai-agent) and rebuild
when the network is healthy.

---

## 4. Tools wired to the agent

Defined in `services/ai-agent/tools/__init__.py` and dispatched by
`services/ai-agent/tool_executor.py`. Every call is wrapped with `AuditedCall` and persists
to `ai.tool_invocations` (one row per call: tool_name, input, output, status, duration_ms).

### Existing tools (kept)

| Tool                | Effect                                                                         |
|---|---|
| `send_advance_input`| POST JSON envelope to node HTTP bridge — submits a v1 advance input.            |
| `query_graphql`     | POST GraphQL query to the sandbox's GraphQL endpoint.                           |
| `call_inspect`      | Synchronous inspect-state.                                                     |
| `read_logs`         | `docker logs` on `rvp-<component>-<short_sandbox_id>`. Updated to fall back to v2.x containers when the agent asks for "node". |
| `run_cast_command`  | Run a `cast` command inline (legacy — depends on `cast` being on PATH in the ai-agent container; currently failing). |
| `generate_payload`  | Returns a random/structured payload for testing.                                |
| `get_node_state`    | Aggregate health + counts via GraphQL + HTTP.                                   |
| `verify_voucher`    | Fetch + check Merkle proof via GraphQL.                                         |
| `advance_time`      | Mine N blocks on the sandbox's Anvil.                                          |
| `report_finding`    | Record an anomaly to `ai.sessions.findings`.                                   |
| `restart_component` | (Chaos mode) restart a sandbox container.                                       |
| `pause_network`     | (Chaos mode) disconnect a container from its sandbox network.                   |

### New tools added by this integration

| Tool                  | Effect                                                                                          |
|---|---|
| `trigger_test`        | Publishes a `tests.commands` message for a whitelisted test (`ai_allowed=true`) with `parameter_overrides`. Polls `tests.results` for completion. **Working.** |
| `read_test_definition`| Fetches the full parsed YAML + override keys for a slug.                                        |
| `run_cli_command`     | `docker exec rvp-cli-<short_id> <binary> <args>` via the docker Python SDK (uses the mounted `/var/run/docker.sock`). Whitelisted binaries: `cartesi-rollups-cli`, `cast`, `forge`, `bash`. Now correctly resolves the container. **Still failing for `cartesi-rollups-cli` because that binary isn't on the cli container's PATH — needs investigation.** |
| `call_jsonrpc`        | POST to `http://host.docker.internal:<host_jsonrpc_port>/rpc`. Method must start with `cartesi_`. **Working.** |
| `query_db`            | SELECT-only SQL against Postgres as role `ai_reader` (5s statement timeout, 200 rows max). **Working** after the role was given LOGIN + password and `AI_READER_DATABASE_URL` was wired into the compose. |
| `provision_sandbox`   | `POST /runs` on the orchestrator with the v2 release/image tags. **Mechanically working**, but provisioning is slow (~2-3 min) and brittle right after a Docker restart. |
| `teardown_sandbox`    | `POST /runs/{run_id}/cancel`. **Working.**                                                      |
| `lookup_skill`        | Reads sections of `/app/knowledge/cartesi-skills/<skill>/SKILL.md`. **Working.**                |

### Wiring details that matter

- `ToolExecutor` is constructed with the sandbox's host-mapped ports (anvil/node/graphql).
  Until this commit the executor used `localhost:<default_port>`; now `SessionManager`
  resolves the real ports from `sandbox.sandboxes` and the executor uses
  `host.docker.internal:<port>` so requests from inside the ai-agent container reach
  the sandbox's published ports.
- For `read_logs` and `run_cli_command`, the agent talks straight to the Docker daemon via
  the mounted socket. Compose has `extra_hosts: ["host.docker.internal:host-gateway"]` so
  Linux Docker resolves the same hostname as Docker Desktop on Mac.
- The audit recorder uses `json.dumps(..., default=str)` to tolerate UUID/datetime values
  surfaced in tool outputs (otherwise the publisher crashes with
  `TypeError: Object of type UUID is not JSON serializable`).

---

## 5. UI hookup

| Page                                  | What was added/changed                                                    |
|---|---|
| `services/dashboard/src/pages/Sessions.tsx` | NewSessionModal: API key input (password-style) + model picker; "Live" indicator dot; global WebSocket subscription + debounced refresh on session-related events. |
| `services/dashboard/src/pages/Session.tsx`  | Tool audit panel (`/sessions/{id}/tools`) with status badges and expandable input/output JSON. Auto-refresh on WS events. |
| `services/dashboard/src/pages/Tests.tsx`    | New "AI" column per row with a toggle that calls `testsApi.toggleAiAllowed(id, !ai_allowed)`. |
| `services/dashboard/src/api.ts`             | `sessionsApi.create` extended with `anthropic_api_key` + `model_id`. New `sessionsApi.tools(id)`. New `testsApi.toggleAiAllowed`. |
| `services/dashboard/src/types.ts`           | Added `ToolInvocation` type; extended `TestDefinition.ai_allowed`. |

---

## 6. Verification & iteration log

Each step below was tried in roughly this order; later fixes supersede earlier failures.

| # | Action                                                                  | Outcome                                                                                             | Resolution                                                                  |
|---|---|---|---|
| 1 | Apply DB migration `0012_ai_session_keys.sql`.                          | OK.                                                                                                 | —                                                                            |
| 2 | First session created via `POST /sessions` with dummy key.              | 500 on `GET /sessions` — list endpoint referenced columns that don't exist (`session_id`, `model`, `completed_at`, `tool_calls_used`, `input_tokens`/`output_tokens`). | Rewrote `_session_row` to use real schema (`id`, `model_id`, `closed_at`, `tool_call_count`, `total_tokens`). |
| 3 | Agent picks up session.                                                 | Crashed with `KeyError: 'release_tag'` in `SessionManager.__init__`.                                | Made `release_tag` optional (`request.get("release_tag") or "unknown"`).    |
| 4 | Real session created with sandbox.                                      | Tool count 0 even though tools were running — `tool_calls_used` only flushed at session close.      | Acceptable; the audit table reflects real-time state.                       |
| 5 | `call_jsonrpc` returns 404.                                             | Wrong URL; sandbox JSON-RPC sits at `/rpc`.                                                         | Tool now uses `http://host.docker.internal:<port>/rpc`.                     |
| 6 | `read_logs` returns "Container 'rvp-node-...' not found".               | v2.x sandboxes have no monolithic node container.                                                   | Tool now falls back to `rvp-advancer-...` and `rvp-jsonrpc-...` when "node" is requested. |
| 7 | `query_db` returns "password authentication failed for user 'ai_reader'". | Role was `NOLOGIN` and had no password.                                                              | `ALTER ROLE ai_reader WITH LOGIN PASSWORD 'ai_reader_changeme'`; compose now passes `AI_READER_DATABASE_URL=postgresql://ai_reader:ai_reader_changeme@postgres:5432/rvp`. |
| 8 | `run_cli_command` errored with "docker not found in PATH".              | Tool used subprocess `docker exec`; ai-agent image has no docker CLI.                                | Migrated to the docker Python SDK over the mounted socket.                  |
| 9 | `trigger_test` always returned `status='timeout'`.                      | Polling loop quit at the deadline; the test result row was written ~700ms later.                    | Added one final post-deadline DB check; reduced poll interval to 1s.        |
| 10| `publish_session_event` crashed with `TypeError: Object of type UUID is not JSON serializable`. | Tool outputs from `query_db` contained UUIDs.                                                       | Added `default=str` to both `json.dumps` sites in `publishers/session_events.py`. |
| 11| `provision_sandbox` returned 500 from orchestrator.                     | Tool used `triggered_by="ai-agent"` which is not in the `triggered_by_type` Postgres enum.          | Tool now passes `triggered_by="user", requested_by="ai-agent"`.             |
| 12| `provision_sandbox` later failed with "pull access denied for 'latest'". | Tool defaulted to `image_tag="latest"`.                                                              | Tool now defaults to the same `release/image` as the last successful run (`v2.0.0-alpha.11` / `cartesi/rollups-runtime:0.12.0-alpha.39`). |
| 13| Demo session run on a sandbox.                                          | 16 of 18 tools succeeded — `call_jsonrpc cartesi_getChainId` returned `0x7a69`; `cartesi_listApplications` returned data; `trigger_test jsonrpc-list-applications-v2` → `status=passed` in 1.3s. | This is the end-to-end success point. |
| 14| Docker daemon died unexpectedly.                                        | All sandboxes torn down; live testing paused.                                                       | Wait for Docker, then re-provision a fresh sandbox.                         |

### What still fails / open items

> **All items in this list were addressed in Iteration 2 (2026-06-10) — see §9.**
> Kept for history; do not work these as-written.

- ~~**`run_cli_command cartesi-rollups-cli`**~~ — RESOLVED. Root cause: the cli image is
  `docker:27-cli` + npm `@cartesi/cli`, so its binary is `cartesi` — `cartesi-rollups-cli`
  ships in the **runtime image** containers (`rvp-advancer-*`, `rvp-jsonrpc-*`), and
  `cast`/`forge` ship in the **Anvil (foundry)** container. `cli.py` now routes each binary
  to the right container automatically and falls back through candidates.
- ~~**`run_cast_command`**~~ — RESOLVED. Re-routed through docker exec into
  `rvp-anvil-<short>` (default `--rpc-url http://localhost:8545` inside that container).
- ~~**AES-GCM encryption**~~ — `cryptography>=42.0` is now active (uncommented) in both
  requirements.txt files; rebuild both images when PyPI is reachable. Compose now also
  propagates `AI_SESSION_KEY` from the root `.env` into both services (it previously
  relied on the per-service `.env` files only).
- ~~**`provision_sandbox` reliability**~~ — orchestrator-call timeout raised to 60s
  (sandbox-manager's docker client already used timeout=600).
- ~~**Tool count `tool_calls_used` lags**~~ — RESOLVED. The audit recorder now increments
  `ai.sessions.tool_call_count` on every invocation.

---

## 9. Iteration 2 — 2026-06-10 (verification & completion pass)

All five open items above were fixed, plus the following defects found while auditing the
implementation against this document:

| # | Defect | Fix |
|---|---|---|
| 1 | `infra/postgres/init.sql` still created `ai_reader` as `NOLOGIN` — fresh installs would re-hit iteration-log item 7. | init.sql now mirrors migration 0012 (`LOGIN PASSWORD 'ai_reader_changeme'`). |
| 2 | `POST /sessions/{id}/message` published to routing key `ai.session.<id>.message` on the **direct** exchange `rvp.ai` — no binding, message silently dropped; collaborative/interactive sessions could never receive user messages. | Publisher now routes `{"type":"user_message", ...}` via the existing `ai.requests` queue; the ai-agent consumer detects it and dispatches to the live session's queue (and cleans the queue map up at session end). |
| 3 | Chaos tools (`restart_component`, `pause_network`) were never dispatched (`ToolExecutor._dispatch` had no branch) and `run_chaos` called a nonexistent `_run_session`; `chaos.py` template had an incompatible `render()` signature. | Dispatch added (container names resolved from sandbox_id + docker_network now loaded from `sandbox.sandboxes`); `run_chaos` rewritten on the autonomous pattern; template signature unified. Chaos mode is still **not** exposed via API/enum — code path is ready for enablement. |
| 4 | An ai-agent crash mid-session left `ai.sessions.status='active'` forever. | `run_autonomous` marks the session `failed` and emits `session_failed` on unhandled exceptions. |
| 5 | `context/sources/project/test-catalog.md` was never generated (the assembler tolerated its absence but the agent had no whitelist catalog). | `main.py` now best-effort regenerates the catalog on every container start. |
| 6 | `read_logs` tool schema only allowed `node\|anvil` even though the implementation supports all v2.x components. | Schema enum expanded (advancer, claimer, validator, jsonrpc, evm-reader, cli, db). |
| 7 | `run_cli_command` schema enum lacked `cartesi` / `sh` and described the wrong routing. | Schema updated to match the new router. |

Testing instructions for this iteration: see `AI_TESTING_README.md` at the repo root.

---

## 10. Iteration 3 — 2026-06-10 (post-test-report fixes)

Driven by `docs/ai-integration-test-report-2026-06-10.md`. Verification verdict: all
Iteration 2 fixes confirmed working end-to-end (binary routing, cast, live tool count,
user-message injection, AES-GCM, catalog generation, guardrails). Three new issues found
and fixed:

| Report ID | Issue | Fix |
|---|---|---|
| F-1 | Both `trigger_test` calls timed out: the post-provision full-suite sweep leaves ~200 messages (~80 min) on `tests.commands` and AI-triggered commands queue behind it with a 90s poll deadline. | New **AI priority lane**: `trigger_test` now publishes to a dedicated durable queue `tests.commands.ai`; the test-runner consumes it on a separate channel (prefetch 1) concurrently with the bulk queue. Queue declared idempotently by both publisher and consumer, plus added to `infra/rabbitmq/definitions.json` for fresh installs. Note: an AI test can now execute concurrently with a bulk test on the same sandbox — intended. |
| F-2 | `AI_SESSION_KEY: ${AI_SESSION_KEY:-}` in compose silently overrode the service `env_file` values with `""` when the var was missing from root `.env` → fresh `up -d` would ship an empty key. | Compose now uses `${AI_SESSION_KEY:?...}` (refuses to start when unset). Both `crypto.py` files log a high-visibility error at import when the key is missing/empty; `_key()`'s RuntimeError message explains where the value must live. `.env.example` updated: root `.env` is the canonical (and required) location. |
| F-3 | `POST /runs/{run_id}/cancel` only flipped `orchestrator.runs.status`; a `ready` sandbox stayed up until its entire test backlog drained. | The sandbox-manager's `_wait_for_tests` poll loop now re-checks `_is_run_cancelled` every 5s and returns early, so the existing `finally:` teardown fires within ~one poll interval of the cancel. |

Report suggestions deliberately **not** implemented yet (candidates for next iteration):
- Playwright smoke for the dashboard (report §4 suggestion 4) — manual/browser check still required for true 4.6 PASS.
- Session cancel ends in `aborted` (not `completed`) — working as designed; documenting the
  state machine is still TODO.

Re-test focus for the next verification run: re-run Phase 3 of `AI_TESTING_README.md` while
a full sweep is in progress and confirm both `trigger_test` calls return `status='passed'`
in seconds; then `POST /runs/{id}/cancel` and confirm all `rvp-*-<short>` containers are
gone within ~60s without manual `docker stop`. Requires rebuilding `ai-agent`,
`test-runner`, `sandbox-manager`, and `orchestrator`.

---

## 7. End-to-end demo recipe

Useful when verifying a clean run from scratch.

```bash
# 0. confirm services are healthy
docker compose ps
curl -s http://localhost:8000/sandboxes | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"

# 1. provision a sandbox (~2-3 min)
RUN_ID=$(curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"release_tag":"v2.0.0-alpha.11","image_tag":"cartesi/rollups-runtime:0.12.0-alpha.39","priority":5,"triggered_by":"user","requested_by":"ai-demo"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 2. wait for a ready sandbox bound to that run
while :; do
  s=$(curl -s "http://localhost:8000/sandboxes" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); hit=[x for x in d if x.get('run_id')=='$RUN_ID']; print(hit[0]['status'] if hit else '')")
  echo "$s"; [ "$s" = "ready" ] && break; sleep 8
done
SANDBOX_ID=$(curl -s "http://localhost:8000/sandboxes" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print([x for x in d if x.get('run_id')=='$RUN_ID'][0]['id'])")

# 3. create an AI session bound to that sandbox
API_KEY=$(grep ANTHROPIC_API_KEY ./services/ai-agent/.env | cut -d= -f2)
SESSION_ID=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d "{\"mode\":\"autonomous\",\"sandbox_id\":\"$SANDBOX_ID\",\"run_id\":\"$RUN_ID\",\"goal\":\"Demo: 1) cartesi_getChainId; 2) cartesi_getNodeVersion; 3) trigger_test jsonrpc-get-chain-id-v2; 4) trigger_test jsonrpc-list-applications-v2; 5) summarise.\",\"anthropic_api_key\":\"$API_KEY\",\"model_id\":\"claude-opus-4-6\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "$SESSION_ID"

# 4. watch
while :; do
  S=$(curl -s "http://localhost:8000/sessions/$SESSION_ID" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  T=$(curl -s "http://localhost:8000/sessions/$SESSION_ID/tools" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d))")
  echo "status=$S tools=$T"; [ "$S" != "active" ] && break; sleep 8
done

# 5. inspect the audit
curl -s "http://localhost:8000/sessions/$SESSION_ID/tools" \
  | python3 -c "import sys,json; [print(f\"{t['status']:6} {t['tool_name']:22} {t['duration_ms']}ms\") for t in json.load(sys.stdin)]"
```

Expected: `cartesi_getChainId` → `0x7a69`, `cartesi_getNodeVersion` → `2.0.0-alpha.11`,
`trigger_test` → `status='passed'` for both tests in <2s each.

---

## 8. Files touched (canonical)

```
infra/postgres/init.sql                                    (schema for fresh installs)
infra/postgres/migrations/0012_ai_session_keys.sql         (migration for existing installs)
services/orchestrator/api/crypto.py                        (encrypt with AES-GCM or base64 fallback)
services/orchestrator/api/routes/sessions.py               (create + list + tools endpoints, real schema)
services/orchestrator/api/routes/tests.py                  (PATCH ai_allowed + GET ?ai_allowed)
services/orchestrator/api/websocket.py                     (broadcast by session_id too)
services/orchestrator/requirements.txt                     (cryptography commented out pending PyPI)
services/ai-agent/crypto.py                                (decrypt counterpart)
services/ai-agent/session_manager.py                       (per-session key + ports lookup)
services/ai-agent/agent_loop.py                            (accept api_key + model per session)
services/ai-agent/tool_executor.py                         (host.docker.internal + new tools dispatch)
services/ai-agent/context/assembler.py                     (three-tier prompt with Skills summary)
services/ai-agent/context/templates/*.py                   (render project_knowledge + skills_summary)
services/ai-agent/context/sources/project/*.md             (executor ref, topology, contracts, jsonrpc quickref, test-app, test-catalog)
services/ai-agent/publishers/session_events.py             (default=str in json.dumps)
services/ai-agent/requirements.txt                         (cryptography commented out)
services/ai-agent/scripts/build_test_catalog.py            (generates project/test-catalog.md)
services/ai-agent/tools/__init__.py                        (tool schemas for Claude)
services/ai-agent/tools/audit.py                           (writes ai.tool_invocations)
services/ai-agent/tools/cli.py                             (docker SDK exec)
services/ai-agent/tools/db_query.py                        (ai_reader SELECT-only)
services/ai-agent/tools/jsonrpc.py                         (cartesi_* via host port)
services/ai-agent/tools/node.py                            (read_logs with v2.x container fallback)
services/ai-agent/tools/sandbox.py                         (provision/teardown via /runs)
services/ai-agent/tools/skill_lookup.py                    (cartesi-skills section reader)
services/ai-agent/tools/test_trigger.py                    (read_test_definition + trigger_test)
services/test-runner/consumers/test_commands.py            (apply parameter_overrides for AI msgs)
services/dashboard/src/pages/Sessions.tsx                  (modal w/ key+model, WS live updates)
services/dashboard/src/pages/Session.tsx                   (tool audit panel)
services/dashboard/src/pages/Tests.tsx                     (AI column + toggle)
services/dashboard/src/api.ts                              (sessionsApi.tools, testsApi.toggleAiAllowed)
services/dashboard/src/types.ts                            (ToolInvocation; TestDefinition.ai_allowed)
docker-compose.yml                                         (mounts cartesi-skills + docker.sock; SANDBOX_HOST; AI_READER_DATABASE_URL)
.env.example                                               (AI_SESSION_KEY)
tests/seed_definitions.py                                  (picks up ai_allowed from YAML)
tests/definitions/*.md                                     (~15 starter tests flipped to ai_allowed: true)
```
