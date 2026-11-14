"""Initial immutable capture and semantic-history schema (frozen DDL)."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

DDL = [
    """CREATE TABLE environments (
    id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_environments PRIMARY KEY (id)
)""",
    """CREATE TABLE artifacts (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    kind VARCHAR NOT NULL,
    source_id UUID NOT NULL,
    camera_id VARCHAR,
    storage_key VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    content_type VARCHAR NOT NULL,
    CONSTRAINT pk_artifacts PRIMARY KEY (id),
    CONSTRAINT uq_artifacts_id UNIQUE (id, environment_id),
        CONSTRAINT fk_artifacts_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT ck_artifacts_camera_id_values CHECK (camera_id IN ('cam_01', 'cam_02',
'cam_03', 'cam_04')),
    CONSTRAINT uq_artifacts_storage_key UNIQUE (storage_key)
)""",
    """CREATE TABLE captures (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    captured_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR NOT NULL,
    source_manifest_hash VARCHAR,
    CONSTRAINT pk_captures PRIMARY KEY (id),
    CONSTRAINT uq_captures_id UNIQUE (id, environment_id),
        CONSTRAINT fk_captures_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
    CONSTRAINT ck_captures_status_values CHECK (status IN ('uploading', 'ready', 'failed'))
)""",
    """CREATE TABLE jobs (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    kind VARCHAR NOT NULL,
    subject_id UUID NOT NULL,
    status VARCHAR NOT NULL,
    idempotency_key VARCHAR NOT NULL,
    error TEXT,
    CONSTRAINT pk_jobs PRIMARY KEY (id),
    CONSTRAINT uq_jobs_id UNIQUE (id, environment_id),
        CONSTRAINT fk_jobs_environment_id_environments FOREIGN KEY(environment_id) REFERENCES
environments (id),
        CONSTRAINT ck_jobs_status_values CHECK (status IN ('queued', 'running', 'succeeded',
'failed', 'model_unavailable', 'blocked_missing_weights')),
    CONSTRAINT uq_jobs_environment_id UNIQUE (environment_id, kind, subject_id, idempotency_key),
    CONSTRAINT ck_jobs_kind_values CHECK (kind IN ('vision', 'reconstruction'))
)""",
    """CREATE TABLE physical_objects (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    label VARCHAR NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR NOT NULL,
    CONSTRAINT pk_physical_objects PRIMARY KEY (id),
    CONSTRAINT uq_physical_objects_id UNIQUE (id, environment_id),
        CONSTRAINT fk_physical_objects_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT ck_physical_objects_status_values CHECK (status IN ('observed', 'unobserved',
'unknown'))
)""",
    """CREATE TABLE view_tracks (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    camera_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_view_tracks PRIMARY KEY (id),
    CONSTRAINT uq_view_tracks_id UNIQUE (id, environment_id),
        CONSTRAINT fk_view_tracks_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT ck_view_tracks_camera_id_values CHECK (camera_id IN ('cam_01', 'cam_02',
'cam_03', 'cam_04')),
    CONSTRAINT ck_view_tracks_status_values CHECK (status IN ('observed', 'unobserved', 'unknown'))
)""",
    """CREATE TABLE frames (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    capture_id UUID NOT NULL,
    camera_id VARCHAR NOT NULL,
    storage_key VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    original_width INTEGER NOT NULL,
    original_height INTEGER NOT NULL,
    exif_orientation INTEGER NOT NULL,
    content_type VARCHAR NOT NULL,
    captured_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_frames PRIMARY KEY (id),
    CONSTRAINT uq_frames_id UNIQUE (id, environment_id),
        CONSTRAINT fk_frames_environment_id_environments FOREIGN KEY(environment_id) REFERENCES
environments (id),
        CONSTRAINT fk_frames_capture_id_captures FOREIGN KEY(capture_id, environment_id)
REFERENCES captures (id, environment_id),
        CONSTRAINT ck_frames_camera_id_values CHECK (camera_id IN ('cam_01', 'cam_02', 'cam_03',
'cam_04')),
    CONSTRAINT uq_frames_capture_id UNIQUE (capture_id, camera_id),
        CONSTRAINT ck_frames_positive_dimensions CHECK (width > 0 AND height > 0 AND
original_width > 0 AND original_height > 0),
    CONSTRAINT ck_frames_orientation CHECK (exif_orientation BETWEEN 1 AND 8)
)""",
    """CREATE TABLE object_track_links (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    physical_object_id UUID NOT NULL,
    view_track_id UUID NOT NULL,
    source VARCHAR NOT NULL,
    review_status VARCHAR NOT NULL,
    evidence JSONB NOT NULL,
    active BOOLEAN NOT NULL,
    CONSTRAINT pk_object_track_links PRIMARY KEY (id),
    CONSTRAINT uq_object_track_links_id UNIQUE (id, environment_id),
        CONSTRAINT fk_object_track_links_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT fk_object_track_links_physical_object_id_physical_objects FOREIGN
KEY(physical_object_id, environment_id) REFERENCES physical_objects (id, environment_id),
        CONSTRAINT fk_object_track_links_view_track_id_view_tracks FOREIGN KEY(view_track_id,
environment_id) REFERENCES view_tracks (id, environment_id),
        CONSTRAINT ck_object_track_links_review_status_values CHECK (review_status IN
('proposed', 'accepted', 'rejected', 'needs_review'))
)""",
    """CREATE TABLE processing_runs (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    capture_id UUID NOT NULL,
    status VARCHAR NOT NULL,
    model_manifest JSONB NOT NULL,
    config_hash VARCHAR NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error TEXT,
    CONSTRAINT pk_processing_runs PRIMARY KEY (id),
    CONSTRAINT uq_processing_runs_id UNIQUE (id, environment_id),
        CONSTRAINT fk_processing_runs_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT fk_processing_runs_capture_id_captures FOREIGN KEY(capture_id,
environment_id) REFERENCES captures (id, environment_id),
        CONSTRAINT ck_processing_runs_status_values CHECK (status IN ('queued', 'running',
'succeeded', 'failed', 'model_unavailable', 'blocked_missing_weights'))
)""",
    """CREATE TABLE revisions (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    parent_id UUID,
    capture_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    message TEXT NOT NULL,
    CONSTRAINT pk_revisions PRIMARY KEY (id),
    CONSTRAINT uq_revisions_id UNIQUE (id, environment_id),
        CONSTRAINT fk_revisions_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT fk_revisions_parent_id_revisions FOREIGN KEY(parent_id, environment_id)
REFERENCES revisions (id, environment_id),
        CONSTRAINT fk_revisions_capture_id_captures FOREIGN KEY(capture_id, environment_id)
REFERENCES captures (id, environment_id),
    CONSTRAINT uq_revisions_parent_id UNIQUE (parent_id),
    CONSTRAINT ck_revisions_no_self_parent CHECK (parent_id IS NULL OR parent_id <> id)
)""",
    """CREATE TABLE track_observations (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    view_track_id UUID NOT NULL,
    detection_id UUID NOT NULL,
    capture_id UUID NOT NULL,
    match_score FLOAT NOT NULL,
    match_metadata JSONB NOT NULL,
    CONSTRAINT pk_track_observations PRIMARY KEY (id),
    CONSTRAINT uq_track_observations_id UNIQUE (id, environment_id),
        CONSTRAINT fk_track_observations_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT fk_track_observations_view_track_id_view_tracks FOREIGN KEY(view_track_id,
environment_id) REFERENCES view_tracks (id, environment_id),
        CONSTRAINT fk_track_observations_capture_id_captures FOREIGN KEY(capture_id,
environment_id) REFERENCES captures (id, environment_id),
    CONSTRAINT uq_track_observations_detection_id UNIQUE (detection_id),
    CONSTRAINT uq_track_observations_view_track_id UNIQUE (view_track_id, capture_id,
detection_id),
    CONSTRAINT ck_track_observations_match_score_range CHECK (match_score BETWEEN 0 AND 1)
)""",
    """CREATE TABLE association_candidates (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    run_id UUID NOT NULL,
    kind VARCHAR NOT NULL,
    source_id UUID NOT NULL,
    target_id UUID NOT NULL,
    features JSONB NOT NULL,
    score FLOAT NOT NULL,
    decision VARCHAR NOT NULL,
    CONSTRAINT pk_association_candidates PRIMARY KEY (id),
    CONSTRAINT uq_association_candidates_id UNIQUE (id, environment_id),
        CONSTRAINT fk_association_candidates_environment_id_environments FOREIGN
KEY(environment_id) REFERENCES environments (id),
        CONSTRAINT fk_association_candidates_run_id_processing_runs FOREIGN KEY(run_id,
environment_id) REFERENCES processing_runs (id, environment_id),
        CONSTRAINT ck_association_candidates_decision_values CHECK (decision IN ('proposed',
'accepted', 'rejected', 'needs_review')),
        CONSTRAINT fk_association_candidates_source_id_view_tracks FOREIGN KEY(source_id,
environment_id) REFERENCES view_tracks (id, environment_id),
        CONSTRAINT fk_association_candidates_target_id_view_tracks FOREIGN KEY(target_id,
environment_id) REFERENCES view_tracks (id, environment_id),
    CONSTRAINT ck_association_candidates_distinct_tracks CHECK (source_id <> target_id),
    CONSTRAINT ck_association_candidates_score_range CHECK (score BETWEEN 0 AND 1)
)""",
    """CREATE TABLE change_proposals (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    run_id UUID NOT NULL,
    object_id UUID,
    type VARCHAR NOT NULL,
    before_ref JSONB,
    after_ref JSONB,
    evidence JSONB NOT NULL,
    status VARCHAR NOT NULL,
    reason TEXT,
    CONSTRAINT pk_change_proposals PRIMARY KEY (id),
    CONSTRAINT uq_change_proposals_id UNIQUE (id, environment_id),
        CONSTRAINT fk_change_proposals_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT fk_change_proposals_run_id_processing_runs FOREIGN KEY(run_id,
environment_id) REFERENCES processing_runs (id, environment_id),
        CONSTRAINT fk_change_proposals_object_id_physical_objects FOREIGN KEY(object_id,
environment_id) REFERENCES physical_objects (id, environment_id),
        CONSTRAINT ck_change_proposals_status_values CHECK (status IN ('proposed', 'accepted',
'rejected', 'needs_review')),
        CONSTRAINT ck_change_proposals_type_values CHECK (type IN ('added_candidate',
'moved_2d_candidate', 'appearance_changed_candidate', 'unobserved', 'removed_candidate',
'possible_relocation', 'unchanged'))
)""",
    """CREATE TABLE detections (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    run_id UUID NOT NULL,
    frame_id UUID NOT NULL,
    label VARCHAR NOT NULL,
    det_score FLOAT NOT NULL,
    box_xyxy JSONB NOT NULL,
    mask_key VARCHAR,
    mask_score FLOAT,
    embedding_key VARCHAR,
    embedding_metadata JSONB,
    debug_crop_key VARCHAR,
    CONSTRAINT pk_detections PRIMARY KEY (id),
    CONSTRAINT uq_detections_id UNIQUE (id, environment_id),
        CONSTRAINT fk_detections_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT fk_detections_run_id_processing_runs FOREIGN KEY(run_id, environment_id)
REFERENCES processing_runs (id, environment_id),
        CONSTRAINT fk_detections_frame_id_frames FOREIGN KEY(frame_id, environment_id)
REFERENCES frames (id, environment_id),
    CONSTRAINT ck_detections_det_score_range CHECK (det_score BETWEEN 0 AND 1),
    CONSTRAINT ck_detections_mask_score_range CHECK (mask_score BETWEEN 0 AND 1)
)""",
    """CREATE TABLE object_state_snapshots (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    revision_id UUID NOT NULL,
    object_id UUID NOT NULL,
    state_json JSONB NOT NULL,
    CONSTRAINT pk_object_state_snapshots PRIMARY KEY (id),
    CONSTRAINT uq_object_state_snapshots_id UNIQUE (id, environment_id),
        CONSTRAINT fk_object_state_snapshots_environment_id_environments FOREIGN
KEY(environment_id) REFERENCES environments (id),
        CONSTRAINT fk_object_state_snapshots_revision_id_revisions FOREIGN KEY(revision_id,
environment_id) REFERENCES revisions (id, environment_id),
        CONSTRAINT fk_object_state_snapshots_object_id_physical_objects FOREIGN KEY(object_id,
environment_id) REFERENCES physical_objects (id, environment_id),
    CONSTRAINT uq_object_state_snapshots_revision_id UNIQUE (revision_id, object_id)
)""",
    """CREATE TABLE reconstructions (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    capture_id UUID NOT NULL,
    revision_id UUID,
    status VARCHAR NOT NULL,
    model_manifest JSONB NOT NULL,
    error TEXT,
    CONSTRAINT pk_reconstructions PRIMARY KEY (id),
    CONSTRAINT uq_reconstructions_id UNIQUE (id, environment_id),
        CONSTRAINT fk_reconstructions_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT fk_reconstructions_capture_id_captures FOREIGN KEY(capture_id,
environment_id) REFERENCES captures (id, environment_id),
        CONSTRAINT fk_reconstructions_revision_id_revisions FOREIGN KEY(revision_id,
environment_id) REFERENCES revisions (id, environment_id),
        CONSTRAINT ck_reconstructions_status_values CHECK (status IN ('queued', 'running',
'succeeded', 'failed', 'model_unavailable', 'blocked_missing_weights'))
)""",
    """CREATE TABLE revision_changes (
    id UUID NOT NULL,
    environment_id UUID NOT NULL,
    revision_id UUID NOT NULL,
    proposal_id UUID NOT NULL,
    applied_payload JSONB NOT NULL,
    CONSTRAINT pk_revision_changes PRIMARY KEY (id),
    CONSTRAINT uq_revision_changes_id UNIQUE (id, environment_id),
        CONSTRAINT fk_revision_changes_environment_id_environments FOREIGN KEY(environment_id)
REFERENCES environments (id),
        CONSTRAINT fk_revision_changes_revision_id_revisions FOREIGN KEY(revision_id,
environment_id) REFERENCES revisions (id, environment_id),
        CONSTRAINT fk_revision_changes_proposal_id_change_proposals FOREIGN KEY(proposal_id,
environment_id) REFERENCES change_proposals (id, environment_id),
    CONSTRAINT uq_revision_changes_proposal_id UNIQUE (proposal_id)
)""",
    """CREATE INDEX ix_captures_environment_time ON captures (environment_id, captured_at)""",
    """CREATE INDEX ix_tracks_camera_id ON view_tracks (camera_id, id)""",
    """CREATE UNIQUE INDEX ix_active_track_link ON object_track_links (view_track_id) WHERE
