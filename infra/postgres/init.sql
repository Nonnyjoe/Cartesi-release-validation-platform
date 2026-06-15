-- ============================================================
--  Cartesi RVP — PostgreSQL Init Script
--  Single instance, per-service schemas.
--  Runs once on first boot via docker-entrypoint-initdb.d/
-- ============================================================

-- ─────────────────────────────────────────────────────────────
--  1. SCHEMAS
-- ─────────────────────────────────────────────────────────────

CREATE SCHEMA IF NOT EXISTS orchestrator;
CREATE SCHEMA IF NOT EXISTS sandbox;
CREATE SCHEMA IF NOT EXISTS tests;
CREATE SCHEMA IF NOT EXISTS ai;
CREATE SCHEMA IF NOT EXISTS github;
CREATE SCHEMA IF NOT EXISTS notifications;


-- ─────────────────────────────────────────────────────────────
--  2. ROLES (one per service, scoped to their schema only)
-- ─────────────────────────────────────────────────────────────

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rvp_orchestrator') THEN
    CREATE ROLE rvp_orchestrator LOGIN PASSWORD 'changeme_orc';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rvp_sandbox') THEN
    CREATE ROLE rvp_sandbox LOGIN PASSWORD 'changeme_sbx';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rvp_tests') THEN
    CREATE ROLE rvp_tests LOGIN PASSWORD 'changeme_tst';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rvp_ai') THEN
    CREATE ROLE rvp_ai LOGIN PASSWORD 'changeme_ai';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rvp_github') THEN
    CREATE ROLE rvp_github LOGIN PASSWORD 'changeme_gh';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rvp_notify') THEN
    CREATE ROLE rvp_notify LOGIN PASSWORD 'changeme_ntf';
  END IF;
END;
$$;

-- Grant schema ownership / usage
GRANT USAGE ON SCHEMA orchestrator TO rvp_orchestrator;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA orchestrator TO rvp_orchestrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA orchestrator GRANT ALL ON TABLES TO rvp_orchestrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA orchestrator GRANT USAGE, SELECT ON SEQUENCES TO rvp_orchestrator;

GRANT USAGE ON SCHEMA sandbox TO rvp_sandbox;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA sandbox TO rvp_sandbox;
ALTER DEFAULT PRIVILEGES IN SCHEMA sandbox GRANT ALL ON TABLES TO rvp_sandbox;
ALTER DEFAULT PRIVILEGES IN SCHEMA sandbox GRANT USAGE, SELECT ON SEQUENCES TO rvp_sandbox;

GRANT USAGE ON SCHEMA tests TO rvp_tests;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA tests TO rvp_tests;
ALTER DEFAULT PRIVILEGES IN SCHEMA tests GRANT ALL ON TABLES TO rvp_tests;
ALTER DEFAULT PRIVILEGES IN SCHEMA tests GRANT USAGE, SELECT ON SEQUENCES TO rvp_tests;

GRANT USAGE ON SCHEMA ai TO rvp_ai;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ai TO rvp_ai;
ALTER DEFAULT PRIVILEGES IN SCHEMA ai GRANT ALL ON TABLES TO rvp_ai;
ALTER DEFAULT PRIVILEGES IN SCHEMA ai GRANT USAGE, SELECT ON SEQUENCES TO rvp_ai;

GRANT USAGE ON SCHEMA github TO rvp_github;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA github TO rvp_github;
ALTER DEFAULT PRIVILEGES IN SCHEMA github GRANT ALL ON TABLES TO rvp_github;
ALTER DEFAULT PRIVILEGES IN SCHEMA github GRANT USAGE, SELECT ON SEQUENCES TO rvp_github;

GRANT USAGE ON SCHEMA notifications TO rvp_notify;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA notifications TO rvp_notify;
ALTER DEFAULT PRIVILEGES IN SCHEMA notifications GRANT ALL ON TABLES TO rvp_notify;
ALTER DEFAULT PRIVILEGES IN SCHEMA notifications GRANT USAGE, SELECT ON SEQUENCES TO rvp_notify;

-- Cross-schema: orchestrator gets read-only on tests.results
GRANT USAGE ON SCHEMA tests TO rvp_orchestrator;
GRANT SELECT ON ALL TABLES IN SCHEMA tests TO rvp_orchestrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA tests GRANT SELECT ON TABLES TO rvp_orchestrator;


