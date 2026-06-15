# AI Manual Test Execution (Iteration 4) — Test & Verification Guide

**Audience:** the Claude Code agent running on this machine with Docker access.
**Goal:** verify the Iteration 4 manual-execution feature end-to-end, then produce a
structured handdown report (`docs/ai-manual-execution-test-report-<date>.md`) for review.

Background reading (do this first):
- `docs/ai-agent-integration.md` §11 — exactly what Iteration 4 changed.
- `AI_TESTING_README.md` — environment prerequisites and debugging guide still apply.
- Also note §10: Iteration 3 (AI priority lane, compose `:?` key guard, cancel teardown)
  was **untested** at last handdown. If you have time, re-verify its three fixes too
  (see §10 "Re-test focus") and report them in a separate section.

You are testing the **changes**. The core question: can a dashboard-created AI session
manually execute selected tests — understanding each definition, choosing its own inputs,
driving the sandbox with primitive tools, and recording per-test verdicts?

---

## 0. Build & migrate

Iteration 4 touched: `ai-agent` (tools, session_manager, agent_loop, context),
`orchestrator` (routes/sessions.py), `dashboard` (Sessions/Session pages, api, types),
`infra/postgres` (init.sql + migration 0013).

```bash
docker compose build ai-agent orchestrator dashboard
docker compose up -d

# Existing DB volume only (fresh volumes get it from init.sql). Idempotent.
docker compose exec -T postgres psql -U rvp -d rvp < infra/postgres/migrations/0013_ai_manual_execution.sql

# Verify schema:
docker compose exec -T postgres psql -U rvp -d rvp -c "\d ai.test_verdicts"
docker compose exec -T postgres psql -U rvp -d rvp -c \
  "SELECT column_name FROM information_schema.columns WHERE table_schema='ai' AND table_name='sessions' AND column_name IN ('execution_mode','selected_tests');"
```

PASS = table exists with verdict CHECK constraint; both columns present.

## 1. Provision a sandbox

Same as `AI_TESTING_README.md` §2. Note the `sandbox_id` and confirm the sandbox row has
metadata (addresses are what feed the new manifest):

```bash
docker compose exec -T postgres psql -U rvp -d rvp -c \
  "SELECT id, metadata FROM sandbox.sandboxes ORDER BY provisioned_at DESC LIMIT 1;"
```

Record in the report whether `app_address` / portal addresses are present in metadata —
if absent, the manifest's fallback text should appear in the system prompt instead
(that's expected, not a failure, but report it).

## 2. API validation guardrails (no tokens consumed)

All against `POST /api/sessions`. Expect **422** for each:

```bash
# ai_manual without sandbox_id
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/sessions -H 'Content-Type: application/json' \
  -d '{"mode":"autonomous","execution_mode":"ai_manual","selected_tests":["ether-deposit-v2"],"anthropic_api_key":"sk-ant-xxxxxxxxxxxxxxxxx"}'

# ai_manual without selected_tests
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/sessions -H 'Content-Type: application/json' \
  -d '{"mode":"autonomous","execution_mode":"ai_manual","sandbox_id":"<SBX>","anthropic_api_key":"sk-ant-xxxxxxxxxxxxxxxxx"}'

# unknown slug
... -d '{"mode":"autonomous","execution_mode":"ai_manual","sandbox_id":"<SBX>","selected_tests":["no-such-test"],...}'

# slug that exists but ai_allowed=false (pick one: SELECT slug FROM tests.definitions WHERE ai_allowed=false LIMIT 1)
```

Also confirm a **runner-mode session with no execution fields at all** still validates the
same as before (backwards compat: autonomous still requires goal in runner mode).

## 3. End-to-end manual session (the main event)

Pick 2–3 cheap, fast tests that exercise different tool paths, e.g.:
- `inspect-valid-v2` (call_inspect / HTTP)
- `jsonrpc-get-node-version-v2` (call_jsonrpc)
- `ether-deposit-v2` (cast/portal + jsonrpc poll)

```bash
curl -s -X POST localhost:8000/sessions -H 'Content-Type: application/json' -d '{
  "mode": "autonomous",
  "execution_mode": "ai_manual",
  "sandbox_id": "<SBX>",
  "selected_tests": ["inspect-valid-v2", "jsonrpc-get-node-version-v2", "ether-deposit-v2"],
  "goal": "Choose distinctive payloads you can recognise in outputs.",
  "anthropic_api_key": "<REAL KEY>",
  "model_id": "claude-sonnet-4-6"
}'
```

Watch: `docker compose logs -f ai-agent`

### PASS criteria (check each, cite evidence in the report)

1. **No trigger_test**: `SELECT tool_name, count(*) FROM ai.tool_invocations WHERE session_id='<SID>' GROUP BY 1;`
   must show zero `trigger_test` rows and a mix of primitive tools + `read_test_definition`.
2. **Active participation**: for at least one test, the chosen input differs from the
   definition's default (e.g. a payload that isn't the example value) AND
   `record_test_verdict.inputs_used` explains the choice. This is the heart of the feature.
