-- 0015: trustworthiness hardening for AI manual-execution verdicts.
-- Addresses the 2026-06-13 trustworthiness review's structural gaps:
--   (1) verdicts judged with no validation layer  → evidence_validated / validation_notes
--   (2) reproducibility (no provenance on verdict) → model/release/image/contracts + params
--   (3) evidence optional for a pass               → trail metrics + downgrade bookkeeping
--   (4) heuristic time-window trail attribution    → immutable verdict_id FK on invocations
--   (5) understanding/plan never persisted         → ai.test_plans
-- All additive + idempotent.

-- ── Verdict provenance, confidence, validation bookkeeping ───────────────────
ALTER TABLE ai.test_verdicts
  ADD COLUMN IF NOT EXISTS confidence            NUMERIC(3,2)
      CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  ADD COLUMN IF NOT EXISTS evidence_validated    BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS validation_notes      TEXT,
  ADD COLUMN IF NOT EXISTS auto_downgraded_from  TEXT,     -- original verdict if the gate downgraded it
  ADD COLUMN IF NOT EXISTS trail_step_count      INTEGER,
  ADD COLUMN IF NOT EXISTS trail_mutating_count  INTEGER,
  ADD COLUMN IF NOT EXISTS trail_truncated       BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS definition_snapshot   JSONB,    -- frozen objective/expected/assertions
  ADD COLUMN IF NOT EXISTS observations          JSONB,    -- agent's per-point interpretations
  ADD COLUMN IF NOT EXISTS model_id              TEXT,
  ADD COLUMN IF NOT EXISTS model_params          JSONB,    -- {temperature, max_tokens, ...}
  ADD COLUMN IF NOT EXISTS release_tag           TEXT,
  ADD COLUMN IF NOT EXISTS image_tag             TEXT,
  ADD COLUMN IF NOT EXISTS contracts_version     TEXT;

-- One verdict per (session, test). record_test_verdict upserts on this; the
-- fail-safe blocked-verdict writer uses ON CONFLICT DO NOTHING so it never
-- clobbers a real verdict.
CREATE UNIQUE INDEX IF NOT EXISTS uq_verdict_session_slug
  ON ai.test_verdicts (session_id, definition_slug);

-- ── Immutable verdict ↔ invocation link (replaces mutable slug/time-window) ──
ALTER TABLE ai.tool_invocations
  ADD COLUMN IF NOT EXISTS verdict_id  UUID
      REFERENCES ai.test_verdicts (id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS intent      TEXT,   -- why the agent made this call (optional)
  ADD COLUMN IF NOT EXISTS observation TEXT;   -- agent's interpretation of the result (optional)

CREATE INDEX IF NOT EXISTS idx_tool_inv_verdict ON ai.tool_invocations (verdict_id);

-- ── Test understanding + plan artifact (persisted before execution) ──────────
CREATE TABLE IF NOT EXISTS ai.test_plans (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       UUID NOT NULL REFERENCES ai.sessions (id) ON DELETE CASCADE,
  definition_slug  TEXT NOT NULL,
  objective        TEXT,
  success_criteria TEXT,
  failure_criteria TEXT,
  planned_steps    JSONB,   -- [{intent, tool, input_rationale, expected_observation}]
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, definition_slug)
);
CREATE INDEX IF NOT EXISTS idx_test_plans_session ON ai.test_plans (session_id);

GRANT SELECT ON ai.test_plans TO ai_reader;
