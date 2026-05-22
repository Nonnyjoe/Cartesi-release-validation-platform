"""
tests/api/test_apps_api.py
FastAPI route tests for the Application Registry (GET/POST/PATCH/DELETE /apps).

The DB session is replaced by MockSession so no PostgreSQL connection is needed.
"""
import pytest


# ─── GET /apps ────────────────────────────────────────────────────────────────

def test_list_apps_returns_empty_list_when_no_apps(apps_client, mock_db):
    mock_db.queue(rows=[])
    r = apps_client.get("/apps")
    assert r.status_code == 200
    assert r.json() == []


def test_list_apps_returns_apps(apps_client, mock_db):
    from tests.api.conftest import make_app_row
    row = make_app_row(name="Echo App")
    mock_db.queue(rows=[row])
    r = apps_client.get("/apps")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["name"] == "Echo App"
    assert data[0]["github_url"] == "https://github.com/cartesi/echo-dapp"
    assert data[0]["is_active"] is True


def test_list_apps_include_inactive_param_accepted(apps_client, mock_db):
    mock_db.queue(rows=[])
    r = apps_client.get("/apps?include_inactive=true")
    assert r.status_code == 200


# ─── POST /apps ───────────────────────────────────────────────────────────────

def test_create_app_success(apps_client, mock_db):
    from tests.api.conftest import make_app_row
    # 1st execute: duplicate check → None
    mock_db.queue(row=None)
    # 2nd execute: INSERT (no fetchone needed — rowcount handled)
    mock_db.queue()
    # 3rd execute: SELECT after insert → the created row
    mock_db.queue(row=make_app_row(name="New App",
                                   github_url="https://github.com/test/new-app"))

    r = apps_client.post("/apps", json={
        "name":       "New App",
        "github_url": "https://github.com/test/new-app",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"]       == "New App"
    assert data["github_url"] == "https://github.com/test/new-app"
    assert data["is_active"]  is True
    assert "id" in data
    assert "added_at" in data


def test_create_app_conflict_on_duplicate_url(apps_client, mock_db):
    from tests.api.conftest import make_app_row
    # duplicate check returns an existing row
    mock_db.queue(row=make_app_row())

    r = apps_client.post("/apps", json={
        "name":       "Duplicate App",
        "github_url": "https://github.com/cartesi/echo-dapp",
    })
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"].lower()


def test_create_app_invalid_url_scheme_returns_422(apps_client, mock_db):
    r = apps_client.post("/apps", json={
        "name":       "Bad URL App",
        "github_url": "ftp://example.com/repo",
    })
    assert r.status_code == 422


def test_create_app_empty_name_returns_422(apps_client, mock_db):
    r = apps_client.post("/apps", json={
        "name":       "   ",   # all whitespace
        "github_url": "https://github.com/test/repo",
    })
    assert r.status_code == 422


def test_create_app_name_too_long_returns_422(apps_client, mock_db):
    r = apps_client.post("/apps", json={
        "name":       "x" * 121,
        "github_url": "https://github.com/test/repo",
    })
    assert r.status_code == 422


def test_create_app_missing_required_fields_returns_422(apps_client, mock_db):
    r = apps_client.post("/apps", json={"name": "Only Name"})
    assert r.status_code == 422


# ─── GET /apps/{app_id} ───────────────────────────────────────────────────────

def test_get_app_found(apps_client, mock_db):
    from tests.api.conftest import make_app_row, _APP_ID
    mock_db.queue(row=make_app_row())
    r = apps_client.get(f"/apps/{_APP_ID}")
    assert r.status_code == 200
    assert r.json()["id"] == str(_APP_ID)


def test_get_app_not_found_returns_404(apps_client, mock_db):
    import uuid
    mock_db.queue(row=None)
    r = apps_client.get(f"/apps/{uuid.uuid4()}")
    assert r.status_code == 404


def test_get_app_invalid_uuid_returns_400(apps_client, mock_db):
    r = apps_client.get("/apps/not-a-uuid")
    assert r.status_code == 400


# ─── PATCH /apps/{app_id} ────────────────────────────────────────────────────

def test_update_app_success(apps_client, mock_db):
    from tests.api.conftest import make_app_row, _APP_ID
    # 1st execute: SELECT existing row
    mock_db.queue(row=make_app_row())
    # 2nd execute: UPDATE
    mock_db.queue(rowcount=1)
    # 3rd execute: SELECT updated row
    updated_row = make_app_row(name="Updated Name")
    mock_db.queue(row=updated_row)

    r = apps_client.patch(f"/apps/{_APP_ID}", json={"name": "Updated Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "Updated Name"


def test_update_app_not_found_returns_404(apps_client, mock_db):
    import uuid
    mock_db.queue(row=None)
    r = apps_client.patch(f"/apps/{uuid.uuid4()}", json={"name": "New"})
    assert r.status_code == 404


def test_update_app_no_fields_returns_current_state(apps_client, mock_db):
    """PATCH with empty body should return the unchanged app."""
    from tests.api.conftest import make_app_row, _APP_ID
    mock_db.queue(row=make_app_row())
    r = apps_client.patch(f"/apps/{_APP_ID}", json={})
    assert r.status_code == 200


def test_update_app_invalid_uuid_returns_400(apps_client, mock_db):
    r = apps_client.patch("/apps/not-a-uuid", json={"name": "X"})
    assert r.status_code == 400


# ─── DELETE /apps/{app_id} ───────────────────────────────────────────────────

def test_delete_app_success_returns_204(apps_client, mock_db):
    from tests.api.conftest import _APP_ID
    mock_db.queue(rowcount=1)
    r = apps_client.delete(f"/apps/{_APP_ID}")
    assert r.status_code == 204


def test_delete_app_not_found_or_already_inactive_returns_404(apps_client, mock_db):
    import uuid
    mock_db.queue(rowcount=0)
    r = apps_client.delete(f"/apps/{uuid.uuid4()}")
    assert r.status_code == 404


def test_delete_app_invalid_uuid_returns_400(apps_client, mock_db):
    r = apps_client.delete("/apps/not-a-uuid")
    assert r.status_code == 400
