"""In-memory work unit store for local development and tests."""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from deerflow.work.units.store.base import WorkUnitStore
from deerflow.utils.time import coerce_iso

_NULLABLE_UPDATE_FIELDS = {
    "description",
    "assignee_ref",
    "reporter_ref",
    "due_at",
    "workflow_id",
    "thread_id",
    "run_id",
    "source",
    "external_type",
    "external_ref",
    "external_url",
}


class MemoryWorkUnitStore(WorkUnitStore):
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _now() -> str:
        return coerce_iso(datetime.now(UTC))

    @staticmethod
    def _copy(row: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(row)

    async def create(
        self,
        *,
        title: str,
        description: str | None = None,
        status: str = "backlog",
        priority: str = "P2",
        assignee_ref: str | None = None,
        reporter_ref: str | None = None,
        due_at: str | None = None,
        workflow_id: str | None = None,
        thread_id: str | None = None,
        run_id: str | None = None,
        source_type: str = "local",
        source: str | None = None,
        external_type: str | None = None,
        external_ref: str | None = None,
        external_url: str | None = None,
        labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
        work_unit_id: str | None = None,
    ) -> dict[str, Any]:
        now = self._now()
        row = {
            "work_unit_id": work_unit_id or str(uuid.uuid4()),
            "title": title,
            "description": description,
            "status": status,
            "priority": priority,
            "assignee_ref": assignee_ref,
            "reporter_ref": reporter_ref,
            "due_at": due_at,
            "workflow_id": workflow_id,
            "thread_id": thread_id,
            "run_id": run_id,
            "source_type": source_type,
            "source": source,
            "external_type": external_type,
            "external_ref": external_ref,
            "external_url": external_url,
            "labels": list(labels or []),
            "metadata": dict(metadata or {}),
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        self._items[row["work_unit_id"]] = row
        self._events[row["work_unit_id"]] = []
        return self._copy(row)

    async def get(self, work_unit_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
        row = self._items.get(work_unit_id)
        if row is None:
            return None
        if user_id is not None and row.get("user_id") != user_id:
            return None
        return self._copy(row)

    async def list(
        self,
        *,
        status: str | None = None,
        workflow_id: str | None = None,
        thread_id: str | None = None,
        run_id: str | None = None,
        source_type: str | None = None,
        source: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = list(self._items.values())
        filters = {
            "status": status,
            "workflow_id": workflow_id,
            "thread_id": thread_id,
            "run_id": run_id,
            "source_type": source_type,
            "source": source,
            "user_id": user_id,
        }
        for key, expected in filters.items():
            if expected is not None:
                rows = [row for row in rows if row.get(key) == expected]
        rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
        return [self._copy(row) for row in rows[:limit]]

    async def update(self, work_unit_id: str, *, user_id: str | None = None, **kwargs: Any) -> dict[str, Any] | None:
        row = self._items.get(work_unit_id)
        if row is None:
            return None
        if user_id is not None and row.get("user_id") != user_id:
            return None
        for key, value in kwargs.items():
            if key == "metadata":
                row["metadata"] = {**(row.get("metadata") or {}), **(value or {})}
            elif key == "labels":
                row["labels"] = list(value or [])
            elif value is None:
                if key in _NULLABLE_UPDATE_FIELDS:
                    row[key] = None
            else:
                row[key] = value
        row["updated_at"] = self._now()
        return self._copy(row)

    async def append_event(
        self,
        work_unit_id: str,
        *,
        event_type: str,
        actor_ref: str | None = None,
        workflow_id: str | None = None,
        run_id: str | None = None,
        content: Any | None = None,
        metadata: dict[str, Any] | None = None,
        work_event_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any] | None:
        if work_unit_id not in self._items:
            return None
        events = self._events.setdefault(work_unit_id, [])
        row = {
            "work_event_id": work_event_id or str(uuid.uuid4()),
            "work_unit_id": work_unit_id,
            "seq": len(events) + 1,
            "event_type": event_type,
            "actor_ref": actor_ref,
            "workflow_id": workflow_id,
            "run_id": run_id,
            "content": content,
            "metadata": dict(metadata or {}),
            "created_at": created_at or self._now(),
        }
        events.append(row)
        return self._copy(row)

    async def list_events(self, work_unit_id: str, *, event_types: list[str] | None = None, limit: int = 500) -> list[dict[str, Any]]:
        rows = list(self._events.get(work_unit_id, []))
        if event_types:
            allowed = set(event_types)
            rows = [row for row in rows if row.get("event_type") in allowed]
        return [self._copy(row) for row in rows[:limit]]
