-- AI Agent integration: per-session credentials, model picker,
-- test whitelist flag, and tool-invocation audit log.

-- Per-session encrypted credentials & model selection
ALTER TABLE ai.sessions
  ADD COLUMN IF NOT EXISTS anthropic_key_ciphertext BYTEA,
  ADD COLUMN IF NOT EXISTS anthropic_key_nonce      BYTEA,
  ADD COLUMN IF NOT EXISTS model_id                 TEXT DEFAULT 'claude-opus-4-6';

-- Whitelist flag on test definitions: agent may only invoke ai_allowed=true tests
ALTER TABLE tests.definitions
  ADD COLUMN IF NOT EXISTS ai_allowed BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_definitions_ai_allowed
  ON tests.definitions (ai_allowed) WHERE ai_allowed = true;

-- Audit table: every tool call by the agent gets one row here
CREATE TABLE IF NOT EXISTS ai.tool_invocations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   UUID NOT NULL REFERENCES ai.sessions (id) ON DELETE CASCADE,
  tool_name    TEXT NOT NULL,
  input        JSONB NOT NULL,
  output       JSONB,
  status       TEXT NOT NULL,                       -- 'ok' | 'error' | 'denied'
  duration_ms  INTEGER,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tool_inv_session ON ai.tool_invocations (session_id);
CREATE INDEX IF NOT EXISTS idx_tool_inv_created ON ai.tool_invocations (created_at DESC);

-- Restricted role for AI agent read-only DB access (query_db tool)
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
GRANT SELECT ON ai.sessions, ai.tool_invocations, ai.suggested_test_actions TO ai_reader;
