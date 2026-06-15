# Cartesi RVP — AI Validation Platform Trustworthiness Review

**Date:** 2026-06-13
**Scope:** Whether the AI execution path can be trusted to validate Cartesi rollups-node
releases without human intervention.
**Reviewer roles:** Principal QA Architect / AI Systems Engineer / SRE / Platform Engineer /
Security Engineer / Release Engineering Lead / Reliability Engineer / Observability Engineer /
LLM Evaluation Specialist / Autonomous Agent Systems Reviewer.
**Method:** Source audit of the live `cartesi-rvp` tree (AI execution path read end-to-end:
`agent_loop.py`, `session_manager.py`, `tool_executor.py`, `tools/*`, prompt templates,
context assembler, `infra/postgres/init.sql`, migrations 0012–0014, test definitions).

> **Headline answer to the primary question — "Would I trust the AI execution path to
> participate in release certification?"**
>
> **Not yet, in the autonomous/manual self-certifying form.** The *runner* path (AI selects a
> whitelisted test; the deterministic test-runner executes and judges it) is trustworthy today
> as a release input. The *ai_manual* path (the agent executes steps **and** writes its own
> verdict) is **not** trustworthy for unattended certification: the model is simultaneously the
> executor and the judge, no layer validates a verdict against its own evidence, the agent's
> reasoning transcript is never persisted, evidence is not required for a `passed` verdict, and
> runs are not reproducible. It is a strong **advisory / triage co-pilot with mandatory human
> sign-off**, not an autonomous certifier.

---

## 1. Executive Summary

The platform is a genuinely impressive, well-iterated harness. Six documented iterations show
real engineering maturity: prompt caching, a dedicated AI test lane, an Anvil state cache that
cuts provisioning from ~3 min to ~45 s, per-session encrypted keys, auto-assembled execution
trails, and fail-safe "blocked" verdicts for un-reached tests. In a live session it found a
**real dApp bug** (student-tracker ether voucher encoded with `value=0x0`).

But the question is not "is this clever" — it is "can a broken release slip through unattended."
On that bar there are **five structural gaps** that each independently block autonomous
certification:

1. **The AI judges its own work with no validation layer** (Phase 6, critical). `record_test_verdict`
   stores whatever the model asserts. Nothing compares the verdict to the captured trail.
2. **The reasoning transcript is discarded** (Phase 4, high). `_save_session` always writes
   `message_history='[]'` and `tool_calls='[]'`. The chain-of-thought is streamed to the UI and
   then lost. Six months later you cannot reconstruct *why* the AI decided anything beyond a
   2–4 sentence `reasoning` string.
3. **Evidence is optional for a pass** (Phase 6, critical). The only hard requirement for a
   `passed` verdict is a non-empty `reasoning` string. A pass with zero tool calls and empty
   evidence is accepted.
4. **Runs are not reproducible** (Phase 7, critical). No model snapshot pin, no temperature
   control, no input seed, non-deterministic chain state, no release/image stamped on the
   verdict, no replay package.
5. **Trail attribution is heuristic** (Phase 5, high). Steps are attributed to a test by a
   *time window* ("everything since the last verdict"), capped at 60 rows, and retro-tagged.
   Pre-read exploration, interleaved tests, or long flows misattribute or silently truncate.

None of these are hard to fix; together they define the gap between "useful AI QA assistant"
and "trusted autonomous certifier."

---

## 2. Architecture Review

### 2.1 Service topology

| Service | Role |
|---|---|
| `orchestrator` | REST API + WebSocket hub. `POST /runs`, `POST /sessions` (encrypts key, persists, publishes), `GET /sessions/{id}/tools`, `/verdicts`. Broadcasts live events. |
| `ai-agent` | Consumes `ai.requests`. Runs the observe→reason→act loop (`AgentLoop`). Manual mode: executes + judges. Writes `ai.tool_invocations`, `ai.test_verdicts`, `ai.sessions`. |
| `test-runner` | Consumes `tests.commands` (bulk) **and** `tests.commands.ai` (priority lane). Deterministic executors produce `tests.results`. Applies AI parameter overrides. |
| `sandbox-manager` | Consumes `sandbox.queue`. Provisions per-run docker-compose stacks; Anvil state cache. |
| `dashboard` | React UI: Sessions, verdict/trail panels, Tests AI toggle. |
| `github-watcher`, `notifier` | PR ingestion + notifications. |
| `postgres` | Schemas: `orchestrator`, `tests`, `sandbox`, `ai`, `github`. |
| `redis` | Pub/sub `rvp:live` broadcast hub. |
| `rabbitmq` | Queues: `ai.requests`, `ai.results`, `tests.commands`, `tests.commands.ai`, `sandbox.queue`. |

