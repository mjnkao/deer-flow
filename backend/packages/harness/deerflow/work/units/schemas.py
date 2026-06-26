"""Work unit schema enums."""

from __future__ import annotations

from enum import StrEnum


class WorkUnitStatus(StrEnum):
    BACKLOG = "backlog"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    REVIEW = "review"
    DONE = "done"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class WorkUnitPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class WorkUnitSourceType(StrEnum):
    LOCAL = "local"
    PM_TOOL = "pm_tool"
    CHANNEL = "channel"
    API = "api"
    OTHER = "other"