3. **One verdict per selected test**:
   `SELECT definition_slug, verdict FROM ai.test_verdicts WHERE session_id='<SID>' ORDER BY created_at;`
   → 3 rows, slugs match the selection, order roughly matches the plan.
4. **Evidence quality**: each verdict row has non-null reasoning referencing observed vs
   expected behaviour; evidence contains concrete artifacts (tx hash, RPC response, hex payload).
5. **App awareness**: the agent's reasoning (WS stream / message text in logs) shows it
   expects the echo behaviour (notice payload == input payload) — i.e. the manifest +
   test-app knowledge reached the prompt.
6. **GET /sessions/{id}/verdicts** returns the same rows as the DB query.
7. **Session row**: `SELECT execution_mode, selected_tests FROM ai.sessions WHERE id='<SID>';`
   persisted correctly.
8. **Limits scaled**: ai-agent logs should NOT show "Tool call limit reached (50)" for a
   3-test session unless the agent really used 46+ calls (budget = 12·3+10 = 50 → for 3
   tests the floor is 50; for 5+ tests confirm the budget is >50).

### Dashboard checks (browser or static)

- New Session modal: "Test execution" select present; choosing Manual reveals the picker;
  picker lists only ai_allowed definitions; filter works; submit blocked without sandbox/tests.
- Session page for the manual session: "manual execution" badge, Test verdicts panel fills
  live (or within the 4s poll), verdict rows expand to show reasoning/inputs/evidence,
  pending list shrinks as verdicts land.
- Sessions list shows "manual (3 tests)" under the mode badge.

## 4. Negative / behavioral checks

- **Runner regression**: create a normal runner-mode autonomous session and confirm the old
  behavior (trigger_test used, no verdicts expected, old prompt text).
- **Blocked verdict path**: include one test whose preconditions can't be met (e.g. a
  voucher test — the echo dApp produces no vouchers, definitions like
  `voucher-generation-v2` if whitelisted). Expect a `blocked`/`failed` verdict with
  reasoning that correctly attributes the cause to the dApp limitation, NOT a false node bug.
  Whether the agent gets this attribution right is a key quality signal — report verbatim.
- **record_test_verdict guardrails**: the tool rejects bad verdict values and empty
  reasoning (can be unit-checked by calling the function directly in the container:
  `docker compose exec ai-agent python3 -c "..."`).

## 5. Cleanup

Same as `AI_TESTING_README.md` §6.

## 6. Handdown report — REQUIRED output

Write `docs/ai-manual-execution-test-report-2026-06-<DD>.md`:

```markdown
# AI Manual Execution Test Report — <date>

## Environment
(compose ps summary, migration applied y/n, sandbox metadata completeness)

## Phase results
| Phase | Check | Result | Evidence |
(one row per numbered PASS criterion above + dashboard + negative checks)

## Agent quality assessment
- Input creativity: did the agent vary inputs meaningfully? Examples.
- Judgment quality: were verdicts/reasonings correct? Any false positives/negatives?
- App awareness: quotes showing it used the manifest/echo semantics.

## Failures & diagnosis
(repro, logs, suspected file/line)

## Iteration 3 re-verification (if performed)
(F-1 priority lane, F-2 key guard, F-3 cancel teardown)

## Suggestions for Iteration 5
```

Be specific with evidence (SQL output, log lines, session IDs). Do not mark a criterion
PASS without citing the artifact that proves it.
