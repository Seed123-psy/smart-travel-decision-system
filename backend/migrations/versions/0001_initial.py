"""Create the four P0 tables and their version/ownership constraints.

Revision ID: 0001_initial
Revises: None
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

TABLE_OPTIONS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


def upgrade() -> None:
    # No current-version FK yet: trip_versions depends on trips itself.
    op.create_table(
        "trips",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("destination", sa.String(100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("travelers", sa.Integer(), nullable=False),
        sa.Column("budget_total", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="CNY", nullable=False),
        sa.Column(
            "budget_scope", sa.String(32), server_default="destination_only", nullable=False
        ),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("travelers BETWEEN 1 AND 10", name="ck_trips_travelers"),
        sa.CheckConstraint("budget_total > 0", name="ck_trips_budget_total"),
        sa.CheckConstraint("end_date >= start_date", name="ck_trips_date_order"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_trips_currency"),
        sa.CheckConstraint(
            "budget_scope = 'destination_only'", name="ck_trips_budget_scope"
        ),
        sa.CheckConstraint(
            "current_version IS NULL OR current_version > 0", name="ck_trips_current_version"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trips"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_trips_created_at", "trips", ["created_at"])
    op.create_index("ix_trips_id_current_version", "trips", ["id", "current_version"])

    op.create_table(
        "planning_tasks",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("trip_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("stage", sa.String(16), server_default="validating", nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("deadline_at", sa.DateTime(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'degraded', 'failed')",
            name="ck_planning_tasks_status",
        ),
        sa.CheckConstraint(
            "stage IN ('validating', 'collecting', 'planning', 'checking', 'persisting')",
            name="ck_planning_tasks_stage",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"],
            name="fk_planning_tasks_trip_id_trips", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_planning_tasks"),
        **TABLE_OPTIONS,
    )
    op.create_index(
        "ix_planning_tasks_trip_created_at", "planning_tasks", ["trip_id", "created_at"]
    )
    op.create_index("ix_planning_tasks_status", "planning_tasks", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("attempt > 0", name="ck_agent_runs_attempt"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'degraded', 'failed', 'skipped')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_agent_runs_duration_ms"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["planning_tasks.id"],
            name="fk_agent_runs_task_id_planning_tasks", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.UniqueConstraint("task_id", "agent_name", "attempt", name="uq_agent_runs_attempt"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_agent_runs_task_created_at", "agent_runs", ["task_id", "created_at"])

    op.create_table(
        "trip_versions",
        sa.Column("trip_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_version", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(100), server_default="initial", nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("validation_json", sa.JSON(), nullable=False),
        sa.Column("budget_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_trip_versions_version"),
        sa.CheckConstraint(
            "parent_version IS NULL OR (parent_version > 0 AND parent_version < version)",
            name="ck_trip_versions_parent_version",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"],
            name="fk_trip_versions_trip_id_trips", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("trip_id", "version", name="pk_trip_versions"),
        **TABLE_OPTIONS,
    )
    op.create_index("ix_trip_versions_created_at", "trip_versions", ["created_at"])
    op.create_foreign_key(
        "fk_trips_current_version", "trips", "trip_versions",
        ["id", "current_version"], ["trip_id", "version"],
    )


def downgrade() -> None:
    # Drop the circular reference before dropping either owner or snapshots.
    op.drop_constraint("fk_trips_current_version", "trips", type_="foreignkey")
    op.drop_table("trip_versions")
    op.drop_table("agent_runs")
    op.drop_table("planning_tasks")
    op.drop_table("trips")
