"""Mask-to-dense-grid coloration. Does not infer correspondence from unordered PLYs."""

import json
from pathlib import Path

import numpy as np
from PIL import Image
from pydantic import Field, model_validator

from scene_tracker.domain.contracts import Contract
from scene_tracker.geometry.highlights import HighlightManifest


class GridTransform(Contract):
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    crop_xyxy: tuple[int, int, int, int]
    resize_width: int = Field(gt=0)
    resize_height: int = Field(gt=0)
    # Crop -> flip -> nearest resize -> zero pad. Order is part of the contract.
    flip_x: bool = False
    flip_y: bool = False
    padding_ltrb: tuple[int, int, int, int] = (0, 0, 0, 0)

    @model_validator(mode="after")
    def valid(self):
        x1, y1, x2, y2 = self.crop_xyxy
        if not (0 <= x1 < x2 <= self.image_width and 0 <= y1 < y2 <= self.image_height):
            raise ValueError("invalid canonical crop")
        if min(self.padding_ltrb) < 0:
            raise ValueError("negative padding")
        return self

    @property
    def grid_shape(self):
        left, top, right, bottom = self.padding_ltrb
        return self.resize_height + top + bottom, self.resize_width + left + right


def map_mask_to_point_grid(mask, transform):
    transform = GridTransform.model_validate(transform)
    mask = np.asarray(mask)
    if mask.shape != (transform.image_height, transform.image_width):
        raise ValueError("mask dimensions disagree with canonical image")
    if not np.isin(mask, [0, 1]).all():
        raise ValueError("mask must be binary")
    x1, y1, x2, y2 = transform.crop_xyxy
    mapped = mask[y1:y2, x1:x2]
    if transform.flip_x:
        mapped = mapped[:, ::-1]
    if transform.flip_y:
        mapped = mapped[::-1, :]
    mapped = np.asarray(
        Image.fromarray(mapped.astype(np.uint8)).resize(
            (transform.resize_width, transform.resize_height), Image.Resampling.NEAREST
        ),
        dtype=bool,
    )
    left, top, right, bottom = transform.padding_ltrb
    return np.pad(mapped, ((top, bottom), (left, right)), constant_values=False)


def colorize_point_grid(points, rgb, manifest, masks, transform, valid_filter=None, model_sha=None):
    manifest = HighlightManifest.model_validate(manifest)
    transform = GridTransform.model_validate(transform)
    if (manifest.image.width, manifest.image.height) != (
        transform.image_width,
        transform.image_height,
    ):
        raise ValueError("manifest and transform image dimensions disagree")
    points, rgb = np.asarray(points), np.asarray(rgb)
    expected = (*transform.grid_shape, 3)
    if points.shape != expected or rgb.shape != expected or rgb.dtype != np.uint8:
        raise ValueError("dense XYZ and uint8 RGB must share the recorded grid shape")
    if not np.issubdtype(points.dtype, np.number):
        raise ValueError("XYZ must be numeric")
    valid = np.isfinite(points).all(axis=-1)
    if valid_filter is not None:
        valid_filter = np.asarray(valid_filter)
        if valid_filter.shape != transform.grid_shape or valid_filter.dtype != bool:
            raise ValueError("validity filter must be boolean on the same grid")
        valid &= valid_filter
    labels = np.zeros(transform.grid_shape, dtype=np.int32)
    colors = rgb.copy()
    membership_count = np.zeros(transform.grid_shape, dtype=np.int32)
    mapping = {}
    ordered = sorted(manifest.regions, key=lambda r: (str(r.change_id), r.temporal_role))
    for label, region in enumerate(ordered, 1):
        if region.mask_ref is None:
            raise ValueError("cannot colorize a region without a canonical mask")
        if region.mask_ref not in masks:
            raise ValueError("missing referenced mask")
        member = map_mask_to_point_grid(masks[region.mask_ref], transform)
        membership_count += member
        # First lexically sorted change/role wins; independent of input region ordering.
        selected = member & (labels == 0)
        labels[selected] = label
        colors[selected] = region.highlight_rgb
        mapping[str(label)] = region.model_dump(mode="json")
    indices = np.flatnonzero(valid.ravel(order="C"))
    sidecar = {
        "schema_version": "1.0",
        "colorization_version": "dense-grid-v1",
        "capture_id": str(manifest.capture_id),
        "camera_id": str(manifest.camera_id),
        "frame_id": str(manifest.frame_id),
        "revision_id": str(manifest.revision_id) if manifest.revision_id else None,
        "model_sha": model_sha,
        "synthetic": model_sha is None,
        "transform": transform.model_dump(mode="json"),
        "transform_order": ["crop", "flip", "nearest_resize", "zero_pad"],
        "grid_shape": list(transform.grid_shape),
        "point_count": len(indices),
        "grid_indices": indices.tolist(),
        "flatten_order": "C",
        "validity": "finite_xyz_and_optional_operator_filter",
        "change_labels": labels.ravel()[indices].tolist(),
        "labels": mapping,
        "overlap_points": int(((membership_count > 1) & valid).sum()),
        "precedence": "lexical_change_id_then_temporal_role_first_wins",
        "scope": "camera_local_unregistered",
    }
    return points.reshape(-1, 3)[indices].copy(), colors.reshape(-1, 3)[indices].copy(), sidecar


def export_test_ply(output, points, colors, sidecar):
    """ASCII synthetic export; exclusive writes preserve previous artifacts."""
    points, colors = np.asarray(points), np.asarray(colors)
    if points.shape != (sidecar["point_count"], 3) or colors.shape != points.shape:
        raise ValueError("export rows disagree with sidecar")
    if colors.dtype != np.uint8 or not np.isfinite(points).all():
        raise ValueError("invalid export attributes")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    header = (
        "ply\nformat ascii 1.0\ncomment synthetic dense-grid test; no PointDiT inference\n"
        f"element vertex {len(points)}\nproperty float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
    )
    with (output / "highlighted.ply").open("x") as stream:
        stream.write(header)
        for xyz, color in zip(points, colors, strict=True):
            stream.write(
                " ".join([*(format(float(v), ".9g") for v in xyz), *(str(int(v)) for v in color)])
                + "\n"
            )
    (output / "highlighted.json").write_text(json.dumps(sidecar, sort_keys=True, indent=2))
