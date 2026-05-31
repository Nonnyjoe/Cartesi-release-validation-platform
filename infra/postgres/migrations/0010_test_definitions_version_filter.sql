-- 0010_test_definitions_version_filter.sql
-- Add min_node_major_version to tests.definitions so v1.x and v2.x suites
-- can coexist without running the wrong tests on the wrong node version.
-- Default 1 preserves all existing definitions as v1.x-compatible.

ALTER TABLE tests.definitions
  ADD COLUMN IF NOT EXISTS min_node_major_version INTEGER NOT NULL DEFAULT 1;

COMMENT ON COLUMN tests.definitions.min_node_major_version IS
  'Minimum node major version required to run this test (1=v1.x, 2=v2.x).';
