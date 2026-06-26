"""Work Unit runtime action tool.

The Work Module owns generic work-unit persistence. This tool is intentionally
bound to a single work unit at construction time so agent runs can mutate only
the unit that the runtime surface explicitly attached to the invocation.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.work_units import WorkUnitRepository
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.work.units.schemas import WorkUnitPriority, WorkUnitStatus

logger = logging.getLogger(__name__)

_StatusLiteral = Literal["backlog", "ready", "in_progress", "blocked", "review", "done", "closed", "cancelled"]
_PriorityLiteral = Literal["P0", "P1", "P2", "P3", "P4"]
WorkUnitToolRuntime = ToolRuntime[dict[str, Any], Any]


class _WorkUnitActionInput(BaseModel):
    action: Literal["get", "update_status"] = Field(
        description="Action to perform on the current bound Work Unit.",
    )
    status: _StatusLiteral | None = Field(
        default=None,
        description="New status when action is update_status.",
    )
    note: str | None = Field(
        default=None,
        description="Short reason or execution note to record in the Work Unit event log.",
    )


def _public_work_unit(row: dict) -> dict:
    return {
        "work_unit_id": row.get("work_unit_id"),
        "title": row.get("title"),
        "description": row.get("description"),
        "status": row.get("status"),
        "priority": row.get("priority"),
        "assignee_ref": row.get("assignee_ref"),
        "workflow_id": row.get("workflow_id"),
        "thread_id": row.get("thread_id"),
        "run_id": row.get("run_id"),
        "labels": row.get("labels") or [],
        "updated_at": row.get("updated_at"),
    }


def _allowed_statuses() -> set[str]:
    return {item.value for item in WorkUnitStatus}


def _allowed_priorities() -> set[str]:
    return {item.value for item in WorkUnitPriority}


def _normalize_status(status: str) -> str:
    normalized = status.lower()
    allowed_statuses = _allowed_statuses()
    if normalized not in allowed_statuses:
        raise ValueError(f"Invalid Work Unit status: {status}. Allowed statuses: {', '.join(sorted(allowed_statuses))}.")
    return normalized


def _validate_priority(priority: str) -> str:
    allowed_priorities = _allowed_priorities()
    if priority not in allowed_priorities:
        raise ValueError(f"Invalid Work Unit priority: {priority}. Allowed priorities: {', '.join(sorted(allowed_priorities))}.")
    return priority


def _runtime_actor_ref(runtime: WorkUnitToolRuntime | None) -> str:
    context = getattr(runtime, "context", None)
    if isinstance(context, dict):
        agent_name = str(context.get("agent_name") or "").strip()
        if agent_name:
            return f"agent:{agent_name}"
    return "agent:lead_agent"


async def _work_units_action(
    *,
    runtime: WorkUnitToolRuntime | None,
    action: str,
    work_unit_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str = "P2",
    assignee_ref: str | None = None,
    workflow_id: str | None = None,
    thread_id: str | None = None,
    run_id: str | None = None,
    labels: list[str] | None = None,
    note: str | None = None,
    limit: int = 20,
) -> dict:
    session_factory = get_session_factory()
    if session_factory is None:
        return {
            "ok": False,
            "error": "Work Unit actions require a database-backed Work Module. The current persistence backend is memory.",
        }

    repo = WorkUnitRepository(session_factory)
    user_id = resolve_runtime_user_id(runtime)
    actor_ref = _runtime_actor_ref(runtime)

    if action == "create":
        if not title or not title.strip():
            return {"ok": False, "error": "title is required when action is create."}
        try:
            initial_status = _normalize_status(status or WorkUnitStatus.BACKLOG.value)
            initial_priority = _validate_priority(priority)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        row = await repo.create(
            title=title.strip(),
            description=description,
            status=initial_status,
            priority=initial_priority,
            assignee_ref=assignee_ref,
            reporter_ref=actor_ref,
            workflow_id=workflow_id,
            thread_id=thread_id,
            run_id=run_id,
            labels=labels,
            user_id=user_id,
            source_type="api",
            source="agent_tool",
        )
        event = await repo.append_event(
            row["work_unit_id"],
            event_type="work_unit.created",
            actor_ref=actor_ref,
            workflow_id=row.get("workflow_id"),
            run_id=row.get("run_id"),
            content={"title": row["title"], "status": row["status"], "priority": row["priority"], "note": note},
            metadata={"source": "agent_tool"},
        )
        return {"ok": True, "work_unit": _public_work_unit(row), "event": event}

    if action == "list":
        try:
            status_filter = _normalize_status(status) if status else None
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        rows = await repo.list(
            status=status_filter,
            workflow_id=workflow_id,
            thread_id=thread_id,
            run_id=run_id,
            user_id=user_id,
            limit=max(1, min(limit, 50)),
        )
        return {"ok": True, "work_units": [_public_work_unit(row) for row in rows]}

    if not work_unit_id:
        return {"ok": False, "error": "work_unit_id is required for this action."}

    current = await repo.get(work_unit_id, user_id=user_id)
    if current is None:
        return {"ok": False, "error": f"Work Unit {work_unit_id} was not found."}

    if action == "get":
        return {"ok": True, "work_unit": _public_work_unit(current)}

    if action != "update_status":
        return {"ok": False, "error": f"Unsupported Work Unit action: {action}"}

    if not status:
        return {"ok": False, "error": "status is required when action is update_status."}

    try:
        normalized_status = _normalize_status(status)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    previous_status = current.get("status")
    updated = await repo.update(work_unit_id, user_id=user_id, status=normalized_status)
    if updated is None:
        return {"ok": False, "error": f"Work Unit {work_unit_id} disappeared before update."}
    event = await repo.append_event(
        work_unit_id,
        event_type="work_unit.status_changed" if previous_status != normalized_status else "work_unit.observed",
        actor_ref=actor_ref,
        workflow_id=workflow_id or updated.get("workflow_id"),
        run_id=run_id or updated.get("run_id"),
        content={"previous_status": previous_status, "status": normalized_status, "note": note},
        metadata={"source": "agent_tool"},
    )
    return {
        "ok": True,
        "changed": previous_status != normalized_status,
        "work_unit": _public_work_unit(updated),
        "event": event,
    }


@tool("work_units", parse_docstring=True)
async def work_units_tool(
    runtime: WorkUnitToolRuntime,
    action: Literal["create", "list", "get", "update_status"],
    work_unit_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    status: _StatusLiteral | None = None,
    priority: _PriorityLiteral = "P2",
    assignee_ref: str | None = None,
    workflow_id: str | None = None,
    thread_id: str | None = None,
    run_id: str | None = None,
    labels: list[str] | None = None,
    note: str | None = None,
    limit: int = 20,
) -> dict:
    """Create, read, list, or update generic Work Units.

    Args:
        action: Operation to perform. Use create for planning new work, list to inspect current work, get for one Work Unit, or update_status after actual progress.
        work_unit_id: Existing Work Unit id for get or update_status.
        title: Short title when creating a Work Unit.
        description: Optional objective, next action, or acceptance context.
        status: Optional status filter for list, initial status for create, or new status for update_status.
        priority: Priority for newly-created Work Units.
        assignee_ref: Optional user, team, agent, or external assignee reference.
        workflow_id: Optional durable workflow id to link or filter.
        thread_id: Optional DeerFlow thread id to link or filter.
        run_id: Optional DeerFlow run id to link or filter.
        labels: Optional labels for newly-created Work Units.
        note: Optional audit note for created or updated Work Units.
        limit: Maximum rows for list, capped at 50.
    """

    return await _work_units_action(
        runtime=runtime,
        action=action,
        work_unit_id=work_unit_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        assignee_ref=assignee_ref,
        workflow_id=workflow_id,
        thread_id=thread_id,
        run_id=run_id,
        labels=labels,
        note=note,
        limit=limit,
    )


def build_work_unit_tool(
    *,
    work_unit_id: str,
    actor_ref: str = "agent:lead_agent",
    user_id: str | None = None,
    workflow_id: str | None = None,
    run_id: str | None = None,
) -> BaseTool:
    """Build a tool scoped to one runtime-bound Work Unit."""

    bound_work_unit_id = work_unit_id

    async def _work_unit(action: str, status: str | None = None, note: str | None = None) -> dict:
        """Read or update the current Work Unit bound to this agent run."""

        session_factory = get_session_factory()
        if session_factory is None:
            return {
                "ok": False,
                "error": "Work Unit actions require a database-backed Work Module. The current persistence backend is memory.",
            }

        repo = WorkUnitRepository(session_factory)
        current = await repo.get(bound_work_unit_id, user_id=user_id)
        if current is None:
            return {"ok": False, "error": f"Work Unit {bound_work_unit_id} was not found."}

        if action == "get":
            return {"ok": True, "work_unit": _public_work_unit(current)}

        if action != "update_status":
            return {"ok": False, "error": f"Unsupported Work Unit action: {action}"}

        if not status:
            return {"ok": False, "error": "status is required when action is update_status."}

        normalized_status = status.lower()
        allowed_statuses = _allowed_statuses()
        if normalized_status not in allowed_statuses:
            return {
                "ok": False,
                "error": f"Invalid Work Unit status: {status}. Allowed statuses: {', '.join(sorted(allowed_statuses))}.",
            }

        previous_status = current.get("status")
        if previous_status == normalized_status:
            event = await repo.append_event(
                bound_work_unit_id,
                event_type="work_unit.observed",
                actor_ref=actor_ref,
                workflow_id=workflow_id or current.get("workflow_id"),
                run_id=run_id or current.get("run_id"),
                content={
                    "status": normalized_status,
                    "note": note,
                },
                metadata={"source": "agent_tool"},
            )
            return {
                "ok": True,
                "changed": False,
                "work_unit": _public_work_unit(current),
                "event": event,
            }

        updated = await repo.update(bound_work_unit_id, user_id=user_id, status=normalized_status)
        if updated is None:
            return {"ok": False, "error": f"Work Unit {bound_work_unit_id} disappeared before update."}

        event = await repo.append_event(
            bound_work_unit_id,
            event_type="work_unit.status_changed",
            actor_ref=actor_ref,
            workflow_id=workflow_id or updated.get("workflow_id"),
            run_id=run_id or updated.get("run_id"),
            content={
                "previous_status": previous_status,
                "status": normalized_status,
                "note": note,
            },
            metadata={"source": "agent_tool"},
        )
        logger.info(
            "Work Unit %s status changed by %s: %s -> %s",
            bound_work_unit_id,
            actor_ref,
            previous_status,
            normalized_status,
        )
        return {
            "ok": True,
            "changed": True,
            "work_unit": _public_work_unit(updated),
            "event": event,
        }

    return StructuredTool.from_function(
        name="work_unit",
        description=(
            "Read or update the current Work Unit bound to this run. "
            "Use this tool before claiming that a Work Unit status has changed. "
            "It can only act on the Work Unit attached by the runtime surface."
        ),
        coroutine=_work_unit,
        args_schema=_WorkUnitActionInput,
    )
