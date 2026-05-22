"""
tests/api/test_runs_api.py
FastAPI route tests for the run management API (POST/GET /runs, /runs/{id}, cancel, logs).

Key bugs exposed (then fixed) by this suite:
  - get_run and cancel_run do not handle invalid UUIDs → 500 before fix, 400 after fix
"""
import pytest
import uuid
from unittest.mock import AsyncMock, patch


# ─── POST /runs ───────────────────────────────────────────────────────────────

def test_trigger_run_basic_success(runs_client, mock_db):
    """Trigger a run without an app_id — should create a run and return 201."""
    # Only one execute: catalog lookup returns None (no catalog row)
    mock_db.queue(row=None)

    with patch("api.routes.runs.publish_sandbox_request", new_callable=AsyncMock):
        r = runs_client.post("/runs", json={
            "release_tag": "v1.5.0",
            "image_tag":   "cartesi/rollups-node:1.5.0",
        })

    assert r.status_code == 201
    data = r.json()
    assert data["release_tag"]  == "v1.5.0"
    assert data["image_tag"]    == "cartesi/rollups-node:1.5.0"
    assert data["status"]       == "queued"
    assert data["priority"]     == 5
    assert data["triggered_by"] == "user"
    assert "id" in data
    assert "queued_at" in data


def test_trigger_run_with_explicit_priority(runs_client, mock_db):
    mock_db.queue(row=None)
    with patch("api.routes.runs.publish_sandbox_request", new_callable=AsyncMock):
        r = runs_client.post("/runs", json={
            "release_tag": "v1.5.0",
            "image_tag":   "cartesi/rollups-node:1.5.0",
            "priority":    9,
            "triggered_by": "github_release",
        })
    assert r.status_code == 201
    assert r.json()["priority"]     == 9
    assert r.json()["triggered_by"] == "github_release"


def test_trigger_run_invalid_app_id_returns_400(runs_client, mock_db):
    """app_id that is not a valid UUID must return 400."""
    r = runs_client.post("/runs", json={
        "release_tag": "v1.5.0",
        "image_tag":   "cartesi/rollups-node:1.5.0",
        "app_id":      "not-a-uuid",
    })
    assert r.status_code == 400
    assert "Invalid app_id" in r.json()["detail"]


def test_trigger_run_app_id_not_found_returns_404(runs_client, mock_db):
    """If the referenced application does not exist, 404 is returned."""
    # App lookup returns no row
    mock_db.queue(row=None)
    r = runs_client.post("/runs", json={
        "release_tag": "v1.5.0",
        "image_tag":   "cartesi/rollups-node:1.5.0",
        "app_id":      str(uuid.uuid4()),
    })
    assert r.status_code == 404


def test_trigger_run_inactive_app_returns_409(runs_client, mock_db):
    """A run targeting an inactive app must return 409."""
    from types import SimpleNamespace
    inactive_app = SimpleNamespace(name="Inactive", github_url="https://g.com/x", is_active=False)
    mock_db.queue(row=inactive_app)
    r = runs_client.post("/runs", json={
        "release_tag": "v1.5.0",
        "image_tag":   "cartesi/rollups-node:1.5.0",
        "app_id":      str(uuid.uuid4()),
    })
    assert r.status_code == 409


def test_trigger_run_publish_called_with_correct_run_id(runs_client, mock_db):
    """publish_sandbox_request must be called exactly once with the new run's id."""
    mock_db.queue(row=None)
    with patch("api.routes.runs.publish_sandbox_request", new_callable=AsyncMock) as mock_pub:
        r = runs_client.post("/runs", json={
            "release_tag": "v2.0.0-alpha.11",
            "image_tag":   "cartesi/rollups-runtime:0.12.0-alpha.39",
        })
    assert r.status_code == 201
    mock_pub.assert_called_once()
    call_kwargs = mock_pub.call_args.kwargs
    assert call_kwargs["run_id"] == r.json()["id"]
    assert call_kwargs["release_tag"] == "v2.0.0-alpha.11"


# ─── GET /runs ────────────────────────────────────────────────────────────────

