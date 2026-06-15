# AI Manual Execution Test Report — 2026-06-10

Verification of **Iteration 4 (AI manual test execution)** per `docs/ai-manual-execution-testing.md`,
with Iteration 3 re-verification per `docs/ai-agent-integration.md` §10. Live sessions ran on
`claude-sonnet-4-6`. Timestamps are UTC and span 2026-06-10 → 2026-06-11 (the definitive Phase 3
session ran at 2026-06-11 00:15 UTC).

## Environment

| Item | Value / Evidence |
|---|---|
| Compose services | All 10 up (`ai-agent`, `orchestrator`, `dashboard` rebuilt for Iteration 4 before testing) |
| Migration 0013 applied | YES — `ALTER TABLE / CREATE TABLE / CREATE INDEX ×2 / GRANT` all returned OK; `\d ai.test_verdicts` shows the verdict CHECK constraint `verdict = ANY (ARRAY['passed','failed','blocked','skipped','inconclusive'])`, FK to `ai.sessions` with `ON DELETE CASCADE`, and both indexes |
| `ai.sessions` new columns | `execution_mode`, `selected_tests` both present (information_schema query returned 2 rows) |
| `ai_reader` grants | `has_table_privilege('ai_reader','ai.test_verdicts','SELECT')` = `t`; `has_column_privilege('ai_reader','ai.sessions','execution_mode','SELECT')` = `t` |
| New tool registered | `record_test_verdict` present in `AGENT_TOOLS` (19 tools total) in the running ai-agent container |
| New API route | `GET /sessions/{session_id}/verdicts` present in the live orchestrator's OpenAPI spec; `SessionCreateIn` props include `execution_mode`, `selected_tests` |
| Sandbox metadata completeness | **Empty `{}`** on both sandboxes used (`5bf068dc`, `22d82a74`) — no `app_address`/portal addresses recorded. The manifest fallback text rendered as designed (see Phase 1). Reported per the guide: this is expected-but-notable, not a failure. |

### IDs for re-querying

| Resource | UUID |
|---|---|
| Phase 3 attempt 1 (no app deployed — see F-1) | session `ab4cbb37-438b-40d8-9951-fea8db774273`, sandbox `5bf068dc-a904-48a1-8356-1ea6bfdaef9e`, run `1bf751a1-9e56-445f-b2b3-8beaba40f796` |
| Phase 3 attempt 2 (**definitive**) | session `a0e0f741-a18c-4ca4-965b-7f293831b6eb`, sandbox `22d82a74-d3e3-41e3-9f2a-e46b50a00fe8`, run `d7ea6082-6039-43bc-af58-ed6df4681561` |
| Runner-mode regression | session `cf4dc77a-b42b-4114-b541-6517086f82f7` |
| Manually deployed app (attempt 2) | `0x22D2509e3bA26518C1C2f6Ea42D052Cd9E23B765` (echo-dapp name, authority `0xd693cc06fFcbe2b82d416A0D4B623b5D83B2E182`) |

### Environment interventions (disclosure — read before judging PASS criteria)

1. **App deployment**: fresh sandboxes ship with NO registered application (`cartesi_listApplications`
   → `total_count: 0`). For attempt 2 I deployed the snapshot myself before the session:
   `docker exec rvp-advancer-22d82a74 cartesi-rollups-cli deploy application echo-dapp /var/lib/cartesi-rollups-node/snapshot`
   → `deploying...success / registering...success`. Attempt 1 (no pre-deploy) shows what happens
   without this — see F-1.
2. **Goal hints**: attempt 2's goal text included the deployed app address, an InputBox address
   hint, and an explicit reminder to call `record_test_verdict` after each test. Notably the
   InputBox hint I gave was **wrong** (`0x59b22D57…`, the v1-era address) and the agent ignored
   it in favour of the correct one from project knowledge — see Agent quality assessment.
3. **No source code was modified during this verification.**

## Phase results

