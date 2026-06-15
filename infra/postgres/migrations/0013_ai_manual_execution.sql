-- 0013: AI manual test execution
-- - ai.sessions gains execution_mode ('runner' = delegate to test-runner via
--   trigger_test; 'ai_manual' = agent executes test steps itself) and
--   selected_tests (ordered slugs picked at session creation).
-- - ai.test_verdicts stores the agent's own pass/fail judgments for manually
--   executed tests, kept separate from runner-produced tests.results.

ALTER TABLE ai.sessions
  ADD COLUMN IF NOT EXISTS execution_mode TEXT NOT NULL DEFAULT 'runner'
    CHECK (execution_mode IN ('runner', 'ai_manual')),
  ADD COLUMN IF NOT EXISTS selected_tests TEXT[] DEFAULT NULL;

CREATE TABLE IF NOT EXISTS ai.test_verdicts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       UUID NOT NULL REFERENCES ai.sessions (id) ON DELETE CASCADE,
  sandbox_id       UUID,
  definition_slug  TEXT NOT NULL,
  verdict          TEXT NOT NULL
    CHECK (verdict IN ('passed', 'failed', 'blocked', 'skipped', 'inconclusive')),
  reasoning        TEXT NOT NULL,
  inputs_used      JSONB,            -- inputs the agent chose (payloads, amounts, args)
  evidence         JSONB,            -- observations backing the verdict (RPC responses, log excerpts)
  duration_ms      INTEGER,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_verdicts_session ON ai.test_verdicts (session_id);
CREATE INDEX IF NOT EXISTS idx_ai_verdicts_slug    ON ai.test_verdicts (definition_slug);

GRANT SELECT ON ai.test_verdicts TO ai_reader;