def test_list_runs_empty(runs_client, mock_db):
    mock_db.queue(rows=[])
    r = runs_client.get("/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_list_runs_returns_runs(runs_client, mock_db):
    from tests.api.conftest import make_run_obj
    run = make_run_obj()
    mock_db.queue(rows=[run])
    r = runs_client.get("/runs")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["release_tag"] == "v1.5.0"


def test_list_runs_status_filter_accepted(runs_client, mock_db):
    mock_db.queue(rows=[])
    r = runs_client.get("/runs?status=queued")
    assert r.status_code == 200


# ─── GET /runs/{run_id} ───────────────────────────────────────────────────────

def test_get_run_found(runs_client, mock_db):
    from tests.api.conftest import make_run_obj, _RUN_ID
    mock_db.set_get_return(make_run_obj())
    r = runs_client.get(f"/runs/{_RUN_ID}")
    assert r.status_code == 200
    assert r.json()["id"] == str(_RUN_ID)


def test_get_run_not_found_returns_404(runs_client, mock_db):
    mock_db.set_get_return(None)
    r = runs_client.get(f"/runs/{uuid.uuid4()}")
    assert r.status_code == 404


def test_get_run_invalid_uuid_returns_400(runs_client, mock_db):
    """
    BUG (before fix): uuid.UUID("not-a-uuid") raises ValueError → 500.
    AFTER fix: the route catches ValueError and returns 400.
    """
    r = runs_client.get("/runs/not-a-uuid")
    assert r.status_code == 400, (
        "get_run should return 400 for an invalid UUID, not 500. "
        "Add try/except ValueError around uuid.UUID(run_id) in get_run()."
    )


# ─── POST /runs/{run_id}/cancel ───────────────────────────────────────────────

def test_cancel_run_success(runs_client, mock_db):
    from tests.api.conftest import make_run_obj, _RUN_ID
    mock_db.set_get_return(make_run_obj(status="running"))
    r = runs_client.post(f"/runs/{_RUN_ID}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_cancel_already_completed_returns_400(runs_client, mock_db):
    from tests.api.conftest import make_run_obj, _RUN_ID
    mock_db.set_get_return(make_run_obj(status="completed"))
    r = runs_client.post(f"/runs/{_RUN_ID}/cancel")
    assert r.status_code == 400
    assert "completed" in r.json()["detail"]


def test_cancel_run_not_found_returns_404(runs_client, mock_db):
    mock_db.set_get_return(None)
    r = runs_client.post(f"/runs/{uuid.uuid4()}/cancel")
    assert r.status_code == 404


def test_cancel_run_invalid_uuid_returns_400(runs_client, mock_db):
    """
    BUG (before fix): uuid.UUID("bad") raises ValueError → 500.
    AFTER fix: the route returns 400.
    """
    r = runs_client.post("/runs/not-a-uuid/cancel")
    assert r.status_code == 400, (
        "cancel_run should return 400 for an invalid UUID, not 500."
    )


# ─── GET /runs/{run_id}/events ────────────────────────────────────────────────

def test_get_run_events_empty(runs_client, mock_db):
    from tests.api.conftest import _RUN_ID
    mock_db.queue(rows=[])
    r = runs_client.get(f"/runs/{_RUN_ID}/events")
    assert r.status_code == 200
    assert r.json() == []


def test_get_run_events_invalid_uuid_returns_400(runs_client, mock_db):
    r = runs_client.get("/runs/not-a-uuid/events")
    assert r.status_code == 400


def test_get_run_events_returns_events(runs_client, mock_db):
    from tests.api.conftest import _RUN_ID
    from types import SimpleNamespace
    from datetime import datetime, timezone
    _now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    event_row = SimpleNamespace(
        id         = uuid.uuid4(),
        run_id     = _RUN_ID,
        event_type = "run.queued",
        payload    = {"priority": 5},
        ts         = _now,
    )
    mock_db.queue(rows=[event_row])
    r = runs_client.get(f"/runs/{_RUN_ID}/events")
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 1
    assert events[0]["event_type"] == "run.queued"
    assert events[0]["payload"] == {"priority": 5}


# ─── GET /runs/{run_id}/logs ──────────────────────────────────────────────────

def test_get_run_logs_empty(runs_client, mock_db):
    from tests.api.conftest import _RUN_ID
    # Main query result + next-cursor check (no more rows)
    mock_db.queue(rows=[])
    r = runs_client.get(f"/runs/{_RUN_ID}/logs")
    assert r.status_code == 200
    body = r.json()
    assert body["lines"] == []
    assert body["next_cursor"] is None


def test_get_run_logs_invalid_uuid_returns_400(runs_client, mock_db):
    r = runs_client.get("/runs/not-a-uuid/logs")
    assert r.status_code == 400


def test_get_run_logs_with_lines(runs_client, mock_db):
    from tests.api.conftest import _RUN_ID
    from types import SimpleNamespace
    from datetime import datetime, timezone
    _now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    log_row = SimpleNamespace(id=1, source="advancer", level="info",
                               message="node ready", ts=_now)
    # Main query returns one row (< limit so no next-cursor check needed)
    mock_db.queue(rows=[log_row])
    r = runs_client.get(f"/runs/{_RUN_ID}/logs")
    assert r.status_code == 200
    lines = r.json()["lines"]
    assert len(lines) == 1
    assert lines[0]["source"]  == "advancer"
    assert lines[0]["message"] == "node ready"
    assert lines[0]["level"]   == "info"


def test_get_run_log_sources(runs_client, mock_db):
    from tests.api.conftest import _RUN_ID
    from types import SimpleNamespace
    mock_db.queue(rows=[
        SimpleNamespace(source="advancer"),
        SimpleNamespace(source="anvil"),
    ])
    r = runs_client.get(f"/runs/{_RUN_ID}/logs/sources")
    assert r.status_code == 200
    assert set(r.json()["sources"]) == {"advancer", "anvil"}