-- ─────────────────────────────────────────────────────────────
--  3. SHARED ENUM TYPES
-- ─────────────────────────────────────────────────────────────

CREATE TYPE run_status AS ENUM (
  'queued', 'provisioning', 'running', 'completed', 'failed', 'warning', 'cancelled'
);

CREATE TYPE sandbox_status AS ENUM (
  'requested', 'queued', 'provisioning', 'ready', 'running', 'teardown', 'closed', 'failed'
);

CREATE TYPE test_status AS ENUM (
  'pending', 'running', 'passed', 'failed', 'error', 'skipped', 'timeout'
);

CREATE TYPE ai_mode AS ENUM (
  'autonomous', 'collaborative', 'interactive'
);

CREATE TYPE ai_session_status AS ENUM (
  'starting', 'active', 'paused', 'completed', 'failed', 'aborted'
);

CREATE TYPE triggered_by_type AS ENUM (
  'github_release', 'user', 'scheduled'
);

CREATE TYPE test_priority AS ENUM (
  'low', 'medium', 'high', 'critical'
);

CREATE TYPE notification_channel AS ENUM (
  'discord', 'dashboard'
);

CREATE TYPE notification_status AS ENUM (
  'pending', 'sent', 'failed'
);


-- ─────────────────────────────────────────────────────────────
--  4. ORCHESTRATOR SCHEMA
-- ─────────────────────────────────────────────────────────────

CREATE TABLE orchestrator.runs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  release_tag       TEXT NOT NULL,
  image_tag         TEXT NOT NULL,
  suite_ids         UUID[],
  status            run_status NOT NULL DEFAULT 'queued',
  priority          SMALLINT NOT NULL DEFAULT 5,
  triggered_by      triggered_by_type NOT NULL,
  triggered_by_user TEXT,
  queued_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at        TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  pass_rate         NUMERIC(5, 2),
  report            JSONB,
  metadata          JSONB DEFAULT '{}'
);

CREATE INDEX idx_runs_status ON orchestrator.runs (status);
CREATE INDEX idx_runs_release_tag ON orchestrator.runs (release_tag);
CREATE INDEX idx_runs_queued_at ON orchestrator.runs (queued_at DESC);

