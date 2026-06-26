"""Tests for generic work unit endpoints."""

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from uuid import UUID

from app.gateway.auth.models import User
from app.gateway.routers import work_units
from deerflow.work.units.store.memory import MemoryWorkUnitStore


def _make_client(store: MemoryWorkUnitStore) -> TestClient:
    user = User(
        email="work-router@example.com",
        password_hash="x",
        system_role="user",
        id=UUID("11111111-1111-1111-1111-111111111111"),
    )
    app = make_authed_test_app(user_factory=lambda: user)
    app.state.work_unit_store = store
    app.include_router(work_units.router)
    return TestClient(app)


def test_work_unit_api_create_list_update_and_events():
    store = MemoryWorkUnitStore()

    with _make_client(store) as client:
        created = client.post(
            "/api/work-units",
            json={
                "work_unit_id": "work-api-1",
                "title": "Review workflow trace",
                "status": "backlog",
                "priority": "P1",
                "workflow_id": "wf-api-1",
                "run_id": "run-api-1",
                "labels": ["runtime"],
            },
        )
        listed = client.get("/api/work-units", params={"status": "backlog", "workflow_id": "wf-api-1"})
        updated = client.patch("/api/work-units/work-api-1", json={"status": "in_progress"})
        events = client.get("/api/work-units/work-api-1/events")

    assert created.status_code == 200
    assert created.json()["work_unit_id"] == "work-api-1"
    assert [row["work_unit_id"] for row in listed.json()["data"]] == ["work-api-1"]
    assert updated.json()["status"] == "in_progress"
    assert [event["event_type"] for event in events.json()["events"]] == [
        "work_unit.created",
        "work_unit.status_changed",
    ]


def test_work_unit_api_missing_and_empty_update():
    store = MemoryWorkUnitStore()

    with _make_client(store) as client:
        missing = client.get("/api/work-units/missing")
        empty_update = client.patch("/api/work-units/missing", json={})

    assert missing.status_code == 404
    assert empty_update.status_code == 400


def test_work_unit_api_rejects_invalid_enum_values():
    store = MemoryWorkUnitStore()

    with _make_client(store) as client:
        created = client.post(
            "/api/work-units",
            json={
                "work_unit_id": "work-api-invalid",
                "title": "Invalid priority",
                "priority": "urgent",
            },
        )
        valid = client.post(
            "/api/work-units",
            json={
                "work_unit_id": "work-api-valid",
                "title": "Valid work unit",
            },
        )
        updated = client.patch("/api/work-units/work-api-valid", json={"status": "shipped"})

    assert created.status_code == 400
    assert "Invalid priority" in created.json()["detail"]
    assert valid.status_code == 200
    assert updated.status_code == 400
    assert "Invalid status" in updated.json()["detail"]
