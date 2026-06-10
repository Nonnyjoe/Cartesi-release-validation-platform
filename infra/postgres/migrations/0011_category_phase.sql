-- Add category and phase columns to tests.definitions so tests can be grouped
-- by the Phase/Category taxonomy from cartesi-sdk-v2-qa.csv.
ALTER TABLE tests.definitions
  ADD COLUMN IF NOT EXISTS category TEXT,
  ADD COLUMN IF NOT EXISTS phase    TEXT;

CREATE INDEX IF NOT EXISTS idx_definitions_category ON tests.definitions (category);
CREATE INDEX IF NOT EXISTS idx_definitions_phase    ON tests.definitions (phase);
