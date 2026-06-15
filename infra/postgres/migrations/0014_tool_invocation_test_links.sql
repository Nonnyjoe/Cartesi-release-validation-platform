-- 0014: link tool invocations to the test being manually executed.
-- The ai-agent's ToolExecutor tags every call with the test the agent is
-- currently working on (inferred from read_test_definition → record_test_verdict
-- boundaries). record_test_verdict then auto-assembles an execution trail from
-- these rows into the verdict's evidence — the agent no longer re-types tool
-- I/O into evidence, saving tokens while making evidence richer and exact.

ALTER TABLE ai.tool_invocations
  ADD COLUMN IF NOT EXISTS definition_slug TEXT;

CREATE INDEX IF NOT EXISTS idx_tool_inv_session_slug
  ON ai.tool_invocations (session_id, definition_slug);
