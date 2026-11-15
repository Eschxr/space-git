"""Append-only review decisions and immutable revision provenance."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("revisions", sa.Column("provenance", JSONB, nullable=True))
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(), nullable=False),
        sa.Column("new_status", sa.String(), nullable=False),
        sa.Column("previous_reason", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(200), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"]),
        sa.ForeignKeyConstraint(
            ["proposal_id", "environment_id"],
            ["change_proposals.id", "change_proposals.environment_id"],
        ),
        sa.UniqueConstraint("id", "environment_id"),
        sa.UniqueConstraint("proposal_id", "idempotency_key"),
        sa.CheckConstraint(
            "previous_status IN ('proposed','accepted','rejected','needs_review')",
            name="previous_status_values",
        ),
        sa.CheckConstraint(
            "new_status IN ('accepted','rejected','needs_review')", name="new_status_values"
        ),
    )
    op.execute(
        "CREATE TRIGGER immutable_review_decisions BEFORE UPDATE OR DELETE ON review_decisions "
        "FOR EACH ROW EXECUTE FUNCTION immutable_evidence()"
    )


def downgrade():
    op.drop_table("review_decisions")
    op.drop_column("revisions", "provenance")
