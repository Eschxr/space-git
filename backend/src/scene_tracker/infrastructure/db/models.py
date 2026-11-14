"""SQLAlchemy Core relational models. Environment-scoped composite FKs prevent cross-space links."""

from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData(
    naming_convention={
        "pk": "pk_%(table_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ix": "ix_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
    }
)


def model(name, *columns, constraints=()):
    return Table(
        name, metadata, Column("id", Uuid, primary_key=True, default=uuid4), *columns, *constraints
    )


def c(name, typ=Uuid, nullable=False, **kwargs):
    return Column(name, typ, nullable=nullable, **kwargs)


def scope():
    return c("environment_id")


def fk(column, target, scoped=True):
    if scoped:
        return ForeignKeyConstraint(
            [column, "environment_id"], [f"{target}.id", f"{target}.environment_id"]
        )
    return ForeignKeyConstraint([column], [f"{target}.id"])


def unique_scope():
    return UniqueConstraint("id", "environment_id")


def values(column, allowed):
    quoted = ", ".join(repr(x) for x in allowed)
    return CheckConstraint(f"{column} IN ({quoted})", name=f"{column}_values")


CAMERAS = ["cam_01", "cam_02", "cam_03", "cam_04"]
JOBS = ["queued", "running", "succeeded", "failed", "model_unavailable", "blocked_missing_weights"]
REVIEWS = ["proposed", "accepted", "rejected", "needs_review"]
TRACKS = ["observed", "unobserved", "unknown"]
CHANGES = [
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

environments = model(
    "environments",
    c("name", String(200)),
    c("prompts", JSONB, nullable=True),
    c("created_at", DateTime(timezone=True), server_default=func.now()),
)

captures = model(
    "captures",
    scope(),
    c("captured_at", DateTime(timezone=True), nullable=False),
    c("status", String, nullable=False),
    c("source_manifest_hash", String, nullable=True),
    c("error", Text, nullable=True),
    c("warnings", JSONB, server_default="[]"),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        values("status", ["uploading", "ready", "failed"]),
    ),
)

frames = model(
    "frames",
    scope(),
    c("capture_id", Uuid, nullable=False),
    c("camera_id", String, nullable=False),
    c("storage_key", String, nullable=False),
    c("sha256", String, nullable=False),
    c("width", Integer, nullable=False),
    c("height", Integer, nullable=False),
    c("original_width", Integer, nullable=False),
    c("original_height", Integer, nullable=False),
    c("exif_orientation", Integer, nullable=False),
    c("content_type", String, nullable=False),
    c("captured_at", DateTime(timezone=True), nullable=True),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("capture_id", "captures"),
        values("camera_id", CAMERAS),
        UniqueConstraint("capture_id", "camera_id"),
        CheckConstraint(
            "width > 0 AND height > 0 AND original_width > 0 AND original_height > 0",
            name="positive_dimensions",
        ),
        CheckConstraint("exif_orientation BETWEEN 1 AND 8", name="orientation"),
    ),
)

processing_runs = model(
    "processing_runs",
    scope(),
    c("capture_id", Uuid, nullable=False),
    c("status", String, nullable=False),
    c("model_manifest", JSONB, nullable=False),
    c("config_hash", String, nullable=False),
    c("progress", JSONB, server_default='{"stage":"queued"}'),
    c("started_at", DateTime(timezone=True), nullable=True),
    c("completed_at", DateTime(timezone=True), nullable=True),
    c("error", Text, nullable=True),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("capture_id", "captures"),
        values("status", JOBS),
    ),
)

detections = model(
    "detections",
    scope(),
    c("run_id", Uuid, nullable=False),
    c("frame_id", Uuid, nullable=False),
    c("label", String, nullable=False),
    c("det_score", Float, nullable=False),
    c("box_xyxy", JSONB, nullable=False),
    c("mask_key", String, nullable=True),
    c("mask_score", Float, nullable=True),
    c("embedding_key", String, nullable=True),
    c("embedding_metadata", JSONB, nullable=True),
    c("debug_crop_key", String, nullable=True),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("run_id", "processing_runs"),
        fk("frame_id", "frames"),
        CheckConstraint("det_score BETWEEN 0 AND 1", name="det_score_range"),
        CheckConstraint("mask_score BETWEEN 0 AND 1", name="mask_score_range"),
    ),
)

