"""SQLAlchemy-backed work unit repository."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.persistence.work_units.model import WorkEventRow, WorkUnitRow
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


class WorkUnitRepository(WorkUnitStore):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    @staticmethod
    def _safe_json(obj: Any) -> Any:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return {k: WorkUnitRepository._safe_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [WorkUnitRepository._safe_json(v) for v in obj]
        if hasattr(obj, "model_dump"):
            try:
                return obj.model_dump()
            except Exception:
                pass
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)

    @staticmethod
    def _coerce_datetime(value: str | datetime | None) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    @staticmethod
    def _row_to_dict(row: WorkUnitRow) -> dict[str, Any]:
        d = row.to_dict()
        d["labels"] = d.pop("labels_json", []) or []
        d["metadata"] = d.pop("metadata_json", {}) or {}
        for key in ("created_at", "updated_at", "due_at"):
            val = d.get(key)
            if isinstance(val, datetime):
                d[key] = coerce_iso(val)
        return d

    @staticmethod
    def _event_row_to_dict(row: WorkEventRow) -> dict[str, Any]:
        d = row.to_dict()
        d["content"] = d.pop("content_json", None)
        d["metadata"] = d.pop("metadata_json", {}) or {}
        val = d.get("created_at")
        if isinstance(val, datetime):
            d["created_at"] = coerce_iso(val)
        return d

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
        now = datetime.now(UTC)
        row = WorkUnitRow(
            work_unit_id=work_unit_id or str(uuid.uuid4()),
            title=title,
            description=description,
            status=status,
            priority=priority,
            assignee_ref=assignee_ref,
            reporter_ref=reporter_ref,
            due_at=self._coerce_datetime(due_at),
            workflow_id=workflow_id,
            thread_id=thread_id,
            run_id=run_id,
            source_type=source_type,
            source=source,
            external_type=external_type,
            external_ref=external_ref,
            external_url=external_url,
            labels_json=list(labels or []),
            metadata_json=self._safe_json(metadata) or {},
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        async with self._sf() as session:
            session.add(row)
            await session.commit()
            return self._row_to_dict(row)

    async def get(self, work_unit_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(WorkUnitRow, work_unit_id)
            if row is None:
                return None
            if user_id is not None and row.user_id != user_id:
                return None
            return self._row_to_dict(row)

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
        stmt = select(WorkUnitRow)
        filters = {
            WorkUnitRow.status: status,
            WorkUnitRow.workflow_id: workflow_id,
            WorkUnitRow.thread_id: thread_id,
            WorkUnitRow.run_id: run_id,
            WorkUnitRow.source_type: source_type,
            WorkUnitRow.source: source,
            WorkUnitRow.user_id: user_id,
        }
        for column, expected in filters.items():
            if expected is not None:
                stmt = stmt.where(column == expected)
        stmt = stmt.order_by(WorkUnitRow.updated_at.desc()).limit(limit)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._row_to_dict(row) for row in rows]

    async def update(self, work_unit_id: str, *, user_id: str | None = None, **kwargs: Any) -> dict[str, Any] | None:
        async with self._sf() as session:
            row = await session.get(WorkUnitRow, work_unit_id)
            if row is None:
                return None
            if user_id is not None and row.user_id != user_id:
                return None
            values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
            for key, value in kwargs.items():
                if key == "metadata":
                    values["metadata_json"] = {**(row.metadata_json or {}), **(self._safe_json(value) or {})}
                elif key == "labels":
                    values["labels_json"] = list(value or [])
                elif key == "due_at":
                    values["due_at"] = self._coerce_datetime(value)
                elif value is None:
                    if key in _NULLABLE_UPDATE_FIELDS:
                        values[key] = None
                else:
                    values[key] = value
            stmt = update(WorkUnitRow).where(WorkUnitRow.work_unit_id == work_unit_id)
            if user_id is not None:
                stmt = stmt.where(WorkUnitRow.user_id == user_id)
            await session.execute(stmt.values(**values))
            await session.commit()
            updated = await session.get(WorkUnitRow, work_unit_id)
            return self._row_to_dict(updated) if updated is not None else None

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
        async with self._sf() as session:
            item = await session.get(WorkUnitRow, work_unit_id)
            if item is None:
                return None
            max_seq = await session.scalar(select(func.max(WorkEventRow.seq)).where(WorkEventRow.work_unit_id == work_unit_id))
            row = WorkEventRow(
                work_event_id=work_event_id or str(uuid.uuid4()),
                work_unit_id=work_unit_id,
                seq=int(max_seq or 0) + 1,
                event_type=event_type,
                actor_ref=actor_ref,
                workflow_id=workflow_id,
                run_id=run_id,
                content_json=self._safe_json(content),
                metadata_json=self._safe_json(metadata) or {},
                created_at=self._coerce_datetime(created_at) or datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            return self._event_row_to_dict(row)

    async def list_events(self, work_unit_id: str, *, event_types: list[str] | None = None, limit: int = 500) -> list[dict[str, Any]]:
        stmt = select(WorkEventRow).where(WorkEventRow.work_unit_id == work_unit_id)
        if event_types:
            stmt = stmt.where(WorkEventRow.event_type.in_(event_types))
        stmt = stmt.order_by(WorkEventRow.seq.asc()).limit(limit)
        async with self._sf() as session:
            rows = (await session.execute(stmt)).scalars().all()
            return [self._event_row_to_dict(row) for row in rows]
