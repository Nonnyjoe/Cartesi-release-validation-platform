-- ============================================================
--  0002: sdk_version + node_major_version on release_catalog
--  Fix seeded image_tag values to use correct registries.
--  Run as superuser (rvp):
--    psql -U rvp rvp -f infra/postgres/migrations/0002_add_sdk_version.sql
-- ============================================================

ALTER TABLE github.release_catalog
  ADD COLUMN IF NOT EXISTS sdk_version TEXT,
  ADD COLUMN IF NOT EXISTS node_major_version SMALLINT;

-- ── Fix v1.x entries ──────────────────────────────────────────────────────────
-- v1.x ships on Docker Hub (not GHCR), without the 'v' prefix in the image tag.
UPDATE github.release_catalog
   SET node_major_version = 1,
       image_tag = 'cartesi/rollups-node:' || ltrim(tag, 'v')
 WHERE tag NOT LIKE '%alpha%'
   AND tag NOT LIKE '%beta%';

-- ── Fix known v2.x alpha entries (confirmed mapping from CLI release notes) ───
UPDATE github.release_catalog
   SET node_major_version = 2,
       sdk_version = '0.12.0-alpha.39',
       image_tag   = 'cartesi/rollups-runtime:0.12.0-alpha.39'
 WHERE tag = 'v2.0.0-alpha.11';

UPDATE github.release_catalog
   SET node_major_version = 2,
       sdk_version = '0.12.0-alpha.27',
       image_tag   = 'cartesi/rollups-runtime:0.12.0-alpha.27'
 WHERE tag = 'v2.0.0-alpha.9';

UPDATE github.release_catalog
   SET node_major_version = 2,
       sdk_version = '0.12.0-alpha.23',
       image_tag   = 'cartesi/rollups-runtime:0.12.0-alpha.23'
 WHERE tag = 'v2.0.0-alpha.8';

UPDATE github.release_catalog
   SET node_major_version = 2,
       sdk_version = '0.12.0-alpha.22',
       image_tag   = 'cartesi/rollups-runtime:0.12.0-alpha.22'
 WHERE tag = 'v2.0.0-alpha.7';

-- ── Any remaining alpha/beta entries without a major version ──────────────────
UPDATE github.release_catalog
   SET node_major_version = 2
 WHERE (tag LIKE '%alpha%' OR tag LIKE '%beta%')
   AND node_major_version IS NULL;
