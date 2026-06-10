# AI Session Integration — Test & Verification Guide

**Audience:** the Claude Code agent running on this machine with Docker access.
**Goal:** verify the AI Session integration end-to-end after Iteration 2 (2026-06-10),
then produce a structured handdown report for review.

Background reading (do this first):
- `docs/ai-agent-integration.md` — full integration log. §9 lists exactly what Iteration 2
  changed; §6 lists historical failures so you don't re-report known-fixed issues.

You are testing the **changes**, not just the happy path. The checklist in Phase 4 maps
1:1 to the Iteration 2 fixes.

---

## 0. Environment prerequisites

Check each; abort with a clear report entry if one fails.

```bash
# Docker daemon up?
docker info > /dev/null && echo DOCKER-OK

# Required env: root .env must define AI_SESSION_KEY (base64 of 32 random bytes).
grep -q '^AI_SESSION_KEY=..' .env && echo AI_SESSION_KEY-SET || echo "MISSING — generate: python3 -c \"import os,base64;print(base64.b64encode(os.urandom(32)).decode())\" and add to .env"

# Anthropic key for live sessions (used as the per-session key in tests):
grep -q ANTHROPIC_API_KEY services/ai-agent/.env && echo AGENT-KEY-OK

# Cartesi Skills repo must exist at the path mounted in docker-compose.yml:
ls /Users/idogwuchi/Documents/Cartesi/cartesi-skills/cartesi-jsonrpc/SKILL.md && echo SKILLS-OK
```

## 1. Build & start

Iteration 2 touched: `ai-agent`, `orchestrator`, `docker-compose.yml`, `infra/postgres/init.sql`.
Both Python images **must be rebuilt** (among other things this activates AES-GCM via the
now-uncommented `cryptography>=42.0` — requires PyPI reachability).

```bash
docker compose build orchestrator ai-agent          # ~1-3 min; needs network
docker compose up -d
docker compose ps                                   # all services healthy/running
```

DB migration — only needed for an EXISTING database volume (fresh volumes get everything
from `init.sql`):

```bash
docker compose exec -T postgres psql -U rvp -d rvp < infra/postgres/migrations/0012_ai_session_keys.sql
# Idempotent; safe to re-run. Also ensures ai_reader has LOGIN + password.
```

Seed/refresh test definitions (sets `ai_allowed: true` on ~15 starter tests):

```bash
python3 tests/seed_definitions.py   # or run it inside any service container if host python lacks deps
```

### Startup verification

```bash
# 1. Orchestrator API up:
curl -s http://localhost:8000/sessions | head -c 200        # JSON, not connection refused

# 2. ai-agent booted, catalog generated, crypto REAL (not base64 fallback):
docker compose logs ai-agent | tail -30
#   EXPECT: "Test catalog refreshed"  (new in Iteration 2)
#   EXPECT ABSENT: "INSECURE"  — if you see "decoded base64 only (INSECURE)", the
#   cryptography package didn't install; report it and note the build log.

# 3. Catalog content:
docker compose exec ai-agent cat context/sources/project/test-catalog.md | head -20
#   EXPECT: "# Whitelisted Test Catalog" with ≥1 slug (e.g. jsonrpc-get-chain-id-v2).
#   If "_No whitelisted tests yet._": run the seeder, then `docker compose restart ai-agent`.

# 4. Whitelist API:
curl -s "http://localhost:8000/tests?ai_allowed=true" | python3 -c "import sys,json; d=json.load(sys.stdin); items=d.get('items',d); print(len(items),'ai_allowed tests')"
#   EXPECT: ≥ 10

# 5. AI priority lane consumed (Iteration 3 — F-1 fix):
curl -s -u rvp:changeme http://localhost:15672/api/queues/%2F/tests.commands.ai \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('consumers:', d.get('consumers'))"
#   EXPECT: consumers: 1  (test-runner's dedicated channel). 404 or consumers:0 = FAIL.
```

## 2. Provision a sandbox (~2-3 min)