active""",
    """CREATE UNIQUE INDEX ix_revision_root ON revisions (environment_id) WHERE parent_id IS
NULL""",
    """CREATE INDEX ix_changes_status ON change_proposals (status)""",
    """CREATE INDEX ix_changes_object ON change_proposals (object_id)""",
    """CREATE INDEX ix_detections_run_frame ON detections (run_id, frame_id)""",
    """CREATE INDEX ix_revision_changes_revision ON revision_changes (revision_id)""",
    """CREATE FUNCTION enforce_capture_frames() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE cid uuid;
BEGIN
IF TG_TABLE_NAME = 'captures' THEN cid := NEW.id;
ELSE cid := COALESCE(NEW.capture_id, OLD.capture_id); END IF;
IF EXISTS (SELECT 1 FROM captures WHERE id=cid AND status='ready') AND
   (SELECT count(*) FROM frames WHERE capture_id=cid) <> 4 THEN
 RAISE EXCEPTION 'ready capture requires exactly four frames'; END IF;
RETURN NULL;
END $$""",
    """CREATE CONSTRAINT TRIGGER capture_four_frames AFTER INSERT OR UPDATE ON captures
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION enforce_capture_frames()""",
    """CREATE CONSTRAINT TRIGGER frame_four_roles AFTER INSERT OR UPDATE OR DELETE ON frames
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION enforce_capture_frames()""",
    """CREATE FUNCTION immutable_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable evidence cannot be updated or deleted'; END $$""",
    """CREATE TRIGGER immutable_frames BEFORE UPDATE OR DELETE ON frames FOR EACH ROW EXECUTE
FUNCTION immutable_evidence()""",
    """CREATE TRIGGER immutable_detections BEFORE UPDATE OR DELETE ON detections FOR EACH ROW
EXECUTE FUNCTION immutable_evidence()""",
    """CREATE TRIGGER immutable_revisions BEFORE UPDATE OR DELETE ON revisions FOR EACH ROW
EXECUTE FUNCTION immutable_evidence()""",
    """CREATE TRIGGER immutable_revision_changes BEFORE UPDATE OR DELETE ON revision_changes FOR
EACH ROW EXECUTE FUNCTION immutable_evidence()""",
    """CREATE TRIGGER immutable_object_state_snapshots BEFORE UPDATE OR DELETE ON
object_state_snapshots FOR EACH ROW EXECUTE FUNCTION immutable_evidence()""",
    """CREATE TRIGGER immutable_artifacts BEFORE UPDATE OR DELETE ON artifacts FOR EACH ROW
EXECUTE FUNCTION immutable_evidence()""",
    """CREATE FUNCTION validate_detection_capture() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
IF (SELECT capture_id FROM processing_runs WHERE id=NEW.run_id) <>
   (SELECT capture_id FROM frames WHERE id=NEW.frame_id) THEN
 RAISE EXCEPTION 'run and frame capture mismatch'; END IF;
RETURN NEW;
END $$""",
    """CREATE TRIGGER detection_capture BEFORE INSERT ON detections FOR EACH ROW EXECUTE
FUNCTION validate_detection_capture()""",
    """CREATE FUNCTION validate_track_observation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
IF NOT EXISTS (SELECT 1 FROM detections d JOIN frames f ON f.id=d.frame_id
 JOIN view_tracks t ON t.id=NEW.view_track_id
 WHERE d.id=NEW.detection_id AND f.capture_id=NEW.capture_id AND f.camera_id=t.camera_id) THEN
 RAISE EXCEPTION 'observation capture or camera mismatch'; END IF;
RETURN NEW;
END $$""",
    """CREATE TRIGGER track_observation_scope BEFORE INSERT OR UPDATE ON track_observations FOR
EACH ROW EXECUTE FUNCTION validate_track_observation()""",
    """CREATE FUNCTION validate_revision_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
IF NOT EXISTS (SELECT 1 FROM change_proposals p
JOIN processing_runs r ON r.id=p.run_id JOIN revisions v ON v.id=NEW.revision_id
WHERE p.id=NEW.proposal_id AND p.status='accepted' AND r.capture_id=v.capture_id) THEN
RAISE EXCEPTION 'revision requires accepted proposals from its capture'; END IF;
RETURN NEW;
END $$""",
    """CREATE TRIGGER revision_accepted_changes BEFORE INSERT ON revision_changes
FOR EACH ROW EXECUTE FUNCTION validate_revision_change()""",
]