view_tracks = model(
    "view_tracks",
    scope(),
    c("camera_id", String, nullable=False),
    c("status", String, nullable=False),
    c("first_seen_at", DateTime(timezone=True), nullable=False),
    c("last_seen_capture_id", Uuid, nullable=True),
    c("missing_count", Integer, server_default="0"),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        values("camera_id", CAMERAS),
        values("status", TRACKS),
    ),
)

physical_objects = model(
    "physical_objects",
    scope(),
    c("label", String, nullable=False),
    c("created_at", DateTime(timezone=True), nullable=False),
    c("status", String, nullable=False),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        values("status", TRACKS),
    ),
)

track_observations = model(
    "track_observations",
    scope(),
    c("run_id", Uuid, nullable=True),
    c("view_track_id", Uuid, nullable=False),
    c("detection_id", Uuid, nullable=False),
    c("capture_id", Uuid, nullable=False),
    c("match_score", Float, nullable=False),
    c("match_metadata", JSONB, nullable=False),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("view_track_id", "view_tracks"),
        fk("capture_id", "captures"),
        UniqueConstraint("detection_id"),
        UniqueConstraint("view_track_id", "capture_id", "detection_id"),
        CheckConstraint("match_score BETWEEN 0 AND 1", name="match_score_range"),
    ),
)

object_track_links = model(
    "object_track_links",
    scope(),
    c("physical_object_id", Uuid, nullable=False),
    c("view_track_id", Uuid, nullable=False),
    c("source", String, nullable=False),
    c("review_status", String, nullable=False),
    c("evidence", JSONB, nullable=False),
    c("active", Boolean, nullable=False),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("physical_object_id", "physical_objects"),
        fk("view_track_id", "view_tracks"),
        values("review_status", REVIEWS),
    ),
)

association_candidates = model(
    "association_candidates",
    scope(),
    c("run_id", Uuid, nullable=False),
    c("kind", String, nullable=False),
    c("source_id", Uuid, nullable=False),
    c("target_id", Uuid, nullable=False),
    c("features", JSONB, nullable=False),
    c("score", Float, nullable=False),
    c("decision", String, nullable=False),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("run_id", "processing_runs"),
        values("decision", REVIEWS),
        fk("source_id", "view_tracks"),
        fk("target_id", "view_tracks"),
        CheckConstraint("source_id <> target_id", name="distinct_tracks"),
        CheckConstraint("score BETWEEN 0 AND 1", name="score_range"),
    ),
)

change_proposals = model(
    "change_proposals",
    scope(),
    c("camera_id", String, nullable=True),
    c("view_track_id", Uuid, nullable=True),
    c("run_id", Uuid, nullable=False),
    c("object_id", Uuid, nullable=True),
    c("type", String, nullable=False),
    c("before_ref", JSONB, nullable=True),
    c("after_ref", JSONB, nullable=True),
    c("evidence", JSONB, nullable=False),
    c("status", String, nullable=False),
    c("reason", Text, nullable=True),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("run_id", "processing_runs"),
        fk("object_id", "physical_objects"),
        fk("view_track_id", "view_tracks"),
        values("camera_id", CAMERAS),
        values("status", REVIEWS),
        values("type", CHANGES),
    ),
)

revisions = model(
    "revisions",
    scope(),
    c("idempotency_key", String, nullable=True),
    c("request_hash", String, nullable=True),
    c("parent_id", Uuid, nullable=True),
    c("capture_id", Uuid, nullable=False),
    c("created_at", DateTime(timezone=True), nullable=False),
    c("message", Text, nullable=False),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("parent_id", "revisions"),
        fk("capture_id", "captures"),
        UniqueConstraint("parent_id"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="no_self_parent"),
    ),
)

revision_changes = model(
    "revision_changes",
    scope(),
    c("revision_id", Uuid, nullable=False),
    c("proposal_id", Uuid, nullable=False),
    c("applied_payload", JSONB, nullable=False),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("revision_id", "revisions"),
        fk("proposal_id", "change_proposals"),
        UniqueConstraint("proposal_id"),
    ),
)