```bash
RUN_ID=$(curl -s -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"release_tag":"v2.0.0-alpha.11","image_tag":"cartesi/rollups-runtime:0.12.0-alpha.39","priority":5,"triggered_by":"user","requested_by":"ai-test"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "RUN_ID=$RUN_ID"

# Wait for ready (poll every 8s; give up after ~5 min and check sandbox-manager logs):
while :; do
  s=$(curl -s "http://localhost:8000/sandboxes" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); hit=[x for x in d if x.get('run_id')=='$RUN_ID']; print(hit[0]['status'] if hit else 'none')")
  echo "sandbox: $s"; [ "$s" = "ready" ] && break; sleep 8
done

SANDBOX_ID=$(curl -s "http://localhost:8000/sandboxes" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print([x for x in d if x.get('run_id')=='$RUN_ID'][0]['id'])")
SHORT=${SANDBOX_ID:0:8}
echo "SANDBOX_ID=$SANDBOX_ID SHORT=$SHORT"
```

**Pre-verify the container-routing assumptions** (these underpin the Iteration 2 cli fixes —
if any fail, the fix is wrong and the report must say so):

```bash
docker exec rvp-cli-$SHORT       which cartesi              # EXPECT a path (npm @cartesi/cli)
docker exec rvp-advancer-$SHORT  which cartesi-rollups-cli  # EXPECT a path (runtime image)
docker exec rvp-anvil-$SHORT     which cast                 # EXPECT a path (foundry image)
docker exec rvp-anvil-$SHORT     which forge                # EXPECT a path
```

## 3. End-to-end autonomous session

```bash
API_KEY=$(grep ANTHROPIC_API_KEY services/ai-agent/.env | cut -d= -f2)

SESSION_ID=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d "{\"mode\":\"autonomous\",\"sandbox_id\":\"$SANDBOX_ID\",\"run_id\":\"$RUN_ID\",
       \"goal\":\"Verification run. Do exactly these steps and then summarise: 1) call_jsonrpc cartesi_getChainId; 2) call_jsonrpc cartesi_getNodeVersion; 3) run_cli_command binary=cartesi-rollups-cli args='--help'; 4) run_cli_command binary=cartesi args='--version'; 5) run_cast_command command='block-number'; 6) read_logs component=advancer tail=20; 7) query_db sql='SELECT count(*) FROM tests.definitions WHERE ai_allowed'; 8) trigger_test jsonrpc-get-chain-id-v2; 9) trigger_test jsonrpc-list-applications-v2.\",
       \"anthropic_api_key\":\"$API_KEY\",\"model_id\":\"claude-opus-4-6\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "SESSION_ID=$SESSION_ID"
```

Watch it (this also tests the **live tool count** fix — `tool_calls_used` must increase
WHILE the session is still `active`, not only at the end):

```bash
while :; do
  R=$(curl -s "http://localhost:8000/sessions/$SESSION_ID")
  S=$(echo "$R" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], d['tool_calls_used'])")
  echo "status/tools: $S"; [ "${S%% *}" != "active" ] && break; sleep 8
done
```

Inspect the audit trail:

```bash
curl -s "http://localhost:8000/sessions/$SESSION_ID/tools" \
  | python3 -c "import sys,json; [print(f\"{t['status']:6} {t['tool_name']:22} {t['duration_ms']}ms\") for t in json.load(sys.stdin)]"
```

### Expected results