| Phase | Check | Result | Evidence |
|---|---|---|---|
| 0 | Build + migrate | PASS | Build exit 0; migration output `ALTER TABLE / CREATE TABLE / CREATE INDEX / CREATE INDEX / GRANT`; schema queries above |
| 1 | Sandbox provisioned, metadata noted | PASS (metadata empty) | Sandbox `22d82a74` ready in ~4 min; `SELECT jsonb_pretty(metadata)` → `{}`; manifest fallback rendered: *"deployed addresses: not recorded in sandbox metadata — discover them via `cartesi_listApplications` and the contracts-devnet project knowledge."* (779-char manifest, verified by direct render in the container) |
| 2 | ai_manual without sandbox_id → 422 | PASS | `{"detail":"autonomous mode requires sandbox_id"}` HTTP 422 |
| 2 | ai_manual without selected_tests → 422 | PASS | `{"detail":"ai_manual execution requires selected_tests (1+ slugs)"}` HTTP 422 |
| 2 | unknown slug → 422 | PASS | `{"detail":"Unknown test slugs: ['no-such-test']"}` HTTP 422 |
| 2 | ai_allowed=false slug → 422 | PASS | `{"detail":"Tests not ai_allowed: ['cli-cast-interop-v2']"}` HTTP 422 |
| 2 | Backwards compat: runner autonomous without goal → 422 | PASS | `{"detail":"autonomous mode requires a non-empty goal"}` HTTP 422 |
| 2 | Backwards compat: runner autonomous without sandbox → 422 | PASS | `{"detail":"autonomous mode requires sandbox_id"}` HTTP 422 |
| 3.1 | **No trigger_test** | PASS | Tool histogram for `a0e0f741`: `call_inspect 1, call_jsonrpc 7, get_node_state 2, read_logs 5, read_test_definition 3, record_test_verdict 3, report_finding 3, run_cast_command 3, run_cli_command 10, send_advance_input 1` — zero `trigger_test` rows, primitives + `read_test_definition` ×3 as required |
| 3.2 | **Active participation** (inputs differ from defaults, rationale present) | PASS | `generic-input-v2` `inputs_used`: `"payload": "0xc0ffee42babe1234", "rationale": "Distinctive hex pattern (coffee + babe + 1234) easily recognizable in hex outputs"` — not a definition example value, rationale stated. Also `jsonrpc-get-node-version-v2` inputs_used carries `"rationale": "No params needed for this method per the API spec"` |
| 3.3 | One verdict per selected test, ordered | PASS | 3 rows, slugs exactly `inspect-state` (00:17:21), `jsonrpc-get-node-version-v2` (00:17:37), `generic-input-v2` (00:19:00) — matches selection order |
| 3.4 | Evidence quality | PASS | Verdict evidence includes: tx hash `0x48fb31987149afdcaeed768dd3cebeccec0db87fbf838f6a1d6fc33b2b07b288` + `cast_send_status: 1 (success)` + block 7282; raw RPC response `{data: "2.0.0-alpha.11"}` + URL; HTTP bodies (`"HTTP method not supported"`, `"404 page not found"`); evm-reader log excerpt with the full `BlockOutOfRangeError` line |
| 3.5 | App awareness | PASS (strong) | See Agent quality assessment — the agent didn't just expect echo semantics, it detected the snapshot **isn't actually the echo dApp** |
| 3.6 | `GET /sessions/{id}/verdicts` ≡ DB | PASS | API returned the same 3 rows (slug/verdict/reasoning lengths 915/271/932 matched DB) |
| 3.7 | Session row persisted | PASS | `execution_mode='ai_manual'`, `selected_tests={inspect-state,jsonrpc-get-node-version-v2,generic-input-v2}`, status `completed`, 38 tool calls, 48,817 tokens |
| 3.8 | Limits scaled | PASS (with caveat) | Formula verified in-container: n=1→50, n=3→50, n=5→70 calls, n=10→130, n=20→200 (durations 600/600/900/1800/3600 s) — budget >50 for 5+ tests as required. Attempt 2 used 38/50 with no limit hit. **Caveat**: attempt 1 DID hit `Session limit hit: Tool call limit reached (50)` — but only because it spent its whole budget bootstrapping an app-less sandbox (F-1), not because the formula is wrong |
| 3-dash | Dashboard static wiring | PASS (static) | `Sessions.tsx:139-144` execution-mode select with `ai_manual` option revealing picker; picker fetches `testsApi.list({ ai_allowed: true })` (`Sessions.tsx:36`) with filter + "No ai_allowed test definitions found" empty state; submit blocked: `if (!form.sandbox_id) { setError('Manual execution requires a sandbox ID.') }` (`:106`); list tag `manual ({n} tests)` (`:257`); `Session.tsx:139` "manual execution" badge, `:225-279` Test verdicts panel with `VERDICT_COLORS` chips, expanders, pending-tests footer, `ai.verdict` WS handler (`:92`) + existing 4s poll; `api.ts:124` `sessionsApi.verdicts`; `types.ts` `AIExecutionMode`/`AIVerdict`/`TestVerdict`. Running bundle contains `ai_manual` (grep on the built `index-*.js` → 1) |
| 3-dash | Dashboard browser-visual | SKIPPED | Test agent has no browser. Static + API evidence above covers wiring but not pixels |
| 4 | Runner regression | PASS | Session `cf4dc77a` (no execution fields sent): `execution_mode='runner'`, `selected_tests=NULL`, 0 verdicts, tool histogram includes `trigger_test 1` — old behaviour intact, completed in ~70s |
| 4 | Blocked-verdict path (voucher test) | SKIPPED | No voucher test is whitelisted: `SELECT slug, ai_allowed FROM tests.definitions WHERE slug LIKE '%voucher%'` → all `f` (delegatecall-paid/targeted/basic, execute-voucher-finalized/latest). The guide conditions this check on "if whitelisted". Partial substitute: `generic-input-v2` hit a real broken-precondition scenario — see Agent quality assessment for the attribution analysis |
| 4 | record_test_verdict guardrails | PASS (partial) | Direct in-container calls: verdict `'maybe'` → `{'success': False, 'error': "verdict must be one of ('passed', 'failed', 'blocked', 'skipped', 'inconclusive'), got 'maybe'"}`; reasoning `'   '` → `{'success': False, 'error': 'reasoning must not be empty'}`. **Gap**: empty `definition_slug` is NOT validated — it falls through to the DB and surfaces as a raw FK-violation error string (no data corruption, but ugly; see Suggestions #4) |
| 5 | Cleanup | PASS | Runs `1bf751a1`, `d7ea6082`, `b12ab5b0` all cancelled (`{"status":"cancelled", ...}` ×3). Sandbox `a7a9e4bb` containers: 8 → 0 within ~30s of cancel with no manual `docker stop` (see Iteration 3 F-3 below) |

## Agent quality assessment

### Input creativity — good

For the one test where inputs genuinely matter (`generic-input-v2`), the agent chose
`0xc0ffee42babe1234` with the recorded rationale *"Distinctive hex pattern (coffee + babe + 1234)
easily recognizable in hex outputs"* — exactly the recognisable-payload behaviour the feature
wants, and the payload is visible in the cast send log evidence. For the trivially-parameterised
test it recorded *why* there was nothing to vary ("No params needed for this method per the API
spec") rather than inventing noise. One test of three offered real input freedom, so the sample
is thin, but what's there is right.

The strongest signal was unprompted: my goal text gave a **wrong** InputBox address
(`0x59b22D57…`), and the agent instead used `0x1b51e2992a2755ba4d6f7094032df91991a0cfac` from the
contracts-devnet project knowledge — and its transaction succeeded (`status: 1`). It followed its
prompt rule ("Never invent a contract address … consult project knowledge") over the operator's
incorrect hint.

### Judgment quality — verdicts faithful; one taxonomy quibble

- **`jsonrpc-get-node-version-v2` → passed.** Correct: *"returned `{data: "2.0.0-alpha.11"}`. The
  single assertion `expect_has_field: "data"` is satisfied."*
- **`inspect-state` → failed.** Faithful, and cross-validated: the agent reported *"GET request to
  /inspect/0x returns HTTP 404 … The v2.x advancer only accepts POST"* and noted POST inspect works
  (HTTP 200). I verified the definition really does assert `http_status` (GET, per
  `executors/http.py:45`) on `/inspect/0x` and `/healthz`, and **the test-runner itself has failed
  this test 3/3 times historically** — the agent's manual verdict agrees with the runner's record.
  Its meta-observation (*"This appears to be a v2.x behavior where the inspect server does not
  support GET"*) correctly identifies the definition as v1-era (release_introduced v1.4.0), not a
  node bug. No false positive/negative.
- **`generic-input-v2` → failed.** The diagnosis is excellent (see below), but the verdict label is
  arguable: the agent itself attributed the failure to the environment (*"the entire input pipeline
  is broken in this environment"*), which by the tool's own taxonomy ("blocked: a precondition or
  environment problem prevented execution") fits **blocked** better than **failed**. The step the
  agent controlled (InputBox.addInput) succeeded; indexing failed due to a pre-existing evm-reader
  fault. Reasoning content was accurate; only the enum choice is debatable.

### App awareness — strong, exceeded expectations

The pass criterion was "expects echo behaviour (notice payload == input payload)". The agent did
expect that — and then noticed reality deviated, filing this finding verbatim:

> **"Running dApp returns student-tracker response, not echo-dapp ready"** — *"The inspect endpoint
> returns a report payload that decodes to `{"route":"all","total_students":0,"students":[]}` rather
> than the expected `echo-dapp ready` string documented in test-app-behavior. The dApp running in
> the machine appears to be a student-tracker application, not the standard echo dApp. This
> discrepancy means any tests relying on the echo dApp semantics (notice payload == input payload,
> inspect returns 'echo-dapp ready') may produce unexpected results."*

It even ran `cast to-ascii` on the hex report payload to decode it. This proves the manifest +
`test-app-behavior.md` knowledge reached the prompt AND that the agent used it as a falsifiable
expectation rather than a script. It also exposes a real environment defect: the snapshot at
`/var/lib/cartesi-rollups-node/snapshot` is **not** the echo dApp the knowledge bundle describes
(see F-2).

### Bug-finding — found a real indexing fault with a precise mechanism

> **"EVM-reader stuck with BlockOutOfRangeError — inputs never indexed"** — *"`BlockOutOfRangeError:
> block height is {current} but requested was 120` … `transitionQuery(startBlock=120)` against an
> Anvil chain that is at block 7282+ … inputs submitted to the chain are never indexed —
> `cartesi_listInputs` returns empty even after a successful InputBox.addInput transaction. The
> application's `iinputbox_block` is `0x78` (= block 120)…"*

The agent connected the app's registered `iinputbox_block` to the evm-reader's stuck start block —
a non-obvious chain of evidence. Likely trigger: the app was deployed manually mid-sandbox-life
(my intervention) and the evm-reader cannot query state at the historical start block. Whether the
root cause is the node (should tolerate historical start blocks) or the environment (Anvil state
availability) needs a follow-up — but the agent's evidence makes that triage possible.

## Failures & diagnosis

### F-1: First manual session burned its whole budget bootstrapping (0 verdicts)

**Repro**: session `ab4cbb37` on sandbox `5bf068dc` — fresh sandbox, no app registered, metadata `{}`.
**Observed**: 50/50 tool calls consumed; ai-agent log `WARNING:ai-agent.loop:Session limit hit: Tool call limit reached (50)`;
`ai.test_verdicts` count 0; session status `completed` (not failed).
**Tool trace**: calls 1–32 were discovery/bootstrap — querying a nonexistent `orchestrator.sandboxes`
table, hunting addresses with `cast logs`, exploring `cartesi-rollups-cli` help pages, inspecting
the snapshot dir, then **deploying and registering the app itself** (`cartesi-rollups-cli deploy
application echo-dapp …`, succeeded on call 31). Only at call 33 did it reach
`read_test_definition` for the first test; calls 34–50 got partway into `inspect-state` before the
ceiling.
**Diagnosis**: not an agent defect — the environment contract is broken. The manifest says "discover
addresses via `cartesi_listApplications`", but on a fresh sandbox that returns an empty list; there
is nothing to discover, and the 12n+10 budget assumes execution, not deployment.
**Suspected fix location**: sandbox provisioning (sandbox-manager) should deploy/register the app
and record `app_address` (+ portals) into `sandbox.sandboxes.metadata`; alternatively
`_manual_plan_message()` should include a deploy-if-missing preamble and the budget should add a
bootstrap allowance. See Suggestions #1/#2.

### F-2: Deployed snapshot is not the echo dApp the knowledge bundle describes

**Repro**: POST inspect to the deployed app → report payload hex-decodes to
`{"route":"all","total_students":0,"students":[]}`.
**Observed**: contradicts `test-app-behavior.md` ("inspect handler returns `echo-dapp ready`").
**Impact**: every manual test that judges outcomes by echo semantics will mis-predict; the agent
flagged this itself (quoted above). `notice-generation-v2`-style tests would be judged against
wrong expectations.
**Suspected fix location**: the snapshot baked into the runtime image / `test-app` build — either
ship the real echo dApp snapshot or update `test-app-behavior.md` + manifest text to describe the
student-tracker app.

### F-3: evm-reader BlockOutOfRangeError after mid-life app registration

**Repro**: register an app on a sandbox whose Anvil chain is already thousands of blocks past the
InputBox deployment block, then submit an input.
**Observed**: `Error fetching inputs … transitionQuery(startBlock=120): failed to get number of
inputs at block 120: BlockOutOfRangeError: block height is 7282 but requested was 120` looping in
evm-reader; `cartesi_listInputs` stays empty despite tx `0x48fb3198…` status 1.
**Status**: open question — node bug vs Anvil state pruning. The agent's evidence (app
`iinputbox_block=0x78` ↔ stuck start block 120) localises it. Needs a dedicated repro on a sandbox
where the app is registered at provision time (which would also fix F-1).

### Minor: `record_test_verdict` accepts an empty `definition_slug`

Direct call with `definition_slug=''` reaches the DB and fails on the session FK (in the test I
used a fake session id; with a real session id an empty-slug row would insert). Validation should
mirror the verdict/reasoning checks. `tools/verdicts.py` (~line 40, before the INSERT).

## Iteration 3 re-verification

| Fix | Result | Evidence |
|---|---|---|
| F-1 AI priority lane (`tests.commands.ai`) | PASS | Queue exists with a consumer: `name=tests.commands.ai messages=0 consumers=1` (RabbitMQ API). Publisher routes there: `test_trigger.py:199-202` declares the queue durable and publishes with `routing_key="tests.commands.ai"`. Live-confirmed: the runner-regression session's `trigger_test` returned promptly (session `cf4dc77a` finished its whole 3-step goal in ~70s, vs the 90s timeouts seen pre-Iteration-3) |
| F-2 compose `:?` key guard | PASS (static) | `docker-compose.yml` contains `AI_SESSION_KEY: ${AI_SESSION_KEY:?AI_SESSION_KEY must be set in root .env — base64 of 32 random bytes, see .env.example}` in both services |
| F-3 cancel → sandbox teardown | **PASS (live)** | `POST /runs/b12ab5b0…/cancel` → containers for sandbox `a7a9e4bb`: 8 at t+0s, 8 at t+10s, 1 at t+20s, **0 at t+30s** — well inside the ~60s criterion, no manual `docker stop`. Code path: `sandbox_queue.py:277` `_is_run_cancelled` polled in the wait loop |

## Suggestions for Iteration 5

1. **Deploy + register the app at provision time and record addresses in
   `sandbox.sandboxes.metadata`** (`app_address`, portals, `iinputbox_block`). This fixes F-1
   (no bootstrap tax), gives the manifest real addresses instead of the fallback text, and avoids
   the F-3 historical-start-block condition entirely. Single highest-leverage change.
2. **Budget guard in `_manual_plan_message()`**: if `cartesi_listApplications` would be empty
   (no app in metadata), either fail fast with a clear session error or grant an explicit
   bootstrap allowance (+15 calls) and instruct the agent to deploy first. A session that
   ends `completed` with 0/3 verdicts and no warning is the worst current outcome (it also
   never wrote `blocked` verdicts for the unreached tests — the "never skip recording" prompt
   rule was unenforceable once the hard limit hit).
3. **Auto-record `blocked` verdicts for unreached tests** when the loop terminates on a
   limit: the session knows `selected_tests` minus recorded slugs (the dashboard already
   computes this "Pending" list) — write them as `blocked` with reasoning "tool budget
   exhausted before reaching this test" so the verdict table is always complete.
4. **Tighten `record_test_verdict` validation** (`tools/verdicts.py`): reject empty
   `definition_slug`; optionally warn (not reject) when the slug isn't in the session's
   `selected_tests`; consider nudging verdict choice — if reasoning attributes the failure to
   environment/preconditions, suggest `blocked` over `failed` (the taxonomy text already says
   this; the agent didn't follow it under pressure).
5. **Reconcile the snapshot vs `test-app-behavior.md`** (F-2): either bake the echo dApp into the
   sandbox snapshot or rewrite the behaviour doc + manifest paragraph for the student-tracker app.
   Until then every echo-semantics judgment is built on a false premise.
6. **Investigate the evm-reader BlockOutOfRangeError** (F-3 above) on a provision-time-registered
   app; if it persists, it is a real node bug worth a `tests.definitions` regression test.
7. **Playwright smoke for the dashboard** (carried over from the Iteration 2 report): the
   manual-mode modal/picker/verdict panel are still only statically verified.
