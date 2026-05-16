-- Migration 0004: CLI and SDK release catalogs
-- Apply with: make migrate-catalogs

CREATE TABLE IF NOT EXISTS github.cli_catalog (
  tag              TEXT PRIMARY KEY,
  channel          TEXT NOT NULL DEFAULT 'alpha',
  label            TEXT,
  is_active        BOOLEAN NOT NULL DEFAULT true,
  added_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at     TIMESTAMPTZ,
  downloads        INTEGER DEFAULT 0,
  body             TEXT,
  html_url         TEXT,
  -- cross-references (editable)
  node_release_tag TEXT,   -- rollups-node release this CLI targets
  sdk_tag          TEXT    -- SDK release this CLI pairs with
);

CREATE TABLE IF NOT EXISTS github.sdk_catalog (
  tag              TEXT PRIMARY KEY,
  channel          TEXT NOT NULL DEFAULT 'alpha',
  label            TEXT,
  is_active        BOOLEAN NOT NULL DEFAULT true,
  added_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at     TIMESTAMPTZ,
  downloads        INTEGER DEFAULT 0,
  body             TEXT,
  html_url         TEXT,
  -- cross-references (editable)
  node_release_tag TEXT,   -- rollups-node release this SDK targets
  cli_tag          TEXT    -- CLI release this SDK pairs with
);

-- Seed known relationships from existing release_catalog data
INSERT INTO github.cli_catalog (tag, channel, label, node_release_tag, sdk_tag) VALUES
  ('v2.0.0-alpha.34', 'alpha', 'v2.0.0-alpha.34', 'v2.0.0-alpha.11', 'v0.12.0-alpha.39'),
  ('v2.0.0-alpha.22', 'alpha', 'v2.0.0-alpha.22', 'v2.0.0-alpha.9',  'v0.12.0-alpha.27'),
  ('v2.0.0-alpha.19', 'alpha', 'v2.0.0-alpha.19', 'v2.0.0-alpha.8',  'v0.12.0-alpha.23'),
  ('v2.0.0-alpha.13', 'alpha', 'v2.0.0-alpha.13', 'v2.0.0-alpha.7',  'v0.12.0-alpha.22')
ON CONFLICT (tag) DO NOTHING;

INSERT INTO github.sdk_catalog (tag, channel, label, node_release_tag, cli_tag) VALUES
  ('v0.12.0-alpha.39', 'alpha', 'v0.12.0-alpha.39', 'v2.0.0-alpha.11', 'v2.0.0-alpha.34'),
  ('v0.12.0-alpha.27', 'alpha', 'v0.12.0-alpha.27', 'v2.0.0-alpha.9',  'v2.0.0-alpha.22'),
  ('v0.12.0-alpha.23', 'alpha', 'v0.12.0-alpha.23', 'v2.0.0-alpha.8',  'v2.0.0-alpha.19'),
  ('v0.12.0-alpha.22', 'alpha', 'v0.12.0-alpha.22', 'v2.0.0-alpha.7',  'v2.0.0-alpha.13')
ON CONFLICT (tag) DO NOTHING;
