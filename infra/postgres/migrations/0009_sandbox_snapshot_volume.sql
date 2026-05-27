-- Migration 0009: persist per-sandbox snapshot volume name
-- Adds snapshot_volume column to sandbox.sandboxes so the teardown path
-- can clean up the named Docker volume even after a sandbox-manager restart
-- (previously the volume name was only tracked in the process's in-memory dict).

ALTER TABLE sandbox.sandboxes
    ADD COLUMN IF NOT EXISTS snapshot_volume TEXT;

COMMENT ON COLUMN sandbox.sandboxes.snapshot_volume IS
    'Name of the per-sandbox Docker volume holding the Cartesi machine snapshot '
    '(e.g. rvp-snapshot-<sandbox_id[:8]>). NULL when the sandbox uses the shared '
    'rvp-test-snapshot volume. Persisted so teardown can remove the volume after '
    'a process restart (Fix 2: startup orphan sweep + GC).';