| Check | Expectation |
|---|---|
| `cartesi_getChainId` | result `0x7a69` (31337) |
| `cartesi_getNodeVersion` | `2.0.0-alpha.11` (or matching release) |
| `run_cli_command cartesi-rollups-cli --help` | `status=ok`, output `container` = `rvp-advancer-<short>` ← **Iteration 2 fix** |
| `run_cli_command cartesi --version` | `status=ok`, container = `rvp-cli-<short>` ← **Iteration 2 fix** |
| `run_cast_command block-number` | `status=ok`, numeric stdout, container = `rvp-anvil-<short>` ← **Iteration 2 fix** |
| `read_logs advancer` | `status=ok`, ≥1 line |
| `query_db` | `status=ok`, row count ≥ 10 (proves ai_reader LOGIN works) |
| `trigger_test` ×2 | `status='passed'`, each <5s — even while the post-provision bulk sweep is still draining `tests.commands` (the AI lane `tests.commands.ai` bypasses it; Iteration 3 F-1 fix) |
| Session terminal state | `completed` (NOT stuck `active` — that's the Iteration 2 failure-handling fix) |
| `tool_calls_used` mid-session | > 0 while still active |

Target: **all tool invocations `ok`**. The old baseline was 16/18 with the cli/cast tools
failing — those two must now pass.

## 4. Iteration-2-specific checks (do not skip)

### 4.1 User-message injection (was completely broken — silently dropped)

```bash
IS=$(curl -s -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d "{\"mode\":\"interactive\",\"sandbox_id\":\"$SANDBOX_ID\",\"goal\":\"Interactive verification.\",\"anthropic_api_key\":\"$API_KEY\",\"model_id\":\"claude-opus-4-6\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
sleep 5
curl -s -X POST http://localhost:8000/sessions/$IS/message \
  -H "Content-Type: application/json" \
  -d '{"message":"Call cartesi_getChainId and tell me the result, then stop."}'
sleep 30
curl -s "http://localhost:8000/sessions/$IS/tools" | python3 -c "import sys,json; print(len(json.load(sys.stdin)),'tool calls')"
# EXPECT: ≥1 tool call. 0 tool calls = message never reached the agent → check
# `docker compose logs ai-agent | grep -i user_message` and report.
# Cleanup: curl -s -X POST http://localhost:8000/sessions/$IS/cancel
```

### 4.2 AES-GCM actually on

```bash
docker compose logs orchestrator ai-agent | grep -i insecure
# EXPECT: no output. Any hit = base64 fallback still active → record the pip install lines
# from the build output in the report.
docker compose exec -T postgres psql -U rvp -d rvp -tc \
  "SELECT octet_length(anthropic_key_ciphertext), octet_length(anthropic_key_nonce) FROM ai.sessions ORDER BY created_at DESC LIMIT 1"
# EXPECT: nonce length 12; ciphertext length ≈ key length + 16 (GCM tag), and NOT
# decodable as base64 plaintext of the key.
```

### 4.3 Fresh-install ai_reader (only if you can afford a destructive check; otherwise static-verify)

Static check is fine: confirm `infra/postgres/init.sql` creates `ai_reader WITH LOGIN PASSWORD`
(not `NOLOGIN`) — destructive alternative is `docker compose down -v && up` and re-running
Phase 1.

### 4.4 read_logs expanded components

In a session goal (or reuse 4.1's session): ask for `read_logs component=claimer` and
`component=evm-reader`. EXPECT `ok` with the right container names.

### 4.5 Negative checks (guardrails still hold)

Ask the agent (or observe it refuses / errors cleanly):
- `query_db sql='DELETE FROM tests.results'` → tool must return "Only SELECT statements are allowed."
- `call_jsonrpc method='eth_blockNumber'` → must be rejected (non-`cartesi_` prefix).
- `trigger_test` with a slug whose `ai_allowed=false` → "not ai_allowed (whitelist)".
- `run_cli_command binary='rm'` → "not whitelisted".
All four must appear in `ai.tool_invocations` with `status='error'` or `'denied'` — never executed.

### 4.6 Dashboard (manual-ish, optional but valuable)

Open http://localhost:3000 → AI Sessions:
- "+ New Session" modal has API-key (password) input + model picker.
- Creating a session makes it appear in the list WITHOUT a page reload.
- Session detail page streams tokens and shows the tool-audit panel with expandable I/O.
- Tests page has the per-row "AI" toggle; flipping it updates `GET /tests?ai_allowed=true`.

## 5. Debugging guide

| Symptom | Where to look | Likely cause |
|---|---|---|
| `POST /sessions` → 500 | `docker compose logs orchestrator` | `AI_SESSION_KEY` unset/empty (encrypt_key raises) — check `docker compose exec orchestrator env \| grep AI_SESSION` |
| Session stays `active`, 0 tools | `docker compose logs ai-agent` | Agent crashed pre-loop (bad API key → Anthropic 401), or RabbitMQ `ai.requests` not consumed |
| Session ends `failed` | ai-agent logs, `session_failed` event | Unhandled exception in loop — stack trace is in the logs (this state is new in Iteration 2) |
| All sandbox-facing tools fail | `docker compose exec ai-agent env \| grep SANDBOX_HOST`; try `curl http://localhost:<node_port>/rpc` from host | Port lookup failed (sandbox row missing ports) or host-gateway broken |
| `run_cli_command` "not runnable in any candidate container" | the result's `attempts` array; `docker ps --filter name=rvp- --format '{{.Names}}'` | Sandbox containers gone / binary genuinely missing — re-check Phase 2 pre-verification |
| `query_db` auth failure | `docker compose exec -T postgres psql -U ai_reader -d rvp -c 'SELECT 1'` (password `ai_reader_changeme`) | Role lacks LOGIN (old DB volume — run migration 0012) |
| `trigger_test` `status=timeout` | `docker compose logs test-runner`; `SELECT status FROM tests.results WHERE id='<result_id>'` | test-runner down, or test genuinely slow — the row may complete after the deadline |
| No live updates in UI | `docker compose logs orchestrator \| grep -i redis`; browser devtools WS frames on `/ws` | Redis pub/sub chain broken |
| Message injection ignored | `docker compose logs ai-agent \| grep -i user_message` | Session not in `_message_queues` (already completed?) — check session status first |

Useful queries:

```sql
-- All sessions, newest first
SELECT id, mode, status, tool_call_count, total_tokens, created_at, closed_at
FROM ai.sessions ORDER BY created_at DESC LIMIT 10;

-- Tool failure summary for a session
SELECT tool_name, status, count(*), avg(duration_ms)::int AS avg_ms
FROM ai.tool_invocations WHERE session_id = '<SESSION_ID>'
GROUP BY 1,2 ORDER BY 1;
```

## 6. Cleanup

```bash
curl -s -X POST http://localhost:8000/runs/$RUN_ID/cancel
# Since Iteration 3: the sandbox-manager polls the cancel flag every 5s mid-run and
# tears the sandbox down via its normal teardown path. Verify within ~60s:
docker ps --filter "label=rvp.sandbox_id=$SANDBOX_ID" -q | wc -l   # EXPECT: 0
# If containers persist beyond ~2 min, that's a FAIL for the F-3 fix — report it
# (fallback cleanup: docker ps --filter "label=rvp.sandbox_id=$SANDBOX_ID" -q | xargs docker rm -f)
```

## 7. Handdown report — REQUIRED output

Write your report to `docs/ai-integration-test-report-<YYYY-MM-DD>.md`. Structure it exactly
like this so it can be diffed against future runs:

```markdown
# AI Integration Test Report — <date>

## Environment
- docker version, compose ps output (summarised), git rev / dirty files
- AI_SESSION_KEY set: yes/no · cryptography active: yes/no (evidence: log line)

## Phase results
| Phase | Check | Result | Evidence |
|---|---|---|---|
| 1 | catalog generated | PASS/FAIL | <log line / file head> |
| 2 | binary routing pre-check (4 binaries) | ... | <which command, which output> |
| 3 | autonomous session — per-tool table | ... | <audit table verbatim> |
| 4.1 | user-message injection | ... | |
| 4.2 | AES-GCM | ... | |
| 4.4 | read_logs components | ... | |
| 4.5 | negative checks (4) | ... | |
| 4.6 | dashboard | PASS/FAIL/SKIPPED | |

## Failures & diagnosis
For each failure: symptom → logs collected (exact excerpts, ≤20 lines each) →
hypothesis → what you tried → current status. Never paraphrase error messages; quote them.

## Regressions vs docs/ai-agent-integration.md §6 item 13
Old baseline was 16/18 tools OK. State the new ratio and name every non-ok tool.

## Open questions / suggested next fixes
Concrete, file-level suggestions (e.g. "cli.py:42 — route X to Y because Z").
```

Reporting rules:
- Quote real output; mark anything you inferred as INFERRED.
- A check you couldn't run is SKIPPED with the blocking reason — not PASS.
- Session IDs, run IDs, and sandbox IDs go in the report so a reviewer can re-query the DB.
- If you changed ANY code to make a test pass, list the diff in its own section — the
  reviewer must be able to distinguish "verified" from "fixed while verifying".

## 8. Cost note

Each autonomous session with the Phase 3 goal costs roughly 25-30k prompt tokens + tool
round-trips on the chosen model. Use `claude-haiku-4-5-20251001` for cheap re-runs of
plumbing checks; use `claude-opus-4-6` for the one definitive end-to-end run.
