"""Generic work unit endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.gateway.authz import require_permission
from app.gateway.deps import get_work_unit_store
from app.gateway.internal_auth import get_trusted_internal_owner_user_id
from deerflow.work.units.schemas import WorkUnitPriority, WorkUnitSourceType, WorkUnitStatus

router = APIRouter(prefix="/api/work-units", tags=["work-units"])


class WorkUnitCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    status: str = "backlog"
    priority: str = "P2"
    assignee_ref: str | None = None
    reporter_ref: str | None = None
    due_at: str | None = None
    workflow_id: str | None = None
    thread_id: str | None = None
    run_id: str | None = None
    source_type: str = "local"
    source: str | None = None
    external_type: str | None = None
    external_ref: str | None = None
    external_url: str | None = None
    labels: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    work_unit_id: str | None = None


class WorkUnitUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_ref: str | None = None
    reporter_ref: str | None = None
    due_at: str | None = None
    workflow_id: str | None = None
    thread_id: str | None = None
    run_id: str | None = None
    source_type: str | None = None
    source: str | None = None
    external_type: str | None = None
    external_ref: str | None = None
    external_url: str | None = None
    labels: list[str] | None = None
    metadata: dict[str, Any] | None = None


def _changed_fields(payload: WorkUnitUpdateRequest) -> dict[str, Any]:
    return payload.model_dump(exclude_unset=True)


def _enum_values(enum_cls: type) -> set[str]:
    return {item.value for item in enum_cls}


def _validate_enum_field(field: str, value: str | None, enum_cls: type) -> str | None:
    if value is None:
        return None
    normalized = value.lower() if field in {"status", "source_type"} else value
    allowed = _enum_values(enum_cls)
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field}: {value}. Allowed values: {', '.join(sorted(allowed))}",
        )
    return normalized


def _validate_work_unit_fields(values: dict[str, Any]) -> dict[str, Any]:
    if "status" in values:
        values["status"] = _validate_enum_field("status", values.get("status"), WorkUnitStatus)
    if "priority" in values:
        values["priority"] = _validate_enum_field("priority", values.get("priority"), WorkUnitPriority)
    if "source_type" in values:
        values["source_type"] = _validate_enum_field("source_type", values.get("source_type"), WorkUnitSourceType)
    return values


def _owner_user_id(request: Request) -> str | None:
    internal_owner = get_trusted_internal_owner_user_id(request)
    if internal_owner:
        return internal_owner
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None)
    return str(user_id) if user_id is not None else None


@router.get("")
@require_permission("work", "read")
async def list_work_units(
    request: Request,
    status: str | None = Query(default=None),
    workflow_id: str | None = Query(default=None),
    thread_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """List generic work units for board and PM-adapter views."""
    store = get_work_unit_store(request)
    rows = await store.list(
        status=status,
        workflow_id=workflow_id,
        thread_id=thread_id,
        run_id=run_id,
        source_type=source_type,
        source=source,
        user_id=_owner_user_id(request),
        limit=limit,
    )
    return {"data": rows}


@router.post("")
@require_permission("work", "create")
async def create_work_unit(payload: WorkUnitCreateRequest, request: Request) -> dict:
    """Create a local or externally-mapped work unit."""
    store = get_work_unit_store(request)
    values = _validate_work_unit_fields(payload.model_dump())
    row = await store.create(**values, user_id=_owner_user_id(request))
    await store.append_event(
        row["work_unit_id"],
        event_type="work_unit.created",
        actor_ref=payload.reporter_ref or _owner_user_id(request),
        workflow_id=row.get("workflow_id"),
        run_id=row.get("run_id"),
        content={"title": row["title"], "status": row["status"], "priority": row["priority"]},
    )
    return row


@router.get("/{work_unit_id}")
@require_permission("work", "read")
async def get_work_unit(work_unit_id: str, request: Request) -> dict:
    """Fetch one work unit."""
    store = get_work_unit_store(request)
    row = await store.get(work_unit_id, user_id=_owner_user_id(request))
    if row is None:
        raise HTTPException(status_code=404, detail=f"Work unit {work_unit_id} not found")
    return row


@router.patch("/{work_unit_id}")
@require_permission("work", "update")
async def update_work_unit(work_unit_id: str, payload: WorkUnitUpdateRequest, request: Request) -> dict:
    """Update a work unit projection."""
    changes = _changed_fields(payload)
    if not changes:
        raise HTTPException(status_code=400, detail="No work unit fields provided")
    changes = _validate_work_unit_fields(changes)
    store = get_work_unit_store(request)
    owner_user_id = _owner_user_id(request)
    previous = await store.get(work_unit_id, user_id=owner_user_id)
    if previous is None:
        raise HTTPException(status_code=404, detail=f"Work unit {work_unit_id} not found")
    row = await store.update(work_unit_id, user_id=owner_user_id, **changes)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Work unit {work_unit_id} not found")

    event_type = "work_unit.status_changed" if "status" in changes and changes["status"] != previous.get("status") else "work_unit.updated"
    await store.append_event(
        work_unit_id,
        event_type=event_type,
        workflow_id=row.get("workflow_id"),
        run_id=row.get("run_id"),
        content={"changes": changes, "previous_status": previous.get("status"), "status": row.get("status")},
    )
    return row


@router.get("/{work_unit_id}/events")
@require_permission("work", "read")
async def list_work_events(
    work_unit_id: str,
    request: Request,
    event_type: list[str] | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
) -> dict:
    """List work unit activity events."""
    store = get_work_unit_store(request)
    item = await store.get(work_unit_id, user_id=_owner_user_id(request))
    if item is None:
        raise HTTPException(status_code=404, detail=f"Work unit {work_unit_id} not found")
    events = await store.list_events(work_unit_id, event_types=event_type, limit=limit)
    return {"work_unit": item, "events": events}
