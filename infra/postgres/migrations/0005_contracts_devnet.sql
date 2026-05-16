-- Migration 0005: contracts catalog + devnet/contracts columns
-- Apply with: make migrate-contracts

-- ── New catalog for rollups-contracts releases ────────────────────────────────
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
  -- cross-references resolved from CLI release bodies
  devnet_tag       TEXT,   -- @cartesi/devnet version that bundles these contracts
  cli_tag          TEXT,   -- CLI release that uses this devnet
  node_release_tag TEXT,   -- rollups-node release that pairs with this CLI
  sdk_tag          TEXT    -- SDK release
);

-- ── Extend cli_catalog with devnet + contracts cross-refs ──────────────────
ALTER TABLE github.cli_catalog
  ADD COLUMN IF NOT EXISTS devnet_tag    TEXT,   -- @cartesi/devnet version this CLI ships
  ADD COLUMN IF NOT EXISTS contracts_tag TEXT;   -- contracts version (via devnet)

-- ── Extend release_catalog with devnet + contracts ─────────────────────────
ALTER TABLE github.release_catalog
  ADD COLUMN IF NOT EXISTS devnet_version    TEXT,   -- @cartesi/devnet version
  ADD COLUMN IF NOT EXISTS contracts_version TEXT;   -- rollups-contracts version
