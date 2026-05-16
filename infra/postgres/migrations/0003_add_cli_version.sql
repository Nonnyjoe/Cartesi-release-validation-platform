-- Migration 0003: add cli_version column to github.release_catalog
-- Apply with: make migrate-cli

ALTER TABLE github.release_catalog
  ADD COLUMN IF NOT EXISTS cli_version TEXT;

-- Populate known CLI versions from static mapping
-- (rollups-node version → cartesi/cli version that ships with it)
UPDATE github.release_catalog SET cli_version = '2.0.0-alpha.34' WHERE tag = 'v2.0.0-alpha.11';
UPDATE github.release_catalog SET cli_version = '2.0.0-alpha.22' WHERE tag = 'v2.0.0-alpha.9';
UPDATE github.release_catalog SET cli_version = '2.0.0-alpha.19' WHERE tag = 'v2.0.0-alpha.8';
UPDATE github.release_catalog SET cli_version = '2.0.0-alpha.13' WHERE tag = 'v2.0.0-alpha.7';
-- v2.0.0-alpha.10 CLI version is not confirmed; leave NULL to be resolved via GitHub API
