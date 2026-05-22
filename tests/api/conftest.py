"""
tests/api/conftest.py
FastAPI test app fixtures with a queue-based mock AsyncSession.

Each test can call mock_db.queue(row=...) / mock_db.queue(rows=...) to
prescribe the return value of successive db.execute() calls.
db.get() is configured per-test via mock_db.set_get_return(obj).
"""
import sys
import os
from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid

# ── env vars must be set BEFORE importing any service module ─────────────────
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("RABBITMQ_URL", "amqp://rvp:test@localhost:5672/")

# sys.path is set via pytest.ini pythonpath: services/orchestrator, shared

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from db import get_db
from api.routes.apps import router as apps_router
from api.routes.runs import router as runs_router


# ─── Mock result helper ───────────────────────────────────────────────────────

class _MockResult:
    """Mimics a SQLAlchemy CursorResult for testing."""

    def __init__(self, rows=None, row=None, scalar_val=0, rowcount=1):
        if rows is not None:
            self._rows = rows
        elif row is not None:
            self._rows = [row]
        else:
            self._rows = []

        self._scalar  = scalar_val
        self.rowcount = rowcount

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar

    def scalars(self):
        rows = self._rows

        class _S:
            def all(_):  # noqa: N805
                return rows

        return _S()


# ─── Mock session ─────────────────────────────────────────────────────────────

class MockSession:
    """
    A queue-based mock of sqlalchemy.ext.asyncio.AsyncSession.

    Usage in tests:
        mock_db.queue(row=some_row)           # next execute() returns this row
        mock_db.queue(rows=[r1, r2])          # next execute() returns these rows
        mock_db.queue(rowcount=0)             # next execute() has rowcount=0
        mock_db.set_get_return(obj)           # db.get(...) returns obj
    """

    def __init__(self):
        self._queue: list[_MockResult] = []
        self._get_return = None
        self.added: list = []
        self.commit_called = False

    def queue(self, *, row=None, rows=None, scalar_val=0, rowcount=1):
        """Enqueue a result for the next execute() call."""
        self._queue.append(_MockResult(rows=rows, row=row,
                                       scalar_val=scalar_val, rowcount=rowcount))
        return self  # fluent

    def set_get_return(self, obj):
        self._get_return = obj
        return self

    async def execute(self, *args, **kwargs):
        if self._queue:
            return self._queue.pop(0)
        return _MockResult()  # default empty

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commit_called = True

    async def refresh(self, obj):
        pass

    async def get(self, model, pk):
        return self._get_return


# ─── Row factories ────────────────────────────────────────────────────────────

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
_APP_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_RUN_ID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")


def make_app_row(**kwargs):
    defaults = dict(
        id          = _APP_ID,
        name        = "Echo App",
        github_url  = "https://github.com/cartesi/echo-dapp",
        description = "A simple echo dApp",
        is_active   = True,
        added_by    = "tester",
        added_at    = _NOW,
        updated_at  = _NOW,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def make_run_obj(**kwargs):
    """Return a SQLAlchemy Run ORM instance suitable for mocking db.get()."""
    from models.run import Run
    defaults = dict(
        id                = _RUN_ID,
        release_tag       = "v1.5.0",
        image_tag         = "cartesi/rollups-node:1.5.0",
        suite_ids         = [],
        status            = "queued",
        priority          = 5,
        triggered_by      = "user",
        triggered_by_user = None,
        queued_at         = _NOW,
        started_at        = None,
        completed_at      = None,
        pass_rate         = None,
        app_id            = None,
        app_address       = None,
    )
    defaults.update(kwargs)
    run = Run()
    for k, v in defaults.items():
        setattr(run, k, v)
    return run


# ─── App-level fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    return MockSession()


def _make_client(router, prefix: str, mock_db: MockSession) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix=prefix)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def apps_client(mock_db):
    return _make_client(apps_router, "/apps", mock_db)


@pytest.fixture
def runs_client(mock_db):
    return _make_client(runs_router, "/runs", mock_db)
