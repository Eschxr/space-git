"""Durable capture failures and job attempts/progress."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("captures", sa.Column("error", sa.Text(), nullable=True))
    op.add_column("captures", sa.Column("warnings", JSONB(), nullable=False, server_default="[]"))
    op.add_column(
        "processing_runs",
        sa.Column("progress", JSONB(), nullable=False, server_default='{"stage":"queued"}'),
    )
    op.add_column("jobs", sa.Column("run_id", sa.Uuid(), nullable=True))
    op.add_column("jobs", sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"))
    op.create_foreign_key(
        "fk_jobs_run_id_processing_runs",
        "jobs",
        "processing_runs",
        ["run_id", "environment_id"],
        ["id", "environment_id"],
    )
    op.create_check_constraint("ck_jobs_positive_attempt", "jobs", "attempt > 0")


def downgrade():
    op.drop_constraint("ck_jobs_positive_attempt", "jobs", type_="check")
    op.drop_constraint("fk_jobs_run_id_processing_runs", "jobs", type_="foreignkey")
    op.drop_column("jobs", "attempt")
    op.drop_column("jobs", "run_id")
    op.drop_column("processing_runs", "progress")
    op.drop_column("captures", "warnings")
    op.drop_column("captures", "error")