CREATE TABLE orchestrator.run_events (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id     UUID NOT NULL REFERENCES orchestrator.runs (id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  payload    JSONB,
  ts         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_run_events_run_id ON orchestrator.run_events (run_id);


-- ─────────────────────────────────────────────────────────────
--  5. SANDBOX SCHEMA
-- ─────────────────────────────────────────────────────────────

CREATE TABLE sandbox.sandboxes (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id           UUID NOT NULL,
  status           sandbox_status NOT NULL DEFAULT 'requested',
  docker_network   TEXT,
  container_ids    TEXT[],
  anvil_port       INTEGER,
  node_port        INTEGER,
  graphql_port     INTEGER,
  resource_limits  JSONB DEFAULT '{"cpu": 2, "memory": "4g"}',
  provisioned_at   TIMESTAMPTZ,
  ready_at         TIMESTAMPTZ,
  closed_at        TIMESTAMPTZ,
  failure_reason   TEXT,
  metadata         JSONB DEFAULT '{}'
);

CREATE INDEX idx_sandboxes_run_id ON sandbox.sandboxes (run_id);
CREATE INDEX idx_sandboxes_status ON sandbox.sandboxes (status);


-- ─────────────────────────────────────────────────────────────
--  6. TESTS SCHEMA
-- ─────────────────────────────────────────────────────────────

CREATE TABLE tests.definitions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug                TEXT NOT NULL UNIQUE,
  name                TEXT NOT NULL,
  version             INTEGER NOT NULL DEFAULT 1,
  tags                TEXT[],
  component           TEXT,
  priority            test_priority NOT NULL DEFAULT 'medium',
  timeout_seconds     INTEGER NOT NULL DEFAULT 120,
  release_introduced  TEXT,
  definition_raw      TEXT NOT NULL,
  definition_parsed   JSONB NOT NULL,
  is_active           BOOLEAN NOT NULL DEFAULT true,
  ai_allowed          BOOLEAN NOT NULL DEFAULT false,
  category            TEXT,
  phase               TEXT,
  created_by          TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_definitions_tags ON tests.definitions USING GIN (tags);
CREATE INDEX idx_definitions_is_active ON tests.definitions (is_active);
CREATE INDEX idx_definitions_component ON tests.definitions (component);
CREATE INDEX idx_definitions_category ON tests.definitions (category);
CREATE INDEX idx_definitions_phase    ON tests.definitions (phase);
CREATE INDEX idx_definitions_ai_allowed ON tests.definitions (ai_allowed) WHERE ai_allowed = true;

CREATE TABLE tests.definition_versions (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  definition_id       UUID NOT NULL REFERENCES tests.definitions (id) ON DELETE CASCADE,
  version             INTEGER NOT NULL,
  definition_raw      TEXT NOT NULL,
  definition_parsed   JSONB NOT NULL,
  created_by          TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (definition_id, version)
);

CREATE TABLE tests.results (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id               UUID NOT NULL,
  sandbox_id           UUID NOT NULL,
  definition_id        UUID NOT NULL REFERENCES tests.definitions (id),
  definition_version   INTEGER NOT NULL,
  status               test_status NOT NULL DEFAULT 'pending',
  duration_ms          INTEGER,
  assertion_results    JSONB,
  logs                 TEXT,
  error_message        TEXT,
  started_at           TIMESTAMPTZ,
  completed_at         TIMESTAMPTZ
);

CREATE INDEX idx_results_run_id ON tests.results (run_id);
CREATE INDEX idx_results_sandbox_id ON tests.results (sandbox_id);
CREATE INDEX idx_results_definition_id ON tests.results (definition_id);
CREATE INDEX idx_results_status ON tests.results (status);


-- ─────────────────────────────────────────────────────────────
--  7. AI SCHEMA
-- ─────────────────────────────────────────────────────────────

CREATE TABLE ai.sessions (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sandbox_id       UUID,
  run_id           UUID,
  mode             ai_mode NOT NULL,
  goal             TEXT,
  base_test_id     UUID,
  status           ai_session_status NOT NULL DEFAULT 'starting',
  message_history  JSONB NOT NULL DEFAULT '[]',
  tool_calls       JSONB NOT NULL DEFAULT '[]',
  findings         JSONB NOT NULL DEFAULT '[]',
  created_by       TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at        TIMESTAMPTZ,
  total_tokens     INTEGER,
  tool_call_count  INTEGER DEFAULT 0,
  anthropic_key_ciphertext BYTEA,
  anthropic_key_nonce      BYTEA,
  model_id                 TEXT DEFAULT 'claude-opus-4-6',
  -- 'runner' = delegate execution to test-runner (trigger_test);
  -- 'ai_manual' = the agent executes test steps itself and records verdicts.
  execution_mode   TEXT NOT NULL DEFAULT 'runner'
    CHECK (execution_mode IN ('runner', 'ai_manual')),
  selected_tests   TEXT[] DEFAULT NULL
);

CREATE INDEX idx_ai_sessions_run_id ON ai.sessions (run_id);
CREATE INDEX idx_ai_sessions_status ON ai.sessions (status);

CREATE TABLE ai.tool_invocations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   UUID NOT NULL REFERENCES ai.sessions (id) ON DELETE CASCADE,
  tool_name    TEXT NOT NULL,
  input        JSONB NOT NULL,
  output       JSONB,
  status       TEXT NOT NULL,
  duration_ms  INTEGER,
  -- Test the agent was executing when this call ran (manual sessions; see
  -- migration 0014). Feeds the auto-assembled verdict execution trail.
  definition_slug TEXT,
  -- Immutable verdict ↔ invocation link (migration 0015): set at verdict time,
  -- replacing the mutable slug/time-window attribution. intent/observation are
  -- the agent's optional per-step rationale + interpretation.
  verdict_id   UUID,
  intent       TEXT,
  observation  TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tool_inv_session ON ai.tool_invocations (session_id);
CREATE INDEX idx_tool_inv_created ON ai.tool_invocations (created_at DESC);
CREATE INDEX idx_tool_inv_session_slug ON ai.tool_invocations (session_id, definition_slug);
CREATE INDEX idx_tool_inv_verdict ON ai.tool_invocations (verdict_id);

-- The agent's own pass/fail judgments for manually executed tests (execution_mode
-- = 'ai_manual'). Deliberately separate from runner-produced tests.results.
CREATE TABLE ai.test_verdicts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       UUID NOT NULL REFERENCES ai.sessions (id) ON DELETE CASCADE,
  sandbox_id       UUID,
  definition_slug  TEXT NOT NULL,
  verdict          TEXT NOT NULL
    CHECK (verdict IN ('passed', 'failed', 'blocked', 'skipped', 'inconclusive')),
  reasoning        TEXT NOT NULL,
  inputs_used      JSONB,
  evidence         JSONB,
  duration_ms      INTEGER,
  -- Trust hardening (migration 0015): validation + provenance + reproducibility.
  confidence           NUMERIC(3,2) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  evidence_validated   BOOLEAN NOT NULL DEFAULT false,
  validation_notes     TEXT,
  auto_downgraded_from  TEXT,
  trail_step_count     INTEGER,
  trail_mutating_count INTEGER,
  trail_truncated      BOOLEAN NOT NULL DEFAULT false,
  definition_snapshot  JSONB,
  observations         JSONB,
  model_id             TEXT,
  model_params         JSONB,
  release_tag          TEXT,
  image_tag            TEXT,
  contracts_version    TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ai_verdicts_session ON ai.test_verdicts (session_id);
CREATE INDEX idx_ai_verdicts_slug    ON ai.test_verdicts (definition_slug);
-- One verdict per (session, test): record_test_verdict upserts on this.
CREATE UNIQUE INDEX uq_verdict_session_slug ON ai.test_verdicts (session_id, definition_slug);

-- Test understanding + plan, persisted before execution (migration 0015).
CREATE TABLE ai.test_plans (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       UUID NOT NULL REFERENCES ai.sessions (id) ON DELETE CASCADE,
  definition_slug  TEXT NOT NULL,
  objective        TEXT,
  success_criteria TEXT,
  failure_criteria TEXT,
  planned_steps    JSONB,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, definition_slug)
);
CREATE INDEX idx_test_plans_session ON ai.test_plans (session_id);