def upgrade():
    for statement in DDL:
        op.execute(statement)


def downgrade():
    op.execute("DROP TABLE revision_changes CASCADE")
    op.execute("DROP TABLE reconstructions CASCADE")
    op.execute("DROP TABLE object_state_snapshots CASCADE")
    op.execute("DROP TABLE detections CASCADE")
    op.execute("DROP TABLE change_proposals CASCADE")
    op.execute("DROP TABLE association_candidates CASCADE")
    op.execute("DROP TABLE track_observations CASCADE")
    op.execute("DROP TABLE revisions CASCADE")
    op.execute("DROP TABLE processing_runs CASCADE")
    op.execute("DROP TABLE object_track_links CASCADE")
    op.execute("DROP TABLE frames CASCADE")
    op.execute("DROP TABLE view_tracks CASCADE")
    op.execute("DROP TABLE physical_objects CASCADE")
    op.execute("DROP TABLE jobs CASCADE")
    op.execute("DROP TABLE captures CASCADE")
    op.execute("DROP TABLE artifacts CASCADE")
    op.execute("DROP TABLE environments CASCADE")
    op.execute("DROP FUNCTION enforce_capture_frames()")
    op.execute("DROP FUNCTION immutable_evidence()")
    op.execute("DROP FUNCTION validate_detection_capture()")
    op.execute("DROP FUNCTION validate_track_observation()")
    op.execute("DROP FUNCTION validate_revision_change()")
