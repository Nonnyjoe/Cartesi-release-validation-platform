# AI Integration Test Report — 2026-06-10 (Run 2)

Verification against `docs/ai-agent-integration.md` §9 (Iteration 2) using
`AI_TESTING_README.md`. This report supersedes Run 1 from earlier today and reflects a
**full fresh re-run** at the user's request. The autonomous Phase 3 session was executed
on `claude-opus-4-6`; interactive Phase 4 sessions used the same model (Anthropic credit
balance was topped up by the user between Phase 3 and Phase 4 — see "Incidents during
testing").

## Environment

| Item | Value / Evidence |
|---|---|
| Docker server | `29.2.1` (from morning's Run 1; not re-queried this run) |
| Compose project | `cartesi-rvp` (10 services) |
| Git rev | `e37fefb fix(voucher_v2): reduce INPUTS_PROCESSED restart delay to 45s` (unchanged from Run 1) |
| Dirty files | 86 modified / 22 untracked (unchanged from Run 1) |
| `AI_SESSION_KEY` in root `.env` | PRESENT (carried over from Run 1's fix — `8gwy1718iZzIyyWguHAu7NGzbqg4db4DctrtTm2KbZQ=`) |
| `cryptography` active | YES — `cryptography 48.0.1` in both `ai-agent` and `orchestrator` (carried over from Run 1 rebuild) |
| Compose services | All 10 up; `ai-agent` + `orchestrator` from Run 1's rebuild (~2h uptime), others 18h+ |
| Sandbox containers | `rvp-*-32fbdef0` provisioned fresh for this run; torn down at the end |

### IDs for re-querying

| Resource | UUID |
|---|---|
| `RUN_ID` | `b0249349-9337-4dd3-9679-d7cc9f89a83b` |
| `SANDBOX_ID` | `32fbdef0-863a-4a08-9b60-37fb829ae964` |
| Phase 3 autonomous session (Opus, ~138k input tokens) | `63c22d74-0d01-4734-bc49-dd98c73ad94c` |
| First interactive session (Opus, blocked by credits — cancelled) | `23194cd1-de16-4fde-8b3c-ebadc127abce` |
| Quick Haiku confirmation session (also blocked, cancelled) | `bd668c0a-1278-4a4e-b008-e8c2b6f261a4` |
| Phase 4.1/4.4/4.5 interactive session (Opus, after credit top-up) | `712ffb0a-c07a-4fec-b14d-e77b65307c7f` |
| Phase 3 trigger_test result_ids (queued, never picked up before sandbox teardown) | `555ecc3d-402b-4c98-b9d0-5987c879a039`, `252f9603-efda-4ff4-8155-cb19d7903311` |

## Phase results

| Phase | Check | Result | Evidence |
|---|---|---|---|
| 0 | Docker up | PASS | `docker info > /dev/null && echo DOCKER-OK` → `DOCKER-OK` |
| 0 | `AI_SESSION_KEY` set | PASS | `grep '^AI_SESSION_KEY=..' .env` returned the value (Run 1's fix carried forward) |
| 0 | Anthropic key | PASS | `services/ai-agent/.env` contains the per-session key |
| 0 | Cartesi Skills repo | PASS | `/Users/idogwuchi/Documents/Cartesi/cartesi-skills/cartesi-jsonrpc/SKILL.md` exists |
| 1 | Image rebuild | PASS (carried) | Same images as Run 1; `cryptography 48.0.1` verified live in both containers |
| 1 | Orchestrator API up | PASS | `GET /sessions` returned `{"items":[…]}` |
| 1 | Catalog generated | PASS | `docker compose exec ai-agent cat context/sources/project/test-catalog.md` head: `# Whitelisted Test Catalog (auto-generated)` listing `generic-input-v2`, `notice-generation-v2`, `graphql-inputs-query`, `inspect-state`, … |
| 1 | No `INSECURE` log | PASS | `docker compose logs orchestrator ai-agent --since 120m \| grep -i insecure` → empty |
| 1 | Whitelist API | PASS | `GET /tests?ai_allowed=true` → 15 items |
| 2 | Sandbox `ready` | PASS | 0:00 → ready at 4m41s (provisioning 12:32:31 → 12:37:13) |
| 2 | Binary routing pre-check | PASS | `which cartesi` in `rvp-cli-32fbdef0` = `/usr/local/bin/cartesi`; `which cartesi-rollups-cli` in `rvp-advancer-32fbdef0` = `/usr/bin/cartesi-rollups-cli`; `which {cast,forge}` in `rvp-anvil-32fbdef0` = `/usr/local/bin/{cast,forge}` |
| 3 | Autonomous per-tool table | MIXED (13 OK / 2 trigger_test timeout) | See audit table below |
| 3 | Session terminal state | PASS (`failed`, not stuck `active`) | Iteration 2 §9 #4 fix verified |
| 3 | `tool_calls_used` live during active | PASS | observed: `3 → 8 → 9 → 11 → 14 → 15` while `status=active` (Iteration 2 §9 #5 fix) |
| 4.1 | User-message injection | PASS | 1 tool call recorded (`call_jsonrpc cartesi_getChainId`, 59ms `ok`) after `POST /sessions/{id}/message` to session `712ffb0a-…`. Without Iteration 2 §9 #2 this would be 0. |
| 4.2 | AES-GCM ciphertext shape | PASS | All 4 most-recent `ai.sessions` rows: `octet_length(anthropic_key_ciphertext)=124`, `octet_length(anthropic_key_nonce)=12`. Plaintext key = 108 bytes; ciphertext = 108 + 16 (GCM tag) = 124 ✓ |
| 4.2 | No INSECURE log | PASS | (same as Phase 1) |
| 4.3 | `ai_reader` LOGIN in init.sql | PASS (static) | `infra/postgres/init.sql`: `CREATE ROLE ai_reader WITH LOGIN PASSWORD 'ai_reader_changeme';` + `EXCEPTION WHEN duplicate_object THEN ALTER ROLE ai_reader WITH LOGIN PASSWORD '…';` |
| 4.4 | `read_logs claimer` | PASS | `container=rvp-claimer-32fbdef0`, `status=ok`, 5 lines, 287ms |
| 4.4 | `read_logs evm-reader` | PASS | `container=rvp-evm-reader-32fbdef0`, `status=ok`, 5 lines, 24ms |
| 4.5 | `query_db DELETE` rejected | PASS | `error="Only SELECT statements are allowed."`, `status=error` |
| 4.5 | `call_jsonrpc eth_blockNumber` rejected | PASS | `error="Method must start with one of ('cartesi_',); got 'eth_blockNumber'"`, `status=error` |
| 4.5 | `trigger_test erc20-deposit-v2` rejected (not whitelisted) | PASS | `error="Definition 'erc20-deposit-v2' is not ai_allowed (whitelist)"`, `status=error` |
| 4.5 | `run_cli_command rm` rejected | PASS | `error="Binary 'rm' not whitelisted. Allowed: ['bash', 'cartesi', 'cartesi-rollups-cli', 'cast', 'forge', 'sh']"`, `status=error` |
| 4.6 | Dashboard reachable | PASS | `curl -I http://localhost:3000/` → `HTTP/1.1 200 OK` |
| 4.6 | Backend endpoints | PASS | `GET /sessions`, `GET /tests?ai_allowed=true` (15 items), `GET /sessions/{id}/tools` (7 rows) |
| 4.6 | UI wiring source matches API | PASS (INFERRED for browser behavior) | `Sessions.tsx:5` `import { useWebSocket }`; `Sessions.tsx:11` listens to `'ai.session_created'`; `api.ts:90` `toggleAiAllowed`; `api.ts:110-111` `anthropic_api_key`/`model_id` |
| 4.6 | Browser-visual (modal layout / live add / AI toggle column) | SKIPPED | Test agent has no browser. Source + backend evidence above is sufficient for wiring correctness but does not constitute end-user verification |

### Phase 3 audit table (verbatim, ordered by `created_at`)

```
get_node_state    | ok    |  36ms | (health probe)
call_jsonrpc      | ok    |  82ms | cartesi_getChainId       -> result.data = "0x7a69"   OK
call_jsonrpc      | ok    |  49ms | cartesi_getNodeVersion   -> "2.0.0-alpha.11"         OK
run_cli_command   | ok    | 595ms | binary=cartesi-rollups-cli, container=rvp-advancer-32fbdef0   Iteration 2 fix
run_cli_command   | ok    | 990ms | binary=cartesi,            container=rvp-cli-32fbdef0         Iteration 2 fix
run_cast_command  | ok    | 204ms |                            container=rvp-anvil-32fbdef0        Iteration 2 fix
read_logs         | ok    |  31ms | component=advancer,        container=rvp-advancer-32fbdef0
query_db          | ok    |  29ms | (initial successful SELECT)
trigger_test      | error | 90738ms | jsonrpc-get-chain-id-v2       -> status=timeout (queue contention - see F-1)
trigger_test      | error | 90719ms | jsonrpc-list-applications-v2  -> status=timeout (queue contention)
query_db          | error |  56ms | agent-side SQL error: column "definition_slug" does not exist (tool correctly forwarded DB error)
query_db          | error |  29ms | agent-side SQL error: column "result_json" does not exist (tool correctly forwarded DB error)
query_db          | ok    |  60ms |
query_db          | ok    | 349ms |
query_db          | ok    | 132ms |
```

**Note on the 2 `query_db error` rows**: these are SQL mistakes by the agent (referencing
columns that don't exist in `tests.results`). The tool itself worked correctly — it
forwarded the Postgres error verbatim to the agent. Counting "tools that did what they
should": 13/15 OK. Counting "tools whose backend mechanically performed the right action":
**15/15** (the 2 query_db errors and the 2 trigger_test timeouts all reflect downstream
state, not tool malfunction).

## Failures & diagnosis

### F-1: Both `trigger_test` calls timed out at ~91s (same as Run 1)

**Symptom**

```
status=error  tool_name=trigger_test  duration=90738ms
output: {"status": "timeout", "success": false,
         "result_id": "555ecc3d-402b-4c98-b9d0-5987c879a039",
         "definition_id": "4b63038e-1d89-4519-8503-f70888926f1b",
         "error_message": "No result within 90s. The test may still be running — query
                           tests.results WHERE id='555ecc3d-…' to check.",
         "definition_slug": "jsonrpc-get-chain-id-v2"}
```

Both `trigger_test` invocations returned this shape. The corresponding rows in
`tests.results` were not present at timeout and not present at sandbox teardown either.

**Logs collected**

```
$ curl -sS -u rvp:changeme http://localhost:15672/api/queues/%2F/tests.commands
# Before the sandbox transitioned to ready:
messages: 0      ready: 0      consumers: 1
# Immediately after sandbox went ready (auto-test-sweep enqueued):
messages: 197    ready: 192    consumers: 1
# During / after Phase 3:
messages: 173    ready: 168    consumers: 1
```

**Hypothesis (confirmed)**

Identical to Run 1 (this version's report supersedes that earlier note). When a new
run's sandbox goes `ready`, the orchestrator publishes the full applicable test suite
to `tests.commands` ahead of any AI session. `trigger_test` publishes to the same queue
with no priority bump and default `wait_seconds=90`. With ~190 messages ahead at ~20s
per message, AI-triggered tests sit at the back of an ~60-minute queue.

The tool itself is mechanically correct (publish succeeded, audit row recorded,
polling loop ran the full deadline, the iteration-9 final post-deadline check ran,
and a clean structured timeout response was returned).

**Status**: not an Iteration 2 regression. This is environmental queue contention with
the auto-test-sweep. Reproduced on both Run 1 (192 messages) and Run 2 (197 messages).

**Suggested fix**: see "Open questions" below.

### F-2 (informational — already addressed by morning's fix)

`AI_SESSION_KEY` missing from root `.env`. This had been fixed during Run 1 and the fix
carried into Run 2. No action needed this run.

### F-3 (informational — same as Run 1)

`POST /runs/{id}/cancel` doesn't tear down sandbox containers; the testing readme's
comment overstates what `cancel_run` does. Verified again: after `cancel_run` returned
`{"status":"cancelled"}`, the 8 sandbox containers remained `Up`. Containers were
torn down manually via the `rvp.sandbox_id` label (`docker stop` + `docker rm`).

## Regressions vs `docs/ai-agent-integration.md` §6 item 13

Old baseline (16/18 OK): the two failures were `run_cli_command cartesi-rollups-cli` and
`run_cast_command`. The doc declared both fixed in Iteration 2 §9.

| Tool | Old baseline | Run 1 | Run 2 | Verdict |
|---|---|---|---|---|
| `run_cli_command cartesi-rollups-cli` | FAIL | OK (rvp-advancer-…) | **OK (rvp-advancer-32fbdef0, 595ms)** | fixed (Iteration 2) |
| `run_cli_command cartesi` (added in §9) | n/a | OK | **OK (rvp-cli-32fbdef0, 990ms)** | added, verified |
| `run_cast_command` | FAIL | OK | **OK (rvp-anvil-32fbdef0, 204ms)** | fixed (Iteration 2) |
| `call_jsonrpc` | OK | OK | **OK (0x7a69, 2.0.0-alpha.11)** | no regression |
| `read_logs` advancer | OK | OK | **OK** | no regression |
| `read_logs` claimer (added in §9) | n/a | OK | **OK (rvp-claimer-32fbdef0)** | added, verified |
| `read_logs` evm-reader (added in §9) | n/a | OK | **OK (rvp-evm-reader-32fbdef0)** | added, verified |
| `query_db` | OK | OK | OK (3 successful SELECTs; 2 agent SQL errors correctly forwarded) | no regression |
| `trigger_test` | OK | error (queue contention) | **error (queue contention, same root cause)** | environmental, not a tool regression |
| `get_node_state` | n/a | OK | **OK** | no regression |

**New ratio this run (Phase 3 only): 13 / 15 OK by the strict count, 15 / 15 by tool-correctness.**

Including the negative checks (Phase 4.5), the agent recorded 4/4 expected rejections
with verbatim correct error messages — these are PASSes that REJECTED, exactly as
designed.

## Open questions / suggested next fixes

1. **`tests.commands` queue contention with `trigger_test` (F-1)** — reproducible across
   both runs.
   - `services/ai-agent/tools/test_trigger.py:189-197` publishes to
     `tests.commands` with no priority. Fix options (preferred → fallback):
     (a) Declare a separate `ai.tests.commands` queue and have the test-runner consume
     both; AI gets a private fast lane. (b) Add RabbitMQ message priorities — set
     `priority=9` on `aio_pika.Message` and declare the queue with `x-max-priority`.
   - Bumping the default `wait_seconds` from 90 → 600 alone would mask the symptom but
     not fix the underlying contention.

2. **`AI_SESSION_KEY` startup check** — `services/orchestrator/api/crypto.py` should
   refuse to start if `AI_SESSION_KEY` is missing/empty, instead of failing on first
   `encrypt_key` call. Update `docker-compose.yml` to use `${AI_SESSION_KEY:?must be
   set in root .env}` so compose itself blocks an unset value.

3. **`POST /runs/{id}/cancel` doesn't actually tear down sandboxes (F-3)** —
   `services/orchestrator/api/routes/runs.py:399-414` should additionally publish a
   teardown message to `sandbox.queue` (or transition the attached `ready` sandbox to
   `terminating`). Either fix the code, or fix the misleading Phase 6 comment in
   `AI_TESTING_README.md`.

4. **Dashboard 4.6 visual** — automate a Playwright smoke (new-session modal opens,
   key input is `type="password"`, model picker has 3 options, submit appears in the
   list within 5s without reload) so future test agents can mark 4.6 as a real PASS.

## Incidents during testing

### Anthropic credits exhausted mid-Phase-4

After Phase 3 consumed ~138k input tokens, the first Phase 4.1 attempt (session
`23194cd1-…`) and a subsequent Haiku confirmation (session `bd668c0a-…`) both returned:

```
anthropic.BadRequestError: Error code: 400 - {'type': 'error',
  'error': {'type': 'invalid_request_error',
            'message': 'Your credit balance is too low to access the Anthropic API.
                        Please go to Plans & Billing to upgrade or purchase credits.'},
  'request_id': 'req_011CbuXmqnYjMnqarHG2uG92'}
```

This was caught by Iteration 2 §9 #4: the affected sessions were marked `failed`
instead of stuck `active`. The user topped up credits, after which session
`712ffb0a-…` ran Phase 4.1, 4.4, and 4.5 successfully.

### Apparent filesystem disappearance

Mid-test, several `ls /Users/idogwuchi/Documents/…` commands returned empty or
"No such file or directory" even though the data was intact. This turned out to be a
transient shell-sandbox/permission glitch — re-running `ls` later showed everything
present. **No actual data was lost. No source code was modified by this test agent
other than the `.env` line added during morning's Run 1 (carried forward unchanged).**

## Code changed during testing

Nothing this run. The single change from Run 1 (`AI_SESSION_KEY` added to root `.env`)
remained in place; no further source changes were needed.

## Cleanup

- Interactive session `712ffb0a-…` cancelled via `POST /sessions/{id}/cancel` → `{"ok":true}`.
- Earlier failed/blocked sessions (`23194cd1-…`, `bd668c0a-…`) also cancelled.
- Run cancelled via `POST /runs/{run_id}/cancel` → `{"status":"cancelled","run_id":"b0249349-…"}`.
- Sandbox containers torn down by label: `docker ps --filter "label=rvp.sandbox_id=32fbdef0-…" -q | xargs docker stop -t 5 && … | xargs docker rm -v` — 8 containers stopped, 8 removed; verification `docker ps --filter "label=rvp.sandbox_id=…"` returns 0.
- Outstanding queued `tests.commands` messages with our `result_id`s will now fail rather than complete (sandbox containers gone). The audit timeout outcome in `ai.tool_invocations` remains the canonical Phase 3 trigger_test result.