### 2.2 Event / queue flow (AI session, manual mode)

```
Dashboard ──POST /sessions──> orchestrator
  encrypt(api_key) → ai.sessions row (status=starting)
  publish ai.requests {session_id, mode, execution_mode, selected_tests, sandbox_id|bootstrap}
        │
        ▼
ai-agent SessionRequestConsumer ── ai.requests ──> SessionManager.run_autonomous()
   [bootstrap?] poll sandbox.sandboxes until ready (relays run_logs as bootstrap_log)
   _load_sandbox_ports()  → ports + metadata (deployed addresses)
   build_system_prompt(manifest, project knowledge, skills summary)
   AgentLoop.run(manual_plan_message)
        loop:  Claude stream → tool_use → ToolExecutor.execute()
                                            ├─ record_invocation → ai.tool_invocations
                                            └─ tool effect (cast/jsonrpc/inspect/cli/db/logs)
               record_test_verdict → _assemble_trail() → ai.test_verdicts
        on end / crash / limit → _record_missing_verdicts() (blocked) → _save_session()
   events → publishers → redis rvp:live → orchestrator WS → dashboard
```

### 2.3 Lifecycles

- **Session:** `starting → active → (completed | failed | aborted)`. Crash path marks `failed`
  and emits `session_failed` (Iteration 2 fix). Cancel during bootstrap → `aborted`.
- **Run / Sandbox:** orchestrator dispatch → `sandbox.queue` → provision (cache hit/miss) →
  `ready`; AI-bootstrap runs tagged `metadata.ai_session=true` skip the bulk sweep and live
  until bound sessions leave `active` (grace 900 s).
- **Test (runner):** `tests.commands(.ai)` → executor → assertions → `tests.results` (deterministic).
- **Test (ai_manual):** `read_test_definition` → agent primitive tools → `record_test_verdict`
  → `ai.test_verdicts` (model-judged, **separate** from `tests.results`).

### 2.4 Key architectural observation

`ai.test_verdicts` is deliberately decoupled from `tests.results`. **There is currently no
roll-up that converts AI verdicts into a release decision** — the AI path is advisory by
construction today. That is the right default and the safety rail that makes the rest of this
review about *future* trust rather than *current* exposure.

---

## 3. AI Test Execution Review

### 3.1 Discovery
- Manual sessions do **not** discover tests; the operator picks `selected_tests` at creation;
  the orchestrator validates each slug exists and is `ai_allowed` (422 otherwise). Good — no
  accidental skip/duplicate from discovery.
