"""Environment-specific detector prompt catalogue."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("environments", sa.Column("prompts", JSONB(), nullable=True))


def downgrade():
    op.drop_column("environments", "prompts")
