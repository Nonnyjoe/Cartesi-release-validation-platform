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
  created_by          TEXT,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_definitions_tags ON tests.definitions USING GIN (tags);
CREATE INDEX idx_definitions_is_active ON tests.definitions (is_active);
CREATE INDEX idx_definitions_component ON tests.definitions (component);

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
  tool_call_count  INTEGER DEFAULT 0
);

CREATE INDEX idx_ai_sessions_run_id ON ai.sessions (run_id);
CREATE INDEX idx_ai_sessions_status ON ai.sessions (status);

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

-- Curated catalog of known/tested rollups-node releases
CREATE TABLE IF NOT EXISTS github.release_catalog (
  tag                TEXT PRIMARY KEY,
  image_tag          TEXT NOT NULL,        -- primary Docker image for this release
  sdk_version        TEXT,                 -- v2.x: @cartesi/sdk version (= Docker image tag suffix)
  cli_version        TEXT,                 -- v2.x: @cartesi/cli version that ships with this node release
  node_major_version SMALLINT,             -- 1 or 2
  channel            TEXT NOT NULL DEFAULT 'stable',  -- stable | alpha | beta
  label              TEXT,
  is_active          BOOLEAN NOT NULL DEFAULT true,
  added_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at       TIMESTAMPTZ,
  downloads          INTEGER DEFAULT 0,
  body               TEXT,
  html_url           TEXT,
  devnet_version     TEXT,                 -- @cartesi/devnet version
  contracts_version  TEXT                  -- rollups-contracts version
);

-- Seed with known releases.
-- v1.x: Docker Hub (docker.io/cartesi/rollups-node:<ver>), no 'v' prefix in image tag.
-- v2.x: SDK runtime image (cartesi/rollups-runtime:<sdk_version>).
--       cli_version is the @cartesi/cli version that ships with the node release.
INSERT INTO github.release_catalog (tag, image_tag, sdk_version, cli_version, node_major_version, channel, label) VALUES
  ('v1.5.1',          'cartesi/rollups-node:1.5.1',              NULL,                NULL,               1, 'stable', 'v1.5.1 (stable)'),
  ('v2.0.0-alpha.11', 'cartesi/rollups-runtime:0.12.0-alpha.39', '0.12.0-alpha.39',  '2.0.0-alpha.34',  2, 'alpha',  'v2.0.0-alpha.11'),
  ('v2.0.0-alpha.10', 'cartesi/rollups-runtime:0.12.0-alpha.27', '0.12.0-alpha.27',  NULL,              2, 'alpha',  'v2.0.0-alpha.10'),
  ('v2.0.0-alpha.9',  'cartesi/rollups-runtime:0.12.0-alpha.27', '0.12.0-alpha.27',  '2.0.0-alpha.22',  2, 'alpha',  'v2.0.0-alpha.9'),
  ('v2.0.0-alpha.8',  'cartesi/rollups-runtime:0.12.0-alpha.23', '0.12.0-alpha.23',  '2.0.0-alpha.19',  2, 'alpha',  'v2.0.0-alpha.8'),
  ('v2.0.0-alpha.7',  'cartesi/rollups-runtime:0.12.0-alpha.22', '0.12.0-alpha.22',  '2.0.0-alpha.13',  2, 'alpha',  'v2.0.0-alpha.7')
ON CONFLICT (tag) DO NOTHING;

-- CLI release catalog (releases from cartesi/cli repo, major v2.x)
CREATE TABLE IF NOT EXISTS github.cli_catalog (
  tag              TEXT PRIMARY KEY,
  channel          TEXT NOT NULL DEFAULT 'alpha',
  label            TEXT,
  is_active        BOOLEAN NOT NULL DEFAULT true,
  added_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at     TIMESTAMPTZ,
  downloads        INTEGER DEFAULT 0,
  body             TEXT,
  html_url         TEXT,
  node_release_tag TEXT,  -- rollups-node release this CLI targets
  sdk_tag          TEXT,  -- SDK release this CLI pairs with
  devnet_tag       TEXT,  -- @cartesi/devnet version this CLI ships
  contracts_tag    TEXT   -- contracts version (via devnet)
);

-- SDK release catalog (releases from cartesi/cli repo, major v0.x)
CREATE TABLE IF NOT EXISTS github.sdk_catalog (
  tag              TEXT PRIMARY KEY,
  channel          TEXT NOT NULL DEFAULT 'alpha',
  label            TEXT,
  is_active        BOOLEAN NOT NULL DEFAULT true,
  added_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at     TIMESTAMPTZ,
  downloads        INTEGER DEFAULT 0,
  body             TEXT,
  html_url         TEXT,
  node_release_tag TEXT,  -- rollups-node release this SDK targets
  cli_tag          TEXT   -- CLI release this SDK pairs with
);

-- Rollups-contracts release catalog
CREATE TABLE IF NOT EXISTS github.contracts_catalog (
  tag              TEXT PRIMARY KEY,
  channel          TEXT NOT NULL DEFAULT 'alpha',
  label            TEXT,
  is_active        BOOLEAN NOT NULL DEFAULT true,
  added_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at     TIMESTAMPTZ,
  downloads        INTEGER DEFAULT 0,
  body             TEXT,
  html_url         TEXT,
  devnet_tag       TEXT,
  cli_tag          TEXT,
  node_release_tag TEXT,
  sdk_tag          TEXT
);

INSERT INTO github.cli_catalog (tag, channel, label, node_release_tag, sdk_tag, devnet_tag, contracts_tag) VALUES
  ('v2.0.0-alpha.34', 'alpha', 'v2.0.0-alpha.34', 'v2.0.0-alpha.11', 'v0.12.0-alpha.39', NULL, NULL),
  ('v2.0.0-alpha.22', 'alpha', 'v2.0.0-alpha.22', 'v2.0.0-alpha.9',  'v0.12.0-alpha.27', NULL, NULL),
  ('v2.0.0-alpha.19', 'alpha', 'v2.0.0-alpha.19', 'v2.0.0-alpha.8',  'v0.12.0-alpha.23', NULL, NULL),
  ('v2.0.0-alpha.13', 'alpha', 'v2.0.0-alpha.13', 'v2.0.0-alpha.7',  'v0.12.0-alpha.22', NULL, NULL)
ON CONFLICT (tag) DO NOTHING;

INSERT INTO github.sdk_catalog (tag, channel, label, node_release_tag, cli_tag) VALUES
  ('v0.12.0-alpha.39', 'alpha', 'v0.12.0-alpha.39', 'v2.0.0-alpha.11', 'v2.0.0-alpha.34'),
  ('v0.12.0-alpha.27', 'alpha', 'v0.12.0-alpha.27', 'v2.0.0-alpha.9',  'v2.0.0-alpha.22'),
  ('v0.12.0-alpha.23', 'alpha', 'v0.12.0-alpha.23', 'v2.0.0-alpha.8',  'v2.0.0-alpha.19'),
  ('v0.12.0-alpha.22', 'alpha', 'v0.12.0-alpha.22', 'v2.0.0-alpha.7',  'v2.0.0-alpha.13')
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
