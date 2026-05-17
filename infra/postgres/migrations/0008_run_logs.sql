-- Migration 0008: Persistent run logs
-- Creates orchestrator.run_logs for storing per-run log lines from all sources:
-- container stdout/stderr (node services, anvil, build containers), subprocess
-- output (git clone, cartesi build), exec_run output (deploy / register), and
-- test-runner executor diagnostics.
--
-- Design decisions:
--   • BIGSERIAL primary key gives free chronological ordering and enables
--     efficient keyset (cursor) pagination without an extra seq column.
--   • Cascade delete: run_logs are cleaned up automatically when a run is purged.
--   • source is a free-text label, e.g. "advancer", "anvil", "build",
--     "deploy", "test:<uuid>".
--   • level: info | warn | error | debug
--   • message is capped at 4096 chars on insert (enforced by the application layer).
--   • The composite index on (run_id, id) is the only index needed — it supports
--     both "all logs for a run" scans and "logs after cursor X" keyset queries.

CREATE TABLE IF NOT EXISTS orchestrator.run_logs (
    id         BIGSERIAL    PRIMARY KEY,
    run_id     UUID         NOT NULL REFERENCES orchestrator.runs(id) ON DELETE CASCADE,
    source     TEXT         NOT NULL,
    level      TEXT         NOT NULL DEFAULT 'info',
    message    TEXT         NOT NULL,
    ts         TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_run_logs_run_cursor
    ON orchestrator.run_logs (run_id, id);

COMMENT ON TABLE orchestrator.run_logs IS
    'Persistent log lines for each run, written by sandbox-manager and test-runner. '
    'Replaces ephemeral WebSocket-only service_log events with durable per-run storage.';

COMMENT ON COLUMN orchestrator.run_logs.source  IS 'Log source label: service name (advancer, anvil, …), "build", "deploy", or "test:<uuid>".';
COMMENT ON COLUMN orchestrator.run_logs.level   IS 'Severity: info | warn | error | debug';
COMMENT ON COLUMN orchestrator.run_logs.message IS 'Log line text, max ~4096 chars.';
