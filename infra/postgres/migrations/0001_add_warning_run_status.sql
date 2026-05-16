-- Migration 0001: Add 'warning' value to run_status enum
-- Run once against the live database. Safe to re-run (IF NOT EXISTS).
-- Must be outside an explicit transaction on PostgreSQL < 12.
ALTER TYPE run_status ADD VALUE IF NOT EXISTS 'warning' AFTER 'failed';
