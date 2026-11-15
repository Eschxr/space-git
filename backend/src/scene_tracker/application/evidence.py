"""Resolve immutable evidence references and sign short-lived URLs on read."""

from uuid import UUID

from minio.error import S3Error
from sqlalchemy import select
from urllib3.exceptions import HTTPError

from scene_tracker.core.errors import AppError
from scene_tracker.infrastructure.db.models import artifacts, detections, frames
from scene_tracker.infrastructure.storage.base import StorageError


class EvidenceReader:
    def __init__(self, services, environment_id):
        self.services = services
        self.environment_id = environment_id
        self.store = services.store_factory(environment_id)
        self.frames = {}
        self.artifact_metadata = {}
        self.run_overlays = {}

    def asset(self, key, expected_sha=None, content_type=None):
        if expected_sha is None:
            if key not in self.artifact_metadata:
                with self.services.repository.engine.connect() as conn:
                    self.artifact_metadata[key] = (
                        conn.execute(
                            select(artifacts).where(
                                artifacts.c.environment_id == self.environment_id,
                                artifacts.c.storage_key == key,
                            )
                        )
                        .mappings()
                        .first()
                    )
            if metadata := self.artifact_metadata[key]:
                expected_sha = metadata["sha256"]
                content_type = metadata["content_type"]
        value = {"storage_key": key, "sha256": expected_sha, "content_type": content_type}
        try:
            blob = self.store.stat(key)
            if expected_sha and blob.sha256 != expected_sha:
                return value | {"url": None, "unavailable_reason": "checksum_mismatch"}
            return value | {
                "sha256": blob.sha256,
                "content_type": blob.content_type,
                "url": self.store.presign(blob),
                "unavailable_reason": None,
            }
        except S3Error as exc:
            reason = (
                "missing_blob"
                if exc.code in {"NoSuchKey", "NoSuchObject"}
                else "storage_unavailable"
            )
            return value | {"url": None, "unavailable_reason": reason}
        except FileNotFoundError:
            return value | {"url": None, "unavailable_reason": "missing_blob"}
        except (StorageError, OSError, HTTPError):
            return value | {"url": None, "unavailable_reason": "storage_unavailable"}

    def frame(self, frame):
        self.frames[str(frame["id"])] = frame
        return dict(frame) | {
            "image": self.asset(frame["storage_key"], frame["sha256"], frame["content_type"])
        }

    def observation(self, ref):
        frame_id = str(ref["frame_id"])
        frame = self.frames.get(frame_id)
        with self.services.repository.engine.connect() as conn:
            if frame is None:
                frame = (
                    conn.execute(
                        select(frames).where(
                            frames.c.id == UUID(frame_id),
                            frames.c.environment_id == self.environment_id,
                        )
                    )
                    .mappings()
                    .first()
                )
                if frame is None:
                    raise AppError(
                        "invalid_evidence", "Observation source frame is unavailable", 409
                    )
                self.frames[frame_id] = frame
            if str(frame["capture_id"]) != str(ref["capture_id"]) or (
                ref.get("camera_id") and frame["camera_id"] != ref["camera_id"]
            ):
                raise AppError("invalid_evidence", "Observation frame/camera mismatch", 409)
            detection_id = UUID(str(ref.get("id") or ref["detection_id"]))
            run_id = conn.scalar(
                select(detections.c.run_id).where(
                    detections.c.id == detection_id,
                    detections.c.environment_id == self.environment_id,
                    detections.c.frame_id == UUID(frame_id),
                )
            )
            overlay_key = (run_id, frame["camera_id"])
            if overlay_key not in self.run_overlays:
                self.run_overlays[overlay_key] = list(
                    conn.execute(
                        select(artifacts)
                        .where(
                            artifacts.c.source_id == run_id,
                            artifacts.c.environment_id == self.environment_id,
                            artifacts.c.camera_id == frame["camera_id"],
                            artifacts.c.kind.in_(["tracks", "changes_overlay"]),
                        )
                        .order_by(artifacts.c.kind, artifacts.c.id)
                    ).mappings()
                )
        return {
            "capture_id": frame["capture_id"],
            "frame_id": frame["id"],
            "camera_id": frame["camera_id"],
            "detection_id": detection_id,
            "run_id": run_id,
            "label": ref["label"],
            "box_xyxy": ref["box_xyxy"],
            "width": frame["width"],
            "height": frame["height"],
            "image": self.asset(frame["storage_key"], frame["sha256"], frame["content_type"]),
            "mask": self.asset(ref["mask_key"]) if ref.get("mask_key") else None,
            "crop": self.asset(ref["debug_crop_key"]) if ref.get("debug_crop_key") else None,
            "overlays": [
                self.asset(row["storage_key"], row["sha256"], row["content_type"])
                for row in self.run_overlays[overlay_key]
            ],
        }

    def track(self, state):
        return {
            "view_track_id": state["view_track_id"],
            "camera_id": state["camera_id"],
            "state": state,
            "observation": self.observation(state["observation"]),
        }

    def change(self, item):
        value = dict(item)
        for side in ("before_ref", "after_ref"):
            if isinstance(ref := value.get(side), dict) and {"capture_id", "frame_id"}.issubset(
                ref
            ):
                evidence = self.observation(ref)
                value[side] = ref | {
                    "image_url": evidence["image"]["url"],
                    "mask_url": evidence["mask"]["url"] if evidence["mask"] else None,
                    "debug_crop_url": evidence["crop"]["url"] if evidence["crop"] else None,
                    "visualization": evidence,
                }
        return value