object_state_snapshots = model(
    "object_state_snapshots",
    scope(),
    c("revision_id", Uuid, nullable=False),
    c("object_id", Uuid, nullable=False),
    c("state_json", JSONB, nullable=False),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("revision_id", "revisions"),
        fk("object_id", "physical_objects"),
        UniqueConstraint("revision_id", "object_id"),
    ),
)

jobs = model(
    "jobs",
    scope(),
    c("kind", String, nullable=False),
    c("subject_id", Uuid, nullable=False),
    c("status", String, nullable=False),
    c("idempotency_key", String, nullable=False),
    c("run_id", Uuid, nullable=True),
    c("attempt", Integer, server_default="1"),
    c("error", Text, nullable=True),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        values("status", JOBS),
        UniqueConstraint("environment_id", "kind", "subject_id", "idempotency_key"),
        values("kind", ["vision", "reconstruction"]),
        fk("run_id", "processing_runs"),
        CheckConstraint("attempt > 0", name="positive_attempt"),
    ),
)

reconstructions = model(
    "reconstructions",
    scope(),
    c("capture_id", Uuid, nullable=False),
    c("revision_id", Uuid, nullable=True),
    c("status", String, nullable=False),
    c("model_manifest", JSONB, nullable=False),
    c("error", Text, nullable=True),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        fk("capture_id", "captures"),
        fk("revision_id", "revisions"),
        values("status", JOBS),
    ),
)

artifacts = model(
    "artifacts",
    scope(),
    c("kind", String, nullable=False),
    c("source_id", Uuid, nullable=False),
    c("camera_id", String, nullable=True),
    c("storage_key", String, nullable=False),
    c("sha256", String, nullable=False),
    c("content_type", String, nullable=False),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", scoped=False),
        values("camera_id", CAMERAS),
        UniqueConstraint("storage_key"),
    ),
)

Index("ix_captures_environment_time", captures.c.environment_id, captures.c.captured_at)
Index("ix_detections_run_frame", detections.c.run_id, detections.c.frame_id)
Index("ix_tracks_camera_id", view_tracks.c.camera_id, view_tracks.c.id)
Index("ix_changes_object", change_proposals.c.object_id)
Index("ix_changes_status", change_proposals.c.status)
Index("ix_revision_changes_revision", revision_changes.c.revision_id)
Index(
    "ix_active_track_link",
    object_track_links.c.view_track_id,
    unique=True,
    postgresql_where=object_track_links.c.active,
)
Index(
    "ix_revision_root",
    revisions.c.environment_id,
    unique=True,
    postgresql_where=revisions.c.parent_id.is_(None),
)


view_track_snapshots = model(
    "view_track_snapshots",
    scope(),
    c("run_id"),
    c("view_track_id"),
    c("camera_id", String),
    c("capture_id"),
    c("state", JSONB),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", False),
        fk("run_id", "processing_runs"),
        fk("view_track_id", "view_tracks"),
        fk("capture_id", "captures"),
        values("camera_id", CAMERAS),
        UniqueConstraint("run_id", "view_track_id"),
    ),
)
Index(
    "ix_observation_run_track",
    track_observations.c.run_id,
    track_observations.c.view_track_id,
    unique=True,
    postgresql_where=track_observations.c.run_id.is_not(None),
)

revision_track_snapshots = model(
    "revision_track_snapshots",
    scope(),
    c("revision_id"),
    c("view_track_id"),
    c("camera_id", String),
    c("state", JSONB),
    constraints=(
        unique_scope(),
        fk("environment_id", "environments", False),
        fk("revision_id", "revisions"),
        fk("view_track_id", "view_tracks"),
        values("camera_id", CAMERAS),
        UniqueConstraint("revision_id", "view_track_id"),
    ),
)
Index(
    "ix_revision_idempotency",
    revisions.c.environment_id,
    revisions.c.idempotency_key,
    unique=True,
    postgresql_where=revisions.c.idempotency_key.is_not(None),
)