- `_manual_plan_message` enriches slugs with phase+name and groups them; the agent chooses
  order. **Ordering correctness is delegated to the model** (prompt: "health first, stress
  last"). Not enforced; a poor order can pollute later results.
- **Skip risk:** low for *recording* (auto-blocked verdicts guarantee one row per selected
  test) but **non-zero for execution** — a `passed`/`blocked` row does not prove the steps ran.
- **Duplicate risk:** the agent could record two verdicts for one slug; only the matching-slug
  one closes `current_test_slug`. No uniqueness constraint on `(session_id, definition_slug)`.

### 3.2 Understanding
The agent *can* explain a test: `read_test_definition` returns the full parsed YAML +
Steps + Expected Behaviour, and the manual protocol instructs "study the assertions, identify
what each verifies." **But the understanding is never captured as an artifact** — there is no
"test understanding summary" persisted before execution. You cannot later verify the agent
understood the test; you only see the final verdict reasoning.

### 3.3 Planning
The prompt asks the agent to "state your chosen order before you start." This is **text only**
— streamed over WebSocket, never persisted (see Phase 4). There is **no structured plan phase**:
no recorded list of required tools, dependencies, required state, or order. The agent typically
begins calling tools immediately after a one-line order statement.

### 3.4 Input generation (critical)
Two regimes:
- **Runner mode:** `parameter_overrides` are merged into the assertion array **by leaf name**
  (`tools/test_trigger.py::_apply_overrides` and mirrored in `test-runner/consumers/test_commands.py`).
  Inputs are therefore derived from the test definition and are valid by construction. **Bug:**
  the merge rewrites the leaf in **every** assertion that has that key (e.g. a shared
  `expect_count`), and ignores nested/path forms (`assertions.0.payload`). Collisions can change
  semantics or mask a failing assertion.
- **Manual mode:** the agent free-forms inputs with primitive tools, guided by
  `test-app-behavior.md` ("proven command recipes"). `generate_payload` uses `os.urandom`
  (non-deterministic; no seed exposed in the tool schema). `inputs_used` is **self-reported and
  unvalidated**.

**Would a human QA engineer generate the same inputs?** Often yes for the documented recipes
(register → deposit → withdraw), because the grounding doc is good. For edge cases, no —
`generate_payload` random bytes against a JSON-only dApp produce a *reject*, which is correct
dApp behaviour but a poor probe of the node.

**Could input generation cause false passes?** Yes — a too-easy or wrong-surface input that the
dApp accepts trivially, judged "passed."
**Could it cause false fails?** Yes — random/malformed payloads rejected by the dApp, misread as
a node bug (the prompt's "judging hints" mitigate but do not enforce this).

---

## 4. AI Tester Quality Review (sampled)

No live DB was available to sample rows during this audit, so quality is assessed from the
**documented** representative session `bdcc4a8e` (Iteration 6) plus code-path analysis.

Session `bdcc4a8e` — 3 multi-tool tests, trails of 13 / 5 / 34 steps; ran the full voucher
L2→L1 journey and filed a real dApp bug.

| Dimension | Rating (1–10) | Basis |
|---|---|---|
| Understanding | 7 | Reads definitions; grounded by manifest + behaviour doc; correctly distinguished dApp-reject from node-bug. But understanding is not persisted/verifiable. |
| Planning | 4 | Order is stated in prose, not a structured/persisted plan; no dependency/state modelling. |
| Execution | 7 | Correctly drove register→deposit→withdraw→epoch→execute with primitive tools. |
| Evidence Collection | 5 | Auto-trail is a real strength, but capped/heuristic; reasoning transcript lost; evidence optional. |
| Verdict Accuracy | 5 | Plausibly accurate in the sampled case, but **unverifiable and self-graded** — no independent check, no confidence. |

**Caveat:** these ratings reflect *one favourable documented run*. With no validation layer, a
bad run is indistinguishable from a good one in the persisted record — which is itself the
finding.

---

## 5. Logging & Auditability Review (mandatory)

Reconstruction test: *an engineer investigates a failed release six months later.*

| Required | Present? | Evidence |
|---|---|---|
| Test ID / Name / Category / Priority | Partial | `definition_slug` on verdict + invocation; name/priority must be re-joined from `tests.definitions` (version drift not pinned). |
| Session / Run / Sandbox | Yes | `ai.sessions`, `verdict.sandbox_id`, `session.run_id`. |
| Test objective / expected behaviour | **No** | Not snapshotted onto the verdict; only retrievable from the current definition. |
| AI execution plan | **No** | Streamed text only; never persisted. |
| Per-step timestamp / tool / input / output | Yes | `ai.tool_invocations` (input ≤50 KB, output ≤200 KB, `duration_ms`, `created_at`, `status`). |
| Per-step **reason for tool** / **interpretation** | **No** | The agent's narration between calls is not stored. |
| Observations (distinct from raw output) | **No** | No observation layer; only raw tool outputs + the final reasoning string. |
| Verdict / evidence / reasoning | Partial | Verdict + reasoning + (optional) evidence + auto-trail present. **No confidence score** (column does not exist). |

**Could a human reconstruct every decision?** **No.** They can reconstruct *what tools ran with
what I/O* (good), but not *why each was chosen* or *what the agent believed at each step* — the
reasoning is gone.
**Could a human reproduce the exact execution?** **No** (Phase 7).
**Missing:** plan artifact, test-definition snapshot, per-step intent/interpretation,
observation layer, confidence, model snapshot + params, release/image pin, and (above all) the
reasoning transcript that the schema already has a column for (`message_history`) but never
fills.

---

## 6. Execution Trail Review

`ai.tool_invocations` + auto-assembled `evidence.execution_trail` (`tools/verdicts.py`).

**Strengths:** every call persisted with full I/O and timing; the trail digests per-step
surface + input + output and deep-links each `invocation_id`; the agent is told not to re-paste
output (token-efficient and reduces transcription error).

**Gaps:**
1. **Time-window attribution** (`_assemble_trail`): trail = invocations since the previous
   `record_test_verdict`. Breaks on pre-read exploration, batch-reading multiple definitions,
   or any interleaving — calls land in the wrong verdict and are **retro-tagged** to it,
   corrupting the audit panel too.
2. **`LIMIT 60`** — flows longer than 60 steps are silently truncated in the trail.
3. **No link table** between a verdict and its invocations; the join is by mutable
   `definition_slug` + timestamp, not an immutable FK.
4. **Inputs/outputs visible** per step, but **observations** (what the agent concluded) are not
   in the trail — only raw I/O.

### Proposed ideal schema (additive)

```sql
-- Persist the conversation/reasoning (column already exists, just stop writing '[]')
UPDATE: ai.sessions.message_history := full transcript (assistant text + tool blocks)

-- Structured plan, one row per session
CREATE TABLE ai.test_plans (
  id UUID PK, session_id UUID, definition_slug TEXT,
  objective TEXT, expected_behaviour TEXT,
  planned_steps JSONB,         -- [{intent, tool, input_rationale, expected_observation}]
  required_tools TEXT[], created_at TIMESTAMPTZ);

-- Immutable per-step record (replaces heuristic time-window attribution)
CREATE TABLE ai.execution_steps (
  id UUID PK, session_id UUID, verdict_id UUID NULL,  -- FK set at verdict time
  definition_slug TEXT, step_no INT,
  intent TEXT, tool_name TEXT, tool_input JSONB,
  tool_output_ref UUID,        -- FK -> ai.tool_invocations
  observation TEXT,            -- agent's interpretation (the missing layer)
  created_at TIMESTAMPTZ);

ALTER TABLE ai.test_verdicts
  ADD confidence NUMERIC(3,2) CHECK (confidence BETWEEN 0 AND 1),
  ADD definition_snapshot JSONB,     -- frozen objective/expected/assertions
  ADD model_id TEXT, ADD model_params JSONB,
  ADD release_tag TEXT, ADD image_tag TEXT, ADD contracts_version TEXT,
  ADD evidence_validated BOOLEAN DEFAULT false,
  ADD UNIQUE (session_id, definition_slug);
```

---

## 7. False Pass / False Fail Analysis (critical)

| Risk | Mode | Mechanism | Severity | Likelihood | Mitigation |
|---|---|---|---|---|---|
| **Self-certified false pass** | manual | Agent writes `passed` with thin/empty evidence; nothing validates it | **Critical** | Med | Verdict-review layer: reject `passed`/`failed` unless trail has ≥1 mutating step + evidence references trail values; require confidence. |
| **Pass with no execution** | manual | `record_test_verdict` only requires non-empty `reasoning`; trail may be empty | **Critical** | Med | Enforce min-trail for non-blocked verdicts; auto-downgrade evidence-less pass → `inconclusive`. |
| **Hallucinated success** | manual | Reasoning cites an observation the trail does not contain | High | Med | Cross-check evidence/claims against trail values programmatically. |
| **Hallucinated failure** | manual | dApp-by-design reject (non-JSON payload) read as node bug | High | Med-High | Already partly mitigated by judging hints; add a "expected-reject" assertion library. |
| **Override-collision false pass** | runner | Leaf-name override rewrites a shared key in every assertion, weakening the check | Medium | Low-Med | Path-scoped overrides (`assertions.N.key`); reject ambiguous leaf names. |
| **Misattributed evidence** | manual | Time-window trail attaches another test's steps | High | Med | Immutable per-step FK (Phase 6 schema). |
| **Trail truncation** | manual | `LIMIT 60` drops decisive late steps from evidence | Medium | Low-Med | Remove cap or paginate; flag truncation on the verdict. |
| **Model/version drift false verdict** | both | Unpinned model alias changes behaviour release-to-release | High | Med | Pin model snapshot + temperature=0; record both. |

---

## 8. Reproducibility Review (critical)

**Can another engineer replay the same test, same release, same inputs, and get a comparable
result? No.**

Non-reproducibility sources:
1. **Model:** `claude-opus-4-6` is an alias (not a dated snapshot); no temperature/seed pinned
   (`agent_loop.py` sets neither). LLM output is non-deterministic across runs and over time.
2. **Inputs:** `generate_payload` uses `os.urandom`; the seed parameter exists in the function
   but is **not** exposed in the tool schema, so the agent can't pin it.
3. **Environment:** chain state is non-deterministic (block timestamps, gas, nonces); the
   Anvil state-cache key is by contracts-version but live tx ordering varies.
4. **Provenance not captured on the verdict:** no `release_tag`, `image_tag`,
   `contracts_version`, model id, or model params stored alongside the verdict.
5. **No replay package:** there is no export bundle (prompt + tool sequence + inputs + chain
   snapshot + model config).

**What's needed for reproducibility:** pinned model snapshot + temperature=0; seeded payload
generation surfaced to the agent; per-verdict provenance (release/image/contracts/model/params);
an exportable replay bundle (system prompt hash, message transcript, ordered tool I/O, Anvil
`dumpState`); and deterministic input recipes for `ai_allowed` tests.

---

## 9. Test Coverage Review

15 of ~240 definitions are `ai_allowed`, heavily weighted to **read-only JSON-RPC** queries
(`jsonrpc-get-chain-id`, `list-applications`, `list-inputs/outputs/reports/epochs`,
`get-node-version`, `processed-input-count`) plus a few input/inspect/notice tests.

| Suitability | Tests | Rationale |
|---|---|---|
| **Good for AI (read-only, low blast radius)** | the `jsonrpc-*` read methods, `inspect-state`, `graphql-inputs-query` | Idempotent, easy to verify, deterministic expected shapes. |
| **AI-with-care (state-changing but recipe-grounded)** | `generic-input`, `notice-generation`, voucher/portal flows | Meaningful but need deterministic inputs + evidence enforcement. |
| **Should stay deterministic (runner only)** | consensus/quorum, determinism-identical-inputs, security (cpu-cycle-limit, reentrancy), performance/latency, chaos hard-kill | Pass/fail must be a coded assertion, not a model judgment. |
| **Never AI-driven for certification** | anything whose verdict gates a release sign-off | Until a validation layer exists. |

**Recommendations:** keep read-only JSON-RPC as the AI exploration surface; promote more tests
to `ai_allowed` **only in runner mode**; never let `ai_manual` verdicts on determinism/security/
consensus/performance tests count toward certification.

---

## 10. AI Architecture Review

**Tooling:** 20 tools + 2 chaos tools, mode-filtered (manual drops `trigger_test`; managed-env
drops provision/teardown) — good least-privilege-by-prompt. `query_db` is SELECT-only with a 5 s
timeout / 200-row cap (good). **`run_cli_command` whitelists `bash`/`sh`** → effectively
arbitrary command execution inside sandbox containers, and the agent reaches the Docker daemon
via the **mounted `/var/run/docker.sock`** (see Security).

**Prompt design:** layered (persona + rules → project knowledge → skills summary → release
context), cache-friendly (stable prefix + moving breakpoint). Manual protocol is explicit and
good. Weakness: protocol compliance (plan, evidence, one-verdict-per-test) is *requested*, not
*enforced* by the runtime.

**Context management / compression:** at 80 % window, `_compress_context` asks the model to
summarise older turns and **replaces them** — irreversible mid-session information loss, and the
summary itself is not persisted. Risk: a decisive early observation is summarised away before
the verdict.

**Knowledge injection:** strong (per-sandbox manifest with real addresses; `test-app-behavior.md`
recipes; on-demand `lookup_skill`). This is the platform's best feature and the reason verdicts
are as good as they are.

**Tool routing:** `run_cli_command` auto-routes binaries to the right container — robust.

**Risks:** prompt fragility (behaviour hinges on the model honouring a long protocol);
tool-misuse via `bash`; context loss via compression; scaling — one `asyncpg.connect()` **per
tool call and per verdict** (no pooling) will not scale to many concurrent sessions.

---

## 11. Observability Review

| Question an engineer must answer | Answerable today? |
|---|---|
| Why did a test fail? | Partially — verdict reasoning (2–4 sentences) + trail I/O; not the step-by-step interpretation. |
| Why did the AI choose an input? | **No** — `inputs_used` rationale is optional/free-form; no enforced justification. |
| Why did the AI reach its verdict? | Partially — short reasoning only; no confidence, no evidence validation. |
| Why was a tool called? | **No** — intent/reason-for-tool is not recorded. |
| Why did a session terminate? | Yes — `limit_reached`/`session_failed`/`aborted` events + status. |

**Missing telemetry:** per-step intent, input justification, observation layer, confidence,
plan, model/version/params, and any metrics (no Prometheus counters for verdict
distribution, tool error rates, false-verdict audits, token spend per release).

---

## 12. Suggested Improvements — impact / priority assessment

| Improvement | Verdict | Impact | Effort | Priority |
|---|---|---|---|---|
| **Explicit planning phase (persisted)** | **Approve** | High (auditability + understanding proof) | Med | High |
| **Structured step records (intent/action/input/output/observation)** | **Approve (strongly)** | High (replaces heuristic trail) | Med | **Immediate** |
| **Confidence scoring** | **Approve** | Med-High (lets a gate threshold + route low-confidence to humans) | Low | High |
| **Evidence requirements before pass/fail** | **Approve (strongly)** | Critical (kills empty-evidence pass) | Low | **Immediate** |
| **Replay packages** | **Approve** | High (reproducibility) | High | Medium |
| **Input-generation justification** | **Approve** | Med (false-pass/fail triage) | Low | High |
| **Observation layer (separate from raw output)** | **Approve** | High (the core missing audit artifact) | Med | High |
| **Test understanding summary** | **Approve** | Med | Low | High |
| **Verdict review layer (validate evidence before verdict)** | **Approve (strongly)** | Critical (the single highest-ROI fix) | Med | **Immediate** |

No proposed improvement should be rejected; the two that matter most are the **verdict review
layer** and **mandatory evidence** — they directly convert "self-graded" into "checked."

---

## 13. Ideal AI Test Execution Model

```
1. Load Test           read_test_definition → snapshot objective/expected/assertions onto the run
2. Understand Test     emit + persist a Test Understanding Summary (objective, success, failure)
3. Generate Plan       persist ai.test_plans: ordered steps {intent, tool, input_rationale,
                       expected_observation, required_state}
4. Generate Inputs     seeded/deterministic where possible; persist inputs_used + justification
5. Execute Steps       primitive tools; one ai.execution_steps row per step (FK to invocation)
6. Record Observations observation layer: agent's interpretation per step (≠ raw output)
7. Validate Assertions assertion-by-assertion expected vs observed, each linked to evidence
8. Generate Evidence   evidence must reference values present in the trail (programmatic check)
9. Produce Verdict     verdict + confidence; VALIDATION GATE: reject pass/fail lacking
                       trail-backed evidence → auto-downgrade to inconclusive
10. Persist Audit Trail message_history (transcript) + plan + steps + observations + verdict +
                       provenance (model snapshot, params, release/image/contracts) + replay bundle
```

Schema deltas in §6. The decisive addition is step 9's **validation gate** and step 6's
**observation layer**.

---

## 14. Launch Readiness Scorecard (1–10)

| Dimension | Score | Notes |
|---|---|---|
| Reliability | 6 | Retries, fail-safe blocked verdicts, crash→failed; but flaky provisioning, per-call DB connects, mid-stream model drops. |
| Trustworthiness | **3** | Self-judging with no validation; evidence optional. |
| Auditability | **4** | Tool I/O persisted well; reasoning transcript discarded; trail heuristic. |
| Reproducibility | **2** | Non-deterministic model/inputs/chain; no provenance; no replay. |
| AI Quality | 6 | Well-grounded; found a real bug; but unverified and single-run evidence. |
| Test Quality | 6 | Solid definitions; only 15 `ai_allowed`, mostly read-only. |
| Platform Quality | 6 | Mature harness; security hardening + connection pooling needed. |
| Operational Readiness | 4 | No metrics/alerting on verdict quality; shared static secrets. |

---

## 15. Priority Roadmap

### Immediate (must fix before trusting AI execution for certification)
| Item | Impact | Effort | Risk if skipped |
|---|---|---|---|
| **Verdict validation gate** — reject `passed`/`failed` without trail-backed evidence; auto-downgrade to `inconclusive` | Critical | Med | Self-certified false pass ships a broken release |
| **Mandatory evidence + min-trail for non-blocked verdicts** | Critical | Low | Empty-evidence pass |
| **Persist `message_history` / structured step records** (stop writing `'[]'`) | Critical (audit) | Low-Med | Unauditable verdicts |
| **Pin model snapshot + temperature=0; stamp on verdict** | High | Low | Non-reproducible, drifting verdicts |
| **Stamp release/image/contracts on every verdict** | High | Low | Cannot tie verdict to artifact |

### High Priority
| Item | Impact | Effort |
|---|---|---|
| Confidence scoring + threshold routing to humans | High | Low |
| Observation layer + per-step intent / input justification | High | Med |
| Replace time-window trail with immutable verdict↔step FK | High | Med |
| Test understanding summary + persisted plan | Med-High | Med |
| Fix override leaf-collision; add path-scoped overrides | Med | Low |

### Medium Priority
| Item | Impact | Effort |
|---|---|---|
| Replay packages (prompt hash + transcript + tool I/O + Anvil dumpState) | High | High |
| Remove/raise trail `LIMIT 60`; flag truncation | Med | Low |
| DB connection pooling in ai-agent tools | Med | Low |
| Metrics: verdict distribution, tool error rate, token/release | Med | Med |
| Persist context-compression summaries | Med | Low |

### Future Enhancements
| Item | Impact | Effort |
|---|---|---|
| Second-model verdict adjudication / ensemble | High | High |
| Golden-run regression (compare verdicts across releases) | High | Med |
| Promote more tests to `ai_allowed` (runner mode only) | Med | Low |
| Enable chaos mode behind a flag with evidence gates | Med | Med |

### Security (parallel track — not optional for production)
- `docker.sock` mounted into ai-agent = host-level blast radius; isolate via a brokered, audited
  exec proxy.
- `run_cli_command` allows `bash`/`sh` → arbitrary execution; constrain to an explicit command
  allow-list.
- Replace static secrets (`ai_reader_changeme`, rabbit `changeme`, shared `AI_SESSION_KEY`);
  ensure `cryptography` is installed so keys are AES-GCM, never base64.
- Per-tenant key isolation (currently one shared symmetric key decrypts all sessions).

---

## 16. AI Architecture Risks (consolidated)

- **Tool misuse:** `bash`/`sh` + `docker.sock` → arbitrary host-adjacent actions.
- **Context loss:** lossy mid-session compression discards potentially decisive observations.
- **Prompt fragility:** correctness depends on the model honouring a long, unenforced protocol.
- **Scaling:** new asyncpg connection per call/verdict; no pooling.

---

## 17. Final Verdict

**Can the AI tester be trusted?** As an **advisory / triage co-pilot, yes** — it is well
grounded, found a real bug, and its runner-mode path produces deterministic results. As an
**autonomous self-certifying judge, no** — it grades its own work with no validation layer.

**Can release certification rely on it?** **Not unattended, today.** The runner path (AI picks
test → deterministic executor judges) can be a *certification input* now. The ai_manual path
must not gate a release until the verdict validation gate, mandatory evidence, and reasoning
persistence exist.

**Largest risks:** (1) self-certified false pass with thin/empty evidence; (2) lost reasoning
transcript → unauditable; (3) non-reproducible runs; (4) heuristic trail misattribution;
(5) model drift from an unpinned alias.

**Highest-ROI improvements:** verdict validation gate + mandatory evidence (low effort, kills the
critical false-pass class), then persist the transcript/step records, then pin the model and
stamp provenance.

**Logging missing:** plan, test-definition snapshot, per-step intent/observation, confidence,
model snapshot+params, release/image/contracts provenance, and the reasoning transcript (column
exists, never written).

**Evidence missing:** programmatic link between verdict claims and trail facts; evidence is not
required and not validated.

**What prevents reproducibility:** unpinned model + no temperature, unseeded inputs,
non-deterministic chain, no provenance on the verdict, no replay bundle.

**What would make it enterprise-grade:** a verdict-review gate, full audit persistence
(transcript + structured steps + observations + provenance), reproducible/seeded execution with
replay packages, confidence-thresholded human-in-the-loop routing, second-model adjudication,
real metrics/alerting on verdict quality, and the security hardening above.

**Must fix before production adoption (certification):** verdict validation gate; mandatory
evidence + min-trail; persist `message_history` + structured steps; pin model + temperature;
stamp release/image/contracts on verdicts; isolate `docker.sock`/`bash` and rotate static
secrets.
