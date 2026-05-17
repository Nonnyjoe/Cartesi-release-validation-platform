-- Migration 0007: Application registry
-- Adds tests.applications for tracking Cartesi dApp repos to validate against,
-- and wires app_id into orchestrator.runs so each run knows which application
-- was built and deployed during that sandbox lifecycle.

-- ── tests.applications ────────────────────────────────────────────────────────
-- Each row represents a Cartesi application registered by an operator.
-- The sandbox-manager clones the repository at app_github_url and runs
-- `cartesi build` before provisioning the node, then deploys + registers
-- the application against the sandbox so tests can exercise real input handling.

CREATE TABLE IF NOT EXISTS tests.applications (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT        NOT NULL,
    github_url   TEXT        NOT NULL,
    description  TEXT,
    is_active    BOOLEAN     NOT NULL DEFAULT true,
    added_by     TEXT,
    added_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_applications_github_url
    ON tests.applications (github_url) WHERE is_active = true;

COMMENT ON TABLE tests.applications IS
    'Cartesi dApp repositories available for use in validation runs. '
    'One application is selected per run; the sandbox-manager clones, builds, '
    'deploys, and registers it before dispatching tests.';

-- ── orchestrator.runs — add app columns ───────────────────────────────────────

ALTER TABLE orchestrator.runs
    ADD COLUMN IF NOT EXISTS app_id      UUID REFERENCES tests.applications (id),
    ADD COLUMN IF NOT EXISTS app_address TEXT;   -- Ethereum address of deployed application contract

COMMENT ON COLUMN orchestrator.runs.app_id      IS 'Application built and deployed for this run (NULL = no application, raw node tests only).';
COMMENT ON COLUMN orchestrator.runs.app_address IS 'Deployed application contract address returned by cartesi-rollups-cli deploy.';
