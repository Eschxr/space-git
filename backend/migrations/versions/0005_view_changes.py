"""Add image-view events and immutable accepted track states; preserve legacy history."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

NEW_TYPES = [
    "added_candidate",
    "moved_2d_candidate",
    "appearance_changed_candidate",
    "unobserved",
    "removed_candidate",
    "possible_relocation",
    "unchanged",
    "appeared_in_view",
    "moved_in_view",
    "appearance_changed",
    "missing_from_view",
    "reappeared",
    "uncertain",
]
OLD_TYPES = NEW_TYPES[:7]
TABLE_SQL = "CREATE TABLE revision_track_snapshots (\n\tid UUID NOT NULL,\n\tenvironment_id UUID NOT NULL,\n\trevision_id UUID NOT NULL,\n\tview_track_id UUID NOT NULL,\n\tcamera_id VARCHAR NOT NULL,\n\tstate JSONB NOT NULL,\n\tCONSTRAINT pk_revision_track_snapshots PRIMARY KEY (id),\n\tCONSTRAINT uq_revision_track_snapshots_id UNIQUE (id, environment_id),\n\tCONSTRAINT fk_revision_track_snapshots_environment_id_environments FOREIGN KEY(environment_id) REFERENCES environments (id),\n\tCONSTRAINT fk_revision_track_snapshots_revision_id_revisions FOREIGN KEY(revision_id, environment_id) REFERENCES revisions (id, environment_id),\n\tCONSTRAINT fk_revision_track_snapshots_view_track_id_view_tracks FOREIGN KEY(view_track_id, environment_id) REFERENCES view_tracks (id, environment_id),\n\tCONSTRAINT ck_revision_track_snapshots_camera_id_values CHECK (camera_id IN ('cam_01', 'cam_02', 'cam_03', 'cam_04')),\n\tCONSTRAINT uq_revision_track_snapshots_revision_id UNIQUE (revision_id, view_track_id)\n)"


def upgrade():
    op.add_column("change_proposals", sa.Column("camera_id", sa.String(), nullable=True))
    op.add_column("change_proposals", sa.Column("view_track_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_change_view_track",
        "change_proposals",
        "view_tracks",
        ["view_track_id", "environment_id"],
        ["id", "environment_id"],
    )
    op.drop_constraint(op.f("ck_change_proposals_type_values"), "change_proposals", type_="check")
    op.create_check_constraint(
        op.f("ck_change_proposals_type_values"),
        "change_proposals",
        "type IN (" + ",".join(repr(v) for v in NEW_TYPES) + ")",
    )
    op.create_check_constraint(
        op.f("ck_change_camera"),
        "change_proposals",
        "camera_id IN ('cam_01','cam_02','cam_03','cam_04')",
    )
    for name in ("idempotency_key", "request_hash"):
        op.add_column("revisions", sa.Column(name, sa.String(), nullable=True))
    op.create_index(
        "ix_revision_idempotency",
        "revisions",
        ["environment_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.execute(TABLE_SQL)
    op.execute(
        "CREATE TRIGGER immutable_revision_track_snapshots BEFORE UPDATE OR DELETE ON revision_track_snapshots FOR EACH ROW EXECUTE FUNCTION immutable_evidence()"
    )
    op.execute("""CREATE FUNCTION validate_view_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
    IF NEW.view_track_id IS NOT NULL AND (NEW.camera_id IS NULL OR NEW.camera_id <>
       (SELECT camera_id FROM view_tracks WHERE id=NEW.view_track_id)) THEN
       RAISE EXCEPTION 'change camera mismatch'; END IF;
    RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER view_change_scope BEFORE INSERT OR UPDATE ON change_proposals FOR EACH ROW EXECUTE FUNCTION validate_view_change()"
    )
    op.execute("""CREATE FUNCTION protect_committed_proposal() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
    IF EXISTS (SELECT 1 FROM revision_changes WHERE proposal_id=OLD.id) THEN
       RAISE EXCEPTION 'committed proposal is immutable'; END IF;
    RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END $$""")
    op.execute(
        "CREATE TRIGGER committed_proposal BEFORE UPDATE OR DELETE ON change_proposals FOR EACH ROW EXECUTE FUNCTION protect_committed_proposal()"
    )
    op.execute("""CREATE FUNCTION validate_revision_track_camera() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
    IF NEW.camera_id <> (SELECT camera_id FROM view_tracks WHERE id=NEW.view_track_id) THEN
       RAISE EXCEPTION 'revision track camera mismatch'; END IF;
    RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER revision_track_camera BEFORE INSERT ON revision_track_snapshots FOR EACH ROW EXECUTE FUNCTION validate_revision_track_camera()"
    )


def downgrade():
    # Refuse to destroy new events: operators must export/remove them explicitly first.
    op.drop_table("revision_track_snapshots")
    op.execute("DROP FUNCTION validate_revision_track_camera()")
    op.execute("DROP TRIGGER committed_proposal ON change_proposals")
    op.execute("DROP FUNCTION protect_committed_proposal()")
    op.execute("DROP TRIGGER view_change_scope ON change_proposals")
    op.execute("DROP FUNCTION validate_view_change()")
    op.drop_index("ix_revision_idempotency", table_name="revisions")
    op.drop_column("revisions", "request_hash")
    op.drop_column("revisions", "idempotency_key")
    op.drop_constraint("fk_change_view_track", "change_proposals", type_="foreignkey")
    op.drop_constraint(op.f("ck_change_camera"), "change_proposals", type_="check")
    op.drop_constraint(op.f("ck_change_proposals_type_values"), "change_proposals", type_="check")
    op.create_check_constraint(
        op.f("ck_change_proposals_type_values"),
        "change_proposals",
        "type IN (" + ",".join(repr(v) for v in OLD_TYPES) + ")",
    )
    op.drop_column("change_proposals", "view_track_id")
    op.drop_column("change_proposals", "camera_id")
