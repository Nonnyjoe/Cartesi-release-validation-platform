-- ─────────────────────────────────────────────────────────────────────────────
-- Migration 0006 — Normalize the version chain to BCNF
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Removes all transitive / reverse-lookup columns so that every non-key
-- attribute depends on its table's primary key only:
--
--   contracts_catalog  tag PK, channel, label, metadata
--         ↑ FK (contracts_tag)
--   devnet_catalog     tag PK, contracts_tag FK, channel, label, metadata
--         ↑ FK (devnet_tag)
--   sdk_catalog        tag PK, channel, label, metadata
--         ↑ FK (sdk_tag) ↑ FK (devnet_tag)
--   cli_catalog        tag PK, sdk_tag FK, devnet_tag FK, channel, label, metadata
--         ↑ FK (cli_tag)
--   release_catalog    tag PK, cli_tag FK, node_major_version, channel, label, metadata
--
-- Dropped columns (all were transitive or reverse-lookup denormalizations):
--   release_catalog : sdk_version, cli_version, devnet_version, contracts_version, image_tag
--   cli_catalog     : contracts_tag (cli→devnet→contracts, 2 hops), node_release_tag (reverse)
--   sdk_catalog     : node_release_tag (reverse+transitive), cli_tag (reverse)
--   contracts_catalog: devnet_tag, cli_tag, node_release_tag, sdk_tag (all reverse/transitive)
--
-- Added:
--   devnet_catalog   (new — was the missing link between cli and contracts)
--   release_catalog.cli_tag  (FK replacing the denormalized cli_version string)
--
-- Run as the rvp superuser against the rvp database.
-- ─────────────────────────────────────────────────────────────────────────────

BEGIN;

-- ── Step 1: Create devnet_catalog ─────────────────────────────────────────────
-- Must exist before we add cli_catalog.devnet_tag FK and before populating data.

CREATE TABLE IF NOT EXISTS github.devnet_catalog (
  tag           TEXT PRIMARY KEY,
  contracts_tag TEXT,             -- FK to contracts_catalog; added as NOT VALID below
  channel       TEXT NOT NULL DEFAULT 'alpha',
  label         TEXT,
  is_active     BOOLEAN NOT NULL DEFAULT true,
  added_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  published_at  TIMESTAMPTZ,
  downloads     INTEGER DEFAULT 0,
  body          TEXT,
  html_url      TEXT
);

-- ── Step 2: Populate devnet_catalog from existing cli_catalog data ─────────────
-- Any CLI release whose body mentioned @cartesi/devnet already has devnet_tag
-- and contracts_tag stored.  Lift those into the new table.

INSERT INTO github.devnet_catalog (tag, contracts_tag, channel)
SELECT DISTINCT
  devnet_tag                                                AS tag,
  contracts_tag                                            AS contracts_tag,
  CASE WHEN devnet_tag ILIKE '%alpha%' THEN 'alpha'
       WHEN devnet_tag ILIKE '%beta%'  THEN 'beta'
       ELSE 'stable' END                                   AS channel
FROM github.cli_catalog
WHERE devnet_tag IS NOT NULL
ON CONFLICT (tag) DO UPDATE
  SET contracts_tag = COALESCE(EXCLUDED.contracts_tag, github.devnet_catalog.contracts_tag);

-- ── Step 3: Add cli_tag to release_catalog ─────────────────────────────────────
-- Normalizes the existing cli_version (stored without 'v') into a proper FK
-- that matches cli_catalog.tag (stored with 'v').

ALTER TABLE github.release_catalog
  ADD COLUMN IF NOT EXISTS cli_tag TEXT;

UPDATE github.release_catalog
SET cli_tag = CASE
    WHEN cli_version IS NULL             THEN NULL
    WHEN cli_version LIKE 'v%'           THEN cli_version
    ELSE 'v' || cli_version
  END
WHERE cli_tag IS NULL;

-- ── Step 4: Drop transitive / reverse columns ──────────────────────────────────

-- release_catalog: sdk_version, cli_version, devnet_version, contracts_version,
--                  and image_tag are all computable via JOINs through the chain.
ALTER TABLE github.release_catalog
  DROP COLUMN IF EXISTS sdk_version,
  DROP COLUMN IF EXISTS cli_version,
  DROP COLUMN IF EXISTS devnet_version,
  DROP COLUMN IF EXISTS contracts_version,
  DROP COLUMN IF EXISTS image_tag;

-- cli_catalog: contracts_tag is 2 hops away (cli→devnet→contracts).
--              node_release_tag is a reverse lookup (the FK lives on release_catalog.cli_tag).
ALTER TABLE github.cli_catalog
  DROP COLUMN IF EXISTS contracts_tag,
  DROP COLUMN IF EXISTS node_release_tag;

-- sdk_catalog: both columns were reverse lookups.
ALTER TABLE github.sdk_catalog
  DROP COLUMN IF EXISTS node_release_tag,
  DROP COLUMN IF EXISTS cli_tag;

-- contracts_catalog: all cross-ref columns were reverse / transitive.
ALTER TABLE github.contracts_catalog
  DROP COLUMN IF EXISTS devnet_tag,
  DROP COLUMN IF EXISTS cli_tag,
  DROP COLUMN IF EXISTS node_release_tag,
  DROP COLUMN IF EXISTS sdk_tag;

-- ── Step 5: Add FK constraints (NOT VALID — enforced for future writes only) ───
-- NOT VALID skips scanning existing rows (avoids blocking on large tables and
-- avoids failures from any historic inconsistent data).
-- Exception blocks used because ADD CONSTRAINT IF NOT EXISTS is not valid SQL.

DO $$
BEGIN
  ALTER TABLE github.release_catalog
    ADD CONSTRAINT fk_release_cli
      FOREIGN KEY (cli_tag) REFERENCES github.cli_catalog (tag)
      NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  ALTER TABLE github.cli_catalog
    ADD CONSTRAINT fk_cli_sdk
      FOREIGN KEY (sdk_tag) REFERENCES github.sdk_catalog (tag)
      NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  ALTER TABLE github.cli_catalog
    ADD CONSTRAINT fk_cli_devnet
      FOREIGN KEY (devnet_tag) REFERENCES github.devnet_catalog (tag)
      NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
  ALTER TABLE github.devnet_catalog
    ADD CONSTRAINT fk_devnet_contracts
      FOREIGN KEY (contracts_tag) REFERENCES github.contracts_catalog (tag)
      NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

COMMIT;
