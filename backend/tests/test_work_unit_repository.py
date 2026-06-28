"""Tests for generic work unit stores."""

import pytest

from deerflow.persistence.work_units import WorkUnitRepository
from deerflow.tools.builtins.work_unit_tool import build_work_unit_tool
from deerflow.work.units.store.memory import MemoryWorkUnitStore


async def _make_repo(tmp_path):
    from deerflow.persistence.engine import get_session_factory, init_engine

    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    await init_engine("sqlite", url=url, sqlite_dir=str(tmp_path))
    return WorkUnitRepository(get_session_factory())


async def _cleanup():
    from deerflow.persistence.engine import close_engine

    await close_engine()


@pytest.mark.anyio
async def test_memory_work_unit_store_create_update_and_events():
    store = MemoryWorkUnitStore()
    item = await store.create(
        work_unit_id="work-1",
        title="Investigate durable run trace",
        status="backlog",
        priority="P1",
        workflow_id="wf-1",
        labels=["runtime"],
    )
    created = await store.append_event("work-1", event_type="work_unit.created", content={"title": item["title"]})
    updated = await store.update("work-1", status="in_progress", metadata={"source": "test"})
    status_changed = await store.append_event("work-1", event_type="work_unit.status_changed")
    rows = await store.list(status="in_progress", workflow_id="wf-1")
    events = await store.list_events("work-1")

    assert item["work_unit_id"] == "work-1"
    assert updated["status"] == "in_progress"
    assert updated["metadata"] == {"source": "test"}
    assert [row["work_unit_id"] for row in rows] == ["work-1"]
    assert created["seq"] == 1
    assert status_changed["seq"] == 2
    assert [event["event_type"] for event in events] == ["work_unit.created", "work_unit.status_changed"]


@pytest.mark.anyio
async def test_memory_work_unit_store_update_is_user_scoped():
    store = MemoryWorkUnitStore()
    await store.create(
        work_unit_id="work-user-scope",
        title="Scoped update",
        user_id="owner-1",
    )

    rejected = await store.update("work-user-scope", user_id="owner-2", status="ready")
    accepted = await store.update("work-user-scope", user_id="owner-1", status="ready")

    assert rejected is None
    assert accepted["status"] == "ready"


@pytest.mark.anyio
async def test_memory_work_unit_store_can_clear_nullable_fields():
    store = MemoryWorkUnitStore()
    await store.create(
        work_unit_id="work-clear-memory",
        title="Clear nullable refs",
        assignee_ref="lead_agent",
        thread_id="thread-1",
        external_ref="EXT-1",
        labels=["stale"],
    )

    updated = await store.update(
        "work-clear-memory",
        assignee_ref=None,
        thread_id=None,
        external_ref=None,
        labels=None,
    )

    assert updated["assignee_ref"] is None
    assert updated["thread_id"] is None
    assert updated["external_ref"] is None
    assert updated["labels"] == []


class TestWorkUnitRepository:
    @pytest.mark.anyio
    async def test_create_list_update_and_events(self, tmp_path):
        repo = await _make_repo(tmp_path)
        try:
            item = await repo.create(
                work_unit_id="work-sql-1",
                title="Connect board card to workflow",
                status="ready",
                priority="P2",
                workflow_id="wf-sql-1",
                thread_id="thread-1",
                run_id="run-1",
                labels=["board"],
                metadata={"adapter": "local"},
            )
            event = await repo.append_event(
                "work-sql-1",
                event_type="work_unit.created",
                workflow_id="wf-sql-1",
                run_id="run-1",
            )
            updated = await repo.update("work-sql-1", status="done", metadata={"closed": True})
            rows = await repo.list(status="done", workflow_id="wf-sql-1")
            events = await repo.list_events("work-sql-1")

            assert item["work_unit_id"] == "work-sql-1"
            assert updated["status"] == "done"
            assert updated["metadata"] == {"adapter": "local", "closed": True}
            assert [row["work_unit_id"] for row in rows] == ["work-sql-1"]
            assert event["seq"] == 1
            assert events[0]["event_type"] == "work_unit.created"
        finally:
            await _cleanup()

    @pytest.mark.anyio
    async def test_update_is_user_scoped(self, tmp_path):
        repo = await _make_repo(tmp_path)
        try:
            await repo.create(
                work_unit_id="work-sql-scoped",
                title="Scoped SQL update",
                user_id="owner-1",
            )

            rejected = await repo.update("work-sql-scoped", user_id="owner-2", status="ready")
            accepted = await repo.update("work-sql-scoped", user_id="owner-1", status="ready")

            assert rejected is None
            assert accepted["status"] == "ready"
        finally:
            await _cleanup()

    @pytest.mark.anyio
    async def test_update_can_clear_nullable_fields(self, tmp_path):
        repo = await _make_repo(tmp_path)
        try:
            await repo.create(
                work_unit_id="work-sql-clear",
                title="Clear nullable SQL fields",
                assignee_ref="lead_agent",
                thread_id="thread-sql",
                external_ref="EXT-SQL",
                labels=["old"],
            )

            updated = await repo.update(
                "work-sql-clear",
                assignee_ref=None,
                thread_id=None,
                external_ref=None,
                labels=None,
            )

            assert updated["assignee_ref"] is None
            assert updated["thread_id"] is None
            assert updated["external_ref"] is None
            assert updated["labels"] == []
        finally:
            await _cleanup()

    @pytest.mark.anyio
    async def test_runtime_tool_is_bound_to_work_unit_owner(self, tmp_path):
        repo = await _make_repo(tmp_path)
        try:
            await repo.create(
                work_unit_id="work-tool-scoped",
                title="Tool scoped update",
                status="backlog",
                user_id="owner-1",
            )

            other_owner_tool = build_work_unit_tool(
                work_unit_id="work-tool-scoped",
                user_id="owner-2",
                actor_ref="agent:lead_agent",
            )
            rejected = await other_owner_tool.ainvoke({"action": "update_status", "status": "ready"})

            owner_tool = build_work_unit_tool(
                work_unit_id="work-tool-scoped",
                user_id="owner-1",
                actor_ref="agent:lead_agent",
            )
            accepted = await owner_tool.ainvoke({"action": "update_status", "status": "ready", "note": "ready"})

            assert rejected["ok"] is False
            assert accepted["ok"] is True
            assert accepted["work_unit"]["status"] == "ready"
        finally:
            await _cleanup()
