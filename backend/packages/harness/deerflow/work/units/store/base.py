"""Abstract interface for generic work unit storage."""

from __future__ import annotations

import abc
from typing import Any


class WorkUnitStore(abc.ABC):
    """Storage contract for DeerFlow work units."""

    @abc.abstractmethod
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
        pass

    @abc.abstractmethod
    async def get(self, work_unit_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
        pass

    @abc.abstractmethod
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
        pass

    @abc.abstractmethod
    async def update(
        self,
        work_unit_id: str,
        *,
        user_id: str | None = None,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        assignee_ref: str | None = None,
        reporter_ref: str | None = None,
        due_at: str | None = None,
        workflow_id: str | None = None,
        thread_id: str | None = None,
        run_id: str | None = None,
        source_type: str | None = None,
        source: str | None = None,
        external_type: str | None = None,
        external_ref: str | None = None,
        external_url: str | None = None,
        labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        pass

    @abc.abstractmethod
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
        pass

    @abc.abstractmethod
    async def list_events(self, work_unit_id: str, *, event_types: list[str] | None = None, limit: int = 500) -> list[dict[str, Any]]:
        pass