-- Must be LOGIN + password so the ai-agent's query_db tool can connect
-- (matches AI_READER_DATABASE_URL in docker-compose.yml and migration 0012).
DO $$ BEGIN
  CREATE ROLE ai_reader WITH LOGIN PASSWORD 'ai_reader_changeme';
EXCEPTION WHEN duplicate_object THEN
  ALTER ROLE ai_reader WITH LOGIN PASSWORD 'ai_reader_changeme';
END $$;

GRANT USAGE ON SCHEMA tests TO ai_reader;
GRANT USAGE ON SCHEMA orchestrator TO ai_reader;
GRANT USAGE ON SCHEMA ai TO ai_reader;
GRANT SELECT ON tests.definitions, tests.results TO ai_reader;
GRANT SELECT ON orchestrator.runs TO ai_reader;
GRANT SELECT ON ai.sessions, ai.tool_invocations, ai.suggested_test_actions, ai.test_verdicts, ai.test_plans TO ai_reader;

CREATE TABLE ai.analyses (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  release_tag   TEXT NOT NULL,
  pr_numbers    INTEGER[],
  changelog     TEXT,
  coverage_gaps JSONB,
  suggestions   JSONB,
  raw_response  TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai.suggested_test_actions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      UUID REFERENCES ai.sessions (id) ON DELETE CASCADE,
  analysis_id     UUID REFERENCES ai.analyses (id) ON DELETE SET NULL,
  definition_raw  TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'pending',
  reviewed_by     TEXT,
  reviewed_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ─────────────────────────────────────────────────────────────
--  8. GITHUB SCHEMA
-- ─────────────────────────────────────────────────────────────
--
-- BCNF normalized version chain.  Every non-key attribute depends on its
-- own table's PK only.  FK direction follows the real causal dependency:
--
--   release_catalog.cli_tag  → cli_catalog.tag
--   cli_catalog.sdk_tag      → sdk_catalog.tag
--   cli_catalog.devnet_tag   → devnet_catalog.tag
--   devnet_catalog.contracts_tag → contracts_catalog.tag
--
-- All cross-reference lookups (e.g. "which node release uses this SDK?")
-- are derived at query time via reverse JOINs — never stored redundantly.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE github.releases (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tag_name        TEXT NOT NULL UNIQUE,
  release_name    TEXT,
  body            TEXT,
  html_url        TEXT,
  image_tag       TEXT,
  pr_numbers      INTEGER[],
  published_at    TIMESTAMPTZ,
  detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_triggered   BOOLEAN NOT NULL DEFAULT false,
  run_id          UUID
);

CREATE INDEX idx_releases_tag_name ON github.releases (tag_name);
CREATE INDEX idx_releases_detected_at ON github.releases (detected_at DESC);

-- ── contracts_catalog — leaf of the version chain ────────────────────────────
-- No FK columns: contracts releases are standalone facts.
CREATE TABLE IF NOT EXISTS github.contracts_catalog (
  tag          TEXT PRIMARY KEY,
  channel      TEXT NOT NULL DEFAULT 'alpha',
  label        TEXT,
  is_active    BOOLEAN NOT NULL DEFAULT true,
  added_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ,
  downloads    INTEGER DEFAULT 0,
  body         TEXT,
  html_url     TEXT
);

-- ── devnet_catalog — bundles a contracts deployment ───────────────────────────
-- @cartesi/devnet is an npm package shipped with each @cartesi/cli release.
-- contracts_tag: which rollups-contracts deployment this devnet includes.
CREATE TABLE IF NOT EXISTS github.devnet_catalog (
  tag           TEXT PRIMARY KEY,
  contracts_tag TEXT REFERENCES github.contracts_catalog (tag),
  channel       TEXT NOT NULL DEFAULT 'alpha',
  label         TEXT,
  is_active     BOOLEAN NOT NULL DEFAULT true,
  added_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at  TIMESTAMPTZ,
  downloads     INTEGER DEFAULT 0,
  body          TEXT,
  html_url      TEXT
);

-- ── sdk_catalog — Docker runtime image releases ───────────────────────────────
-- No FK columns: which CLI/node uses this SDK is derived via reverse JOIN.
CREATE TABLE IF NOT EXISTS github.sdk_catalog (
  tag          TEXT PRIMARY KEY,
  channel      TEXT NOT NULL DEFAULT 'alpha',
  label        TEXT,
  is_active    BOOLEAN NOT NULL DEFAULT true,
  added_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ,
  downloads    INTEGER DEFAULT 0,
  body         TEXT,
  html_url     TEXT
);

-- ── cli_catalog — @cartesi/cli releases (v2.x) ───────────────────────────────
-- sdk_tag:    which @cartesi/sdk this CLI version uses
-- devnet_tag: which @cartesi/devnet this CLI ships (→ contracts via devnet_catalog)
CREATE TABLE IF NOT EXISTS github.cli_catalog (
  tag        TEXT PRIMARY KEY,
  sdk_tag    TEXT REFERENCES github.sdk_catalog (tag),
  devnet_tag TEXT REFERENCES github.devnet_catalog (tag),
  channel    TEXT NOT NULL DEFAULT 'alpha',
  label      TEXT,
  is_active  BOOLEAN NOT NULL DEFAULT true,
  added_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at TIMESTAMPTZ,
  downloads  INTEGER DEFAULT 0,
  body       TEXT,
  html_url   TEXT
);

-- ── release_catalog — curated rollups-node releases ──────────────────────────
-- cli_tag: which @cartesi/cli ships with this node release.
--          NULL for v1.x (no CLI concept).
-- image_tag is NOT stored — computed at query time:
--   v2.x → 'cartesi/rollups-runtime:' || ltrim(cli.sdk_tag, 'v')
--   v1.x → 'cartesi/rollups-node:'    || ltrim(tag, 'v')
CREATE TABLE IF NOT EXISTS github.release_catalog (
  tag                TEXT PRIMARY KEY,
  cli_tag            TEXT REFERENCES github.cli_catalog (tag),
  node_major_version SMALLINT,
  channel            TEXT NOT NULL DEFAULT 'stable',
  label              TEXT,
  is_active          BOOLEAN NOT NULL DEFAULT true,
  added_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at       TIMESTAMPTZ,
  downloads          INTEGER DEFAULT 0,
  body               TEXT,
  html_url           TEXT
);

-- ── Seed data ─────────────────────────────────────────────────────────────────
-- Insert leaf-to-root so FK constraints are satisfied immediately.
-- contracts_catalog and sdk_catalog first, then devnet_catalog, cli_catalog, release_catalog.

INSERT INTO github.contracts_catalog (tag, channel, label) VALUES
  ('v2.2.0', 'stable', 'rollups-contracts v2.2.0'),
  ('v2.1.1', 'stable', 'rollups-contracts v2.1.1'),
  ('v2.0.1', 'stable', 'rollups-contracts v2.0.1')
ON CONFLICT (tag) DO NOTHING;

INSERT INTO github.sdk_catalog (tag, channel, label) VALUES
  ('v0.12.0-alpha.39', 'alpha', 'v0.12.0-alpha.39'),
  ('v0.12.0-alpha.27', 'alpha', 'v0.12.0-alpha.27'),
  ('v0.12.0-alpha.23', 'alpha', 'v0.12.0-alpha.23'),
  ('v0.12.0-alpha.22', 'alpha', 'v0.12.0-alpha.22')
ON CONFLICT (tag) DO NOTHING;

-- devnet_catalog: seeded with known devnet↔contracts pairings.
-- devnet_tag values are populated by github-watcher from CLI release bodies.
-- Until synced from GitHub the devnet entries below serve as anchors; the
-- contracts_tag links are the authoritative source for sandbox provisioning.
INSERT INTO github.devnet_catalog (tag, contracts_tag, channel, label) VALUES
  ('2.2.0', 'v2.2.0', 'stable', '@cartesi/devnet 2.2.0'),
  ('2.1.1', 'v2.1.1', 'stable', '@cartesi/devnet 2.1.1'),
  ('2.0.1', 'v2.0.1', 'stable', '@cartesi/devnet 2.0.1')
ON CONFLICT (tag) DO NOTHING;

-- cli_catalog: sdk_tag and devnet_tag are FKs established by seeding above.
INSERT INTO github.cli_catalog (tag, sdk_tag, devnet_tag, channel, label) VALUES
  ('v2.0.0-alpha.34', 'v0.12.0-alpha.39', '2.2.0', 'alpha', 'v2.0.0-alpha.34'),
  ('v2.0.0-alpha.22', 'v0.12.0-alpha.27', '2.1.1', 'alpha', 'v2.0.0-alpha.22'),
  ('v2.0.0-alpha.19', 'v0.12.0-alpha.23', '2.0.1', 'alpha', 'v2.0.0-alpha.19'),
  ('v2.0.0-alpha.13', 'v0.12.0-alpha.22', '2.0.1', 'alpha', 'v2.0.0-alpha.13')
ON CONFLICT (tag) DO NOTHING;

-- release_catalog: cli_tag FK points to cli_catalog.
-- v1.x releases have cli_tag = NULL (no CLI concept).
-- image_tag is NOT stored here; computed in queries via the JOIN chain.
INSERT INTO github.release_catalog
  (tag, cli_tag, node_major_version, channel, label)
VALUES
  ('v1.5.1',          NULL,               1, 'stable', 'v1.5.1 (stable)'),
  ('v2.0.0-alpha.11', 'v2.0.0-alpha.34',  2, 'alpha',  'v2.0.0-alpha.11'),
  ('v2.0.0-alpha.10', NULL,               2, 'alpha',  'v2.0.0-alpha.10'),
  ('v2.0.0-alpha.9',  'v2.0.0-alpha.22',  2, 'alpha',  'v2.0.0-alpha.9'),
  ('v2.0.0-alpha.8',  'v2.0.0-alpha.19',  2, 'alpha',  'v2.0.0-alpha.8'),
  ('v2.0.0-alpha.7',  'v2.0.0-alpha.13',  2, 'alpha',  'v2.0.0-alpha.7')
ON CONFLICT (tag) DO NOTHING;


-- ─────────────────────────────────────────────────────────────
--  9. NOTIFICATIONS SCHEMA
-- ─────────────────────────────────────────────────────────────

CREATE TABLE notifications.deliveries (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  channel    notification_channel NOT NULL,
  event_type TEXT NOT NULL,
  payload    JSONB NOT NULL,
  status     notification_status NOT NULL DEFAULT 'pending',
  sent_at    TIMESTAMPTZ,
  error      TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_deliveries_status ON notifications.deliveries (status);
CREATE INDEX idx_deliveries_channel ON notifications.deliveries (channel);
