"""Add versioned camera-local state without modifying historical evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("view_tracks", sa.Column("last_seen_capture_id", sa.Uuid(), nullable=True))
    op.add_column(
        "view_tracks", sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.create_foreign_key(
        "fk_track_last_capture",
        "view_tracks",
        "captures",
        ["last_seen_capture_id", "environment_id"],
        ["id", "environment_id"],
    )
    op.create_check_constraint("ck_track_missing_count", "view_tracks", "missing_count >= 0")
    op.add_column("track_observations", sa.Column("run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_observation_run",
        "track_observations",
        "processing_runs",
        ["run_id", "environment_id"],
        ["id", "environment_id"],
    )
    op.create_foreign_key(
        "fk_observation_detection",
        "track_observations",
        "detections",
        ["detection_id", "environment_id"],
        ["id", "environment_id"],
    )
    op.execute(TABLE_SQL)
    op.execute(INDEX_SQL)
    op.execute(
        "CREATE TRIGGER immutable_view_track_snapshots BEFORE UPDATE OR DELETE ON view_track_snapshots FOR EACH ROW EXECUTE FUNCTION immutable_evidence()"
    )
    op.execute("""CREATE FUNCTION validate_snapshot_scope() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
    IF NEW.camera_id <> (SELECT camera_id FROM view_tracks WHERE id=NEW.view_track_id) OR
       NEW.capture_id <> (SELECT capture_id FROM processing_runs WHERE id=NEW.run_id) THEN
      RAISE EXCEPTION 'snapshot camera or capture mismatch'; END IF;
    RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER snapshot_scope BEFORE INSERT ON view_track_snapshots FOR EACH ROW EXECUTE FUNCTION validate_snapshot_scope()"
    )
    op.execute("""CREATE FUNCTION validate_observation_run() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
    IF NEW.run_id IS NOT NULL AND NEW.run_id <> (SELECT run_id FROM detections WHERE id=NEW.detection_id) THEN
      RAISE EXCEPTION 'observation run mismatch'; END IF;
    RETURN NEW; END $$""")
    op.execute(
        "CREATE TRIGGER observation_run BEFORE INSERT OR UPDATE ON track_observations FOR EACH ROW EXECUTE FUNCTION validate_observation_run()"
    )


def downgrade():
    op.drop_table("view_track_snapshots")
    op.execute("DROP FUNCTION validate_snapshot_scope()")
    op.execute("DROP TRIGGER observation_run ON track_observations")
    op.execute("DROP FUNCTION validate_observation_run()")
    op.drop_index("ix_observation_run_track", table_name="track_observations")
    op.drop_constraint("fk_observation_run", "track_observations", type_="foreignkey")
    op.drop_constraint("fk_observation_detection", "track_observations", type_="foreignkey")
    op.drop_column("track_observations", "run_id")
    op.drop_constraint("fk_track_last_capture", "view_tracks", type_="foreignkey")
    op.drop_constraint("ck_track_missing_count", "view_tracks", type_="check")
    op.drop_column("view_tracks", "missing_count")
    op.drop_column("view_tracks", "last_seen_capture_id")


TABLE_SQL = """CREATE TABLE view_track_snapshots (
	id UUID NOT NULL,
	environment_id UUID NOT NULL,
	run_id UUID NOT NULL,
	view_track_id UUID NOT NULL,
	camera_id VARCHAR NOT NULL,
	capture_id UUID NOT NULL,
	state JSONB NOT NULL,
	CONSTRAINT pk_view_track_snapshots PRIMARY KEY (id),
	CONSTRAINT uq_view_track_snapshots_id UNIQUE (id, environment_id),
	CONSTRAINT fk_view_track_snapshots_environment_id_environments FOREIGN KEY(environment_id) REFERENCES environments (id),
	CONSTRAINT fk_view_track_snapshots_run_id_processing_runs FOREIGN KEY(run_id, environment_id) REFERENCES processing_runs (id, environment_id),
	CONSTRAINT fk_view_track_snapshots_view_track_id_view_tracks FOREIGN KEY(view_track_id, environment_id) REFERENCES view_tracks (id, environment_id),
	CONSTRAINT fk_view_track_snapshots_capture_id_captures FOREIGN KEY(capture_id, environment_id) REFERENCES captures (id, environment_id),
	CONSTRAINT ck_view_track_snapshots_camera_id_values CHECK (camera_id IN ('cam_01', 'cam_02', 'cam_03', 'cam_04')),
	CONSTRAINT uq_view_track_snapshots_run_id UNIQUE (run_id, view_track_id)
)"""
INDEX_SQL = """CREATE UNIQUE INDEX ix_observation_run_track ON track_observations (run_id, view_track_id) WHERE run_id IS NOT NULL"""
