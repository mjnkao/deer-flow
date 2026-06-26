"""ORM models for generic work units."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


class WorkUnitRow(Base):
    __tablename__ = "work_units"

    work_unit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="backlog", index=True)
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="P2", index=True)

    assignee_ref: Mapped[str | None] = mapped_column(String(256), index=True)
    reporter_ref: Mapped[str | None] = mapped_column(String(256))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), index=True)

    workflow_id: Mapped[str | None] = mapped_column(String(64), index=True)
    thread_id: Mapped[str | None] = mapped_column(String(64), index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), index=True)

    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="local", index=True)
    source: Mapped[str | None] = mapped_column(String(128), index=True)
    external_type: Mapped[str | None] = mapped_column(String(64), index=True)
    external_ref: Mapped[str | None] = mapped_column(String(512))
    external_url: Mapped[str | None] = mapped_column(Text)

    labels_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (
        Index(
            "uq_work_units_external_ref",
            "source_type",
            "source",
            "external_ref",
            unique=True,
            sqlite_where=text("external_ref IS NOT NULL"),
            postgresql_where=text("external_ref IS NOT NULL"),
        ),
        Index("ix_work_units_status_updated", "status", "updated_at"),
        Index("ix_work_units_priority_updated", "priority", "updated_at"),
        Index("ix_work_units_thread_run", "thread_id", "run_id"),
    )


class WorkEventRow(Base):
    __tablename__ = "work_events"

    work_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    work_unit_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("work_units.work_unit_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_ref: Mapped[str | None] = mapped_column(String(256))
    workflow_id: Mapped[str | None] = mapped_column(String(64), index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    content_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)

    __table_args__ = (
        UniqueConstraint("work_unit_id", "seq", name="uq_work_events_unit_seq"),
        Index("ix_work_events_unit_created", "work_unit_id", "created_at"),
    )
