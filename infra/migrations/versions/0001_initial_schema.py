"""Initial schema — all 6 schemas, roles, enums and tables from init.sql

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""
from __future__ import annotations
from alembic import op

revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    -- ── Schemas ──────────────────────────────────────────────────────────────
    CREATE SCHEMA IF NOT EXISTS orchestrator;
    CREATE SCHEMA IF NOT EXISTS sandbox;
    CREATE SCHEMA IF NOT EXISTS tests;
    CREATE SCHEMA IF NOT EXISTS ai;
    CREATE SCHEMA IF NOT EXISTS github;
    CREATE SCHEMA IF NOT EXISTS notifications;

    -- ── Shared enums ─────────────────────────────────────────────────────────
    DO $$ BEGIN
        CREATE TYPE run_status     AS ENUM ('pending','provisioning','running','completed','failed','cancelled');
        CREATE TYPE sandbox_status AS ENUM ('provisioning','ready','in_use','teardown','failed');
        CREATE TYPE test_status    AS ENUM ('pending','running','passed','failed','error','skipped');
        CREATE TYPE ai_mode        AS ENUM ('autonomous','collaborative','interactive','chaos');
        CREATE TYPE ai_sess_status AS ENUM ('active','completed','failed','cancelled');
        CREATE TYPE notif_status   AS ENUM ('pending','delivered','failed');
    EXCEPTION WHEN duplicate_object THEN null;
    END $$;

    -- ── orchestrator.runs ────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS orchestrator.runs (
        run_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        pr_number      INTEGER,
        repo_url       TEXT,
        node_version   TEXT NOT NULL,
        status         run_status NOT NULL DEFAULT 'pending',
        triggered_by   TEXT NOT NULL DEFAULT 'manual',
        priority       INTEGER NOT NULL DEFAULT 5,
        pass_rate      NUMERIC(5,2),
        total_tests    INTEGER NOT NULL DEFAULT 0,
        passed_tests   INTEGER NOT NULL DEFAULT 0,
        failed_tests   INTEGER NOT NULL DEFAULT 0,
        error_message  TEXT,
        sandbox_id     UUID,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        started_at     TIMESTAMPTZ,
        completed_at   TIMESTAMPTZ
    );

    -- ── sandbox.sandboxes ────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS sandbox.sandboxes (
        sandbox_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id         UUID REFERENCES orchestrator.runs(run_id) ON DELETE SET NULL,
        status         sandbox_status NOT NULL DEFAULT 'provisioning',
        node_version   TEXT,
        docker_network TEXT,
        container_ids  JSONB DEFAULT '[]',
        anvil_port     INTEGER,
        node_port      INTEGER,
        graphql_port   INTEGER,
        error_message  TEXT,
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        ready_at       TIMESTAMPTZ,
        released_at    TIMESTAMPTZ
    );

    -- ── tests.definitions ────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS tests.definitions (
        definition_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name           TEXT NOT NULL UNIQUE,
        description    TEXT,
        category       TEXT NOT NULL DEFAULT 'general',
        priority       INTEGER NOT NULL DEFAULT 5,
        enabled        BOOLEAN NOT NULL DEFAULT true,
        tags           JSONB DEFAULT '[]',
        assertions     JSONB NOT NULL DEFAULT '[]',
        created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- ── tests.results ────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS tests.results (
        result_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id          UUID NOT NULL REFERENCES orchestrator.runs(run_id) ON DELETE CASCADE,
        definition_id   UUID NOT NULL REFERENCES tests.definitions(definition_id),
        definition_name TEXT NOT NULL,
        status          test_status NOT NULL DEFAULT 'pending',
        duration_ms     INTEGER,
        error_message   TEXT,
        assertions      JSONB NOT NULL DEFAULT '[]',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        completed_at    TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_results_run_id ON tests.results(run_id);

    -- ── ai.sessions ──────────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS ai.sessions (
        session_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id           UUID REFERENCES orchestrator.runs(run_id) ON DELETE SET NULL,
        mode             ai_mode NOT NULL DEFAULT 'autonomous',
        status           ai_sess_status NOT NULL DEFAULT 'active',
        goal             TEXT,
        model            TEXT NOT NULL DEFAULT 'claude-opus-4-6',
        tool_calls_used  INTEGER NOT NULL DEFAULT 0,
        input_tokens     INTEGER NOT NULL DEFAULT 0,
        output_tokens    INTEGER NOT NULL DEFAULT 0,
        findings         JSONB NOT NULL DEFAULT '[]',
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
        completed_at     TIMESTAMPTZ
    );

    -- ── ai.suggested_test_actions ─────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS ai.suggested_test_actions (
        action_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id           UUID NOT NULL REFERENCES ai.sessions(session_id) ON DELETE CASCADE,
        action_type          TEXT NOT NULL,
        description          TEXT NOT NULL,
        rationale            TEXT,
        status               TEXT NOT NULL DEFAULT 'pending',
        test_definition_yaml TEXT,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- ── github.releases ───────────────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS github.releases (
        release_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tag_name      TEXT NOT NULL UNIQUE,
        release_name  TEXT,
        body          TEXT,
        published_at  TIMESTAMPTZ,
        author        TEXT,
        pr_summary    JSONB DEFAULT '[]',
        run_id        UUID REFERENCES orchestrator.runs(run_id) ON DELETE SET NULL,
        run_triggered BOOLEAN NOT NULL DEFAULT false,
        created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
    );

    -- ── notifications.deliveries ──────────────────────────────────────────────
    CREATE TABLE IF NOT EXISTS notifications.deliveries (
        delivery_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        event_type   TEXT NOT NULL,
        run_id       UUID,
        channel      TEXT NOT NULL DEFAULT 'discord',
        status       notif_status NOT NULL DEFAULT 'pending',
        error        TEXT,
        delivered_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)


def downgrade() -> None:
    op.execute("""
        DROP SCHEMA IF EXISTS notifications CASCADE;
        DROP SCHEMA IF EXISTS github       CASCADE;
        DROP SCHEMA IF EXISTS ai           CASCADE;
        DROP SCHEMA IF EXISTS tests        CASCADE;
        DROP SCHEMA IF EXISTS sandbox      CASCADE;
        DROP SCHEMA IF EXISTS orchestrator CASCADE;
        DROP TYPE IF EXISTS notif_status;
        DROP TYPE IF EXISTS ai_sess_status;
        DROP TYPE IF EXISTS ai_mode;
        DROP TYPE IF EXISTS test_status;
        DROP TYPE IF EXISTS sandbox_status;
        DROP TYPE IF EXISTS run_status;
    """)
