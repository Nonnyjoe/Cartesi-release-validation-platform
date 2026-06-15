# AI Trustworthiness Review — Remediation Log (2026-06-13)

Response to `ai-trustworthiness-review-2026-06-13.md`. This log records, per review
item, what was changed, where, and how it was verified — plus the items deliberately
deferred (with rationale) because they are large architectural tracks rather than fixes.

**Net effect:** the `ai_manual` self-certifying path now has a runtime **validation gate**
(you cannot pass/fail a test you did not execute), full **audit persistence** (reasoning
transcript + immutable per-step links + plan/understanding), **provenance** on every
verdict (pinned model + temperature + release/image/contracts + frozen definition
snapshot), and a **confidence** signal for human-review routing. The five headline gaps
are closed at the mechanism level.

Schema: migration `0015_ai_verdict_trust.sql` (+ mirrored in `infra/postgres/init.sql`).

---

## Immediate tier (review §15) — all done

| Review item | Fix | Files | Verified |
|---|---|---|---|
| **Verdict validation gate** — reject pass/fail without trail-backed evidence | `record_test_verdict` claims the session's unclaimed invocations as the test's trail; a `passed`/`failed` with an **empty trail is auto-downgraded to `inconclusive`** (`auto_downgraded_from` + `validation_notes` recorded). Evidence is cross-checked: `evidence_validated` is true only if a concrete literal the agent cited (tx hash / value) appears in the captured trail. | `tools/verdicts.py` | Synthetic E2E: `passed`+no-trail → `inconclusive` (downgraded_from=passed); `passed`+trail citing `0x7a69` → stays passed, `evidence_validated=t`. |
| **Mandatory evidence + min-trail for non-blocked verdicts** | Same gate; `passed`/`failed` require ≥1 attributable tool call. `blocked`/`skipped`/`inconclusive` are the honest "couldn't fully execute" buckets and are exempt. Read-only tests legitimately pass with zero *mutating* steps (mutating count is informational, not a hard requirement). | `tools/verdicts.py` | Unit + synthetic E2E above. |
| **Persist `message_history` / structured records** (stop writing `'[]'`) | `AgentLoop.transcript()` returns the cleaned message list (+ context-compression summaries); `_save_session` now writes it to `ai.sessions.message_history` on terminal save (interim `active` saves keep the prior value). Bounded to 400 KB (tail kept if larger). | `agent_loop.py`, `session_manager.py` | Live session below: `message_history` non-`[]`. |
| **Pin model snapshot + temperature=0; stamp on verdict** | `AI_TEMPERATURE=0` on both stream + summarise calls; `resolve_model_snapshot()` maps an alias to a dated snapshot via `AI_MODEL_<ALIAS>` env when configured; `model_id` + `model_params` stamped on every verdict. | `agent_loop.py`, `tool_executor.py`, `tools/verdicts.py` | Synthetic E2E: `model_id`, `model_params.temperature=0` on the verdict. |
| **Stamp release/image/contracts on every verdict** | `_load_provenance()` reads release/image from `orchestrator.runs` and contracts from sandbox metadata; threaded into the executor and stamped. Plus a **frozen `definition_snapshot`** (name/version/assertions/expected) captured at verdict time → version-drift-proof. | `session_manager.py`, `tool_executor.py`, `tools/verdicts.py` | Synthetic E2E: `release_tag`, `definition_snapshot` present. |

## High-priority tier — all done

