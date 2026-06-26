"""Work Unit runtime action tool.

The Work Module owns generic work-unit persistence. This tool is intentionally
bound to a single work unit at construction time so agent runs can mutate only
the unit that the runtime surface explicitly attached to the invocation.
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.work_units import WorkUnitRepository
from deerflow.work.units.schemas import WorkUnitStatus

logger = logging.getLogger(__name__)

_StatusLiteral = Literal["backlog", "ready", "in_progress", "blocked", "review", "done", "closed", "cancelled"]


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
        allowed_statuses = {item.value for item in WorkUnitStatus}
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
