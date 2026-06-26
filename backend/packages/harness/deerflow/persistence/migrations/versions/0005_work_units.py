"""Add work unit module tables.

Revision ID: 0005_work_units
Revises: 0004_workflow_events
Create Date: 2026-06-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_work_units"
down_revision: str | Sequence[str] | None = "0004_workflow_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("work_units"):
        op.create_table(
            "work_units",
            sa.Column("work_unit_id", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=300), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("priority", sa.String(length=8), nullable=False),
            sa.Column("assignee_ref", sa.String(length=256), nullable=True),
            sa.Column("reporter_ref", sa.String(length=256), nullable=True),
            sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("user_id", sa.String(length=64), nullable=True),
            sa.Column("workflow_id", sa.String(length=64), nullable=True),
            sa.Column("thread_id", sa.String(length=64), nullable=True),
            sa.Column("run_id", sa.String(length=64), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("source", sa.String(length=128), nullable=True),
            sa.Column("external_type", sa.String(length=64), nullable=True),
            sa.Column("external_ref", sa.String(length=512), nullable=True),
            sa.Column("external_url", sa.Text(), nullable=True),
            sa.Column("labels_json", sa.JSON(), nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("work_unit_id"),
        )
        with op.batch_alter_table("work_units", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_work_units_assignee_ref"), ["assignee_ref"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_due_at"), ["due_at"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_external_type"), ["external_type"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_priority"), ["priority"], unique=False)
            batch_op.create_index("ix_work_units_priority_updated", ["priority", "updated_at"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_run_id"), ["run_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_source"), ["source"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_source_type"), ["source_type"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_status"), ["status"], unique=False)
            batch_op.create_index("ix_work_units_status_updated", ["status", "updated_at"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_thread_id"), ["thread_id"], unique=False)
            batch_op.create_index("ix_work_units_thread_run", ["thread_id", "run_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_user_id"), ["user_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_units_workflow_id"), ["workflow_id"], unique=False)
            batch_op.create_index(
                "uq_work_units_external_ref",
                ["source_type", "source", "external_ref"],
                unique=True,
                sqlite_where=sa.text("external_ref IS NOT NULL"),
                postgresql_where=sa.text("external_ref IS NOT NULL"),
            )

    if not _table_exists("work_events"):
        op.create_table(
            "work_events",
            sa.Column("work_event_id", sa.String(length=64), nullable=False),
            sa.Column("work_unit_id", sa.String(length=64), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("actor_ref", sa.String(length=256), nullable=True),
            sa.Column("workflow_id", sa.String(length=64), nullable=True),
            sa.Column("run_id", sa.String(length=64), nullable=True),
            sa.Column("content_json", sa.JSON(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["work_unit_id"], ["work_units.work_unit_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("work_event_id"),
            sa.UniqueConstraint("work_unit_id", "seq", name="uq_work_events_unit_seq"),
        )
        with op.batch_alter_table("work_events", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_work_events_created_at"), ["created_at"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_events_event_type"), ["event_type"], unique=False)
            batch_op.create_index("ix_work_events_unit_created", ["work_unit_id", "created_at"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_events_run_id"), ["run_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_events_work_unit_id"), ["work_unit_id"], unique=False)
            batch_op.create_index(batch_op.f("ix_work_events_workflow_id"), ["workflow_id"], unique=False)


def downgrade() -> None:
    if _table_exists("work_events"):
        with op.batch_alter_table("work_events", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_work_events_workflow_id"))
            batch_op.drop_index(batch_op.f("ix_work_events_work_unit_id"))
            batch_op.drop_index(batch_op.f("ix_work_events_run_id"))
            batch_op.drop_index("ix_work_events_unit_created")
            batch_op.drop_index(batch_op.f("ix_work_events_event_type"))
            batch_op.drop_index(batch_op.f("ix_work_events_created_at"))
        op.drop_table("work_events")

    if _table_exists("work_units"):
        with op.batch_alter_table("work_units", schema=None) as batch_op:
            batch_op.drop_index("uq_work_units_external_ref")
            batch_op.drop_index(batch_op.f("ix_work_units_workflow_id"))
            batch_op.drop_index(batch_op.f("ix_work_units_user_id"))
            batch_op.drop_index("ix_work_units_thread_run")
            batch_op.drop_index(batch_op.f("ix_work_units_thread_id"))
            batch_op.drop_index("ix_work_units_status_updated")
            batch_op.drop_index(batch_op.f("ix_work_units_status"))
            batch_op.drop_index(batch_op.f("ix_work_units_source_type"))
            batch_op.drop_index(batch_op.f("ix_work_units_source"))
            batch_op.drop_index(batch_op.f("ix_work_units_run_id"))
            batch_op.drop_index("ix_work_units_priority_updated")
            batch_op.drop_index(batch_op.f("ix_work_units_priority"))
            batch_op.drop_index(batch_op.f("ix_work_units_external_type"))
            batch_op.drop_index(batch_op.f("ix_work_units_due_at"))
            batch_op.drop_index(batch_op.f("ix_work_units_assignee_ref"))
        op.drop_table("work_units")
