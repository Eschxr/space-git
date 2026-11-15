"""Durable commits of complete saved camera sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "camera_commits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("capture_id", sa.Uuid(), nullable=False),
        sa.Column("source_session_id", sa.String(200), nullable=False),
        sa.Column("message", sa.String(2000), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("id", "environment_id"),
        sa.UniqueConstraint("source_session_id"),
        sa.UniqueConstraint("capture_id"),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"]),
        sa.ForeignKeyConstraint(
            ["capture_id", "environment_id"], ["captures.id", "captures.environment_id"]
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "environment_id"], ["camera_commits.id", "camera_commits.environment_id"]
        ),
    )
    op.execute(
        "CREATE TRIGGER immutable_camera_commits BEFORE UPDATE OR DELETE ON camera_commits "
        "FOR EACH ROW EXECUTE FUNCTION immutable_evidence()"
    )


def downgrade():
    op.drop_table("camera_commits")