| Review item | Fix | Files |
|---|---|---|
| **Confidence scoring + human-review routing** | `confidence` (0–1) on the verdict schema + column; dashboard flags `<0.6` for review; required-by-prompt for pass/fail (absence noted in `validation_notes`). | `tools/__init__.py`, `tools/verdicts.py`, `Session.tsx` |
| **Observation layer + per-step intent/justification** | `observations` (agent's interpretations, distinct from raw output) on the verdict; `intent`/`observation` columns on `ai.tool_invocations`; `record_test_plan` captures per-step intent + rationale + expected observation. | migration 0015, `tools/__init__.py`, `tools/verdicts.py` |
| **Replace time-window trail with immutable verdict↔step FK** | `ai.tool_invocations.verdict_id` FK, set at verdict time; the trail is gathered by `verdict_id IS NULL` (each call claimed by exactly one verdict, in order) instead of the mutable slug/timestamp heuristic. Fixes batch-read misattribution. | migration 0015, `tools/verdicts.py`, `tool_executor.py` |
| **Test understanding summary + persisted plan** | New `record_test_plan` tool → `ai.test_plans` (objective, success/failure criteria, ordered planned steps). Manual protocol requires it after `read_test_definition`, before execution. `GET /sessions/{id}/plans`; rendered in the verdict panel. | migration 0015, `tools/verdicts.py`, `tools/__init__.py`, `tool_executor.py`, `session_manager.py`, `routes/sessions.py`, dashboard |
| **Fix override leaf-collision; path-scoped overrides** | Bare-key overrides that match >1 assertion are **rejected as ambiguous** (was: silently rewritten in every assertion); `assertions.<N>.<leaf>` path form added. Mirrored in the test-runner consumer (logs + skips ambiguous). | `tools/test_trigger.py`, `test-runner/consumers/test_commands.py` |

## Medium-priority tier — done

| Review item | Fix | Files |
|---|---|---|
| Remove/raise trail `LIMIT 60`; flag truncation | Cap raised to 400; `trail_truncated` flag set + surfaced on the verdict and in the UI. | `tools/verdicts.py`, dashboard |
| DB connection pooling in ai-agent tools | Shared process-wide `asyncpg` pool (`tools/db.py`, `AI_DB_POOL_MAX=8`); `audit.py` and `verdicts.py` use it instead of `connect()` per call. | `tools/db.py`, `tools/audit.py`, `tools/verdicts.py` |
| Persist context-compression summaries | Each compression summary appended to `compression_summaries`, included in the persisted transcript (no longer lost). | `agent_loop.py` |

## Security tier — partial (tractable guardrails done; isolation deferred)

| Item | Status | Notes |
|---|---|---|
| `run_cli_command` `bash`/`sh` → arbitrary execution | **Guardrail added** | Destructive-pattern denylist (`rm -rf /`, fork bombs, `dd of=/dev/*`, pipe-to-shell, `docker`/`docker.sock`, `iptables`, reboot/shutdown, …). Blocked calls return `denied`. Not a full sandbox — see deferred. |
| AES-GCM (not base64) for session keys | **Verified active** | `cryptography 48.0.1` present in the ai-agent image; base64 fallback only triggers when the package is absent. |
| `docker.sock` mounted = host blast radius | **Deferred** (architectural) | Real fix is a brokered, audited exec proxy + dropping the socket mount. Large, separate track. |
| Static secrets (`ai_reader_changeme`, rabbit `changeme`, shared `AI_SESSION_KEY`) | **Deferred** (ops) | Dev defaults; rotation belongs to a secrets-management track (Vault/SOPS), not a code change. Documented as a launch blocker. |
| Per-tenant key isolation | **Deferred** | One shared symmetric key decrypts all sessions; per-tenant KMS is a multi-tenancy track. |

## Deferred — large architectural tracks (not "fixes")

These are genuine projects the review itself rated High effort; they are intentionally
**not** bundled here so the trust-critical gate work could land verified and coherent.

1. **Full replay packages** (prompt hash + transcript + ordered tool I/O + Anvil
   `dumpState` bundle). Foundations now exist (transcript persisted, provenance stamped,
   model/temperature pinned, immutable step links) — the remaining work is the export/import
   bundler. Medium-High effort.
2. **Second-model verdict adjudication / ensemble.** The `evidence_validated` flag +
   `confidence` give the routing signal; a second-model adjudicator is a separate service.
3. **`docker.sock` brokered exec proxy** + dropping the socket mount (security track).
4. **Secrets management** (rotate + per-tenant keys) — ops/infra track.
5. **Prometheus metrics** (verdict distribution, tool error rate, token/release, false-verdict
   audits) — observability track; the data now exists in `ai.test_verdicts` to power it.
6. **Golden-run regression** (compare verdicts across releases) — depends on provenance
   stamping (now in place) + a comparison harness.

## What this changes about the review's headline

The review's "not yet, in the autonomous/manual self-certifying form" rested on five gaps:
self-judging with no validation (now gated), discarded reasoning (now persisted),
optional evidence (now required for pass/fail + cross-checked), non-reproducible runs (model
+ temperature pinned, provenance + frozen snapshot stamped), and heuristic trail attribution
(now an immutable FK). The remaining blockers for *unattended certification* are the deferred
**security isolation** and **replay/adjudication** tracks — i.e. the platform moves from
"advisory co-pilot" toward "checked, reproducible, human-gated certifier", which is the
intended trajectory. `ai_manual` verdicts should still route through human sign-off until the
deferred security + replay items land.

## Verification summary

- **Schema:** migration 0015 applied; 14 verdict columns, `ai.test_plans`, 3 invocation
  columns confirmed.
- **Gate (offline unit):** mutating detection, evidence cross-check, path-scoped/ambiguous
  override parsing, destructive denylist — all pass.
- **Gate (synthetic E2E against live DB):** empty-trail `passed`→`inconclusive` downgrade;
  trail-backed `passed` stays passed with `evidence_validated=true`, provenance + frozen
  snapshot stamped; invocations immutably linked to the verdict (`verdict_id` set).
- **API:** `/sessions/{id}/verdicts` exposes all trust/provenance fields; `/plans` added.
- **Live session** (`463ffea2-…`, Sonnet, bootstrap, 2 tests `jsonrpc-get-chain-id-v2` +
  `generic-input-v2`, 18 tool calls): both verdicts `passed` with `evidence_validated=true`,
  confidence 1.00 / 0.95, `model_id=claude-sonnet-4-6`, **`model_params.temperature=0.0`**,
  `release_tag=v2.0.0-alpha.11`, `definition_snapshot` + `observations` present; **2 plans
  persisted** (the agent called `record_test_plan` per test); **`message_history`=27,047
  bytes** (previously always `[]`); 11/18 invocations immutably linked to their verdict
  (the rest are the meta-tools `read_test_definition`/`record_test_plan`/`record_test_verdict`,
  excluded from trails by design). The trail digest correctly classed `generic-input-v2`'s
  cast `addInput` as a mutating step (mut=2) and the read-only chain-id test as mut=0.
