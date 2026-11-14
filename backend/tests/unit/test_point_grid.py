from uuid import UUID, uuid4

import numpy as np
import pytest
from pydantic import ValidationError

from scene_tracker.geometry.highlights import HighlightManifest, HighlightRegion, ImageSpace
from scene_tracker.geometry.point_grid import (
    GridTransform,
    colorize_point_grid,
    export_test_ply,
    map_mask_to_point_grid,
)


def manifest(regions=()):
    return HighlightManifest(
        capture_id=uuid4(),
        camera_id="cam_01",
        frame_id=uuid4(),
        image=ImageSpace(width=4, height=4),
        regions=regions,
    )


def region(change=1, mask="mask", color=(255, 196, 0)):
    return HighlightRegion(
        change_id=UUID(int=change),
        view_track_id=uuid4(),
        change_type="moved_in_view",
        temporal_role="after",
        detection_id=uuid4(),
        mask_ref=mask,
        bbox_xyxy=(0, 0, 4, 4),
        highlight_rgb=color,
    )


def transform(**kwargs):
    return GridTransform(
        image_width=4, image_height=4, crop_xyxy=(0, 0, 4, 4), resize_width=4, resize_height=4
    ).model_copy(update=kwargs)


def grid():
    y, x = np.indices((4, 4))
    return np.stack((x, y, np.ones_like(x)), axis=-1).astype(float)


def test_exact_pixel_vertex_membership_filtering_and_ply(tmp_path):
    mask = np.zeros((4, 4), bool)
    mask[1:3, 1:3] = True
    points = grid()
    points[0, 0] = np.nan
    valid = np.ones((4, 4), bool)
    valid[1, 2] = False
    rgb = np.full((4, 4, 3), 100, np.uint8)
    xyz, colors, sidecar = colorize_point_grid(
        points, rgb, manifest([region()]), {"mask": mask}, transform(), valid
    )
    assert sidecar["grid_indices"] == [i for i in range(16) if i not in (0, 6)]
    assert [
        sidecar["grid_indices"][i] for i, label in enumerate(sidecar["change_labels"]) if label
    ] == [5, 9, 10]
    np.testing.assert_array_equal(xyz, points.reshape(-1, 3)[sidecar["grid_indices"]])
    assert (colors == (255, 196, 0)).all(axis=1).sum() == 3
    assert (rgb == 100).all()  # No mutation of source colors.
    export_test_ply(tmp_path / "export", xyz, colors, sidecar)
    rows = (tmp_path / "export/highlighted.ply").read_text().split("end_header\n")[1].splitlines()
    assert len(rows) == 14
    assert sum(row.endswith("255 196 0") for row in rows) == 3
    assert (tmp_path / "export/highlighted.json").is_file()
    with pytest.raises(FileExistsError):
        export_test_ply(tmp_path / "export", xyz, colors, sidecar)


def test_nearest_resize_crop_flip_pad_and_no_changes():
    mask = np.zeros((4, 4), bool)
    mask[0:2, 2:4] = True
    small = map_mask_to_point_grid(mask, transform(resize_width=2, resize_height=2))
    np.testing.assert_array_equal(small, [[False, True], [False, False]])
    moved = map_mask_to_point_grid(
        mask,
        transform(
            crop_xyxy=(2, 0, 4, 4),
            resize_width=2,
            resize_height=4,
            flip_y=True,
            flip_x=True,
            padding_ltrb=(1, 1, 0, 0),
        ),
    )
    expected = np.zeros((5, 3), bool)
    expected[3:5, 1:3] = True
    np.testing.assert_array_equal(moved, expected)
    asymmetric = np.zeros((4, 4), bool)
    asymmetric[0, 0] = True
    flipped = map_mask_to_point_grid(asymmetric, transform(flip_x=True))
    assert np.argwhere(flipped).tolist() == [[0, 3]]
    rgb = np.arange(48, dtype=np.uint8).reshape(4, 4, 3)
    _, colors, info = colorize_point_grid(grid(), rgb, manifest(), {}, transform())
    np.testing.assert_array_equal(colors, rgb.reshape(-1, 3))
    assert set(info["change_labels"]) == {0}


def test_overlap_determinism_and_invalid_contracts():
    a, b = region(1), region(2, color=(255, 0, 0))
    mask = np.ones((4, 4), bool)
    rgb = np.zeros((4, 4, 3), np.uint8)
    first = colorize_point_grid(grid(), rgb, manifest([b, a]), {"mask": mask}, transform())
    second = colorize_point_grid(grid(), rgb, manifest([a, b]), {"mask": mask}, transform())
    np.testing.assert_array_equal(first[1], second[1])
    assert first[2]["overlap_points"] == 16
    assert (first[1] == a.highlight_rgb).all()
    with pytest.raises(ValueError, match="dimensions"):
        map_mask_to_point_grid(mask[:2], transform())
    with pytest.raises(ValueError, match="grid shape"):
        colorize_point_grid(grid()[:2], rgb, manifest(), {}, transform())
    with pytest.raises(ValueError, match="boolean"):
        colorize_point_grid(grid(), rgb, manifest(), {}, transform(), np.ones((4, 4)))
    with pytest.raises(ValueError, match="missing referenced"):
        colorize_point_grid(grid(), rgb, manifest([a]), {}, transform())
    with pytest.raises(ValidationError):
        GridTransform(
            image_width=4, image_height=4, crop_xyxy=(-1, 0, 4, 4), resize_width=4, resize_height=4
        )
    with pytest.raises(ValidationError):
        HighlightManifest.model_validate(manifest().model_dump() | {"schema_version": "2"})
    with pytest.raises(ValidationError):
        HighlightRegion.model_validate(a.model_dump() | {"mask_ref": None})
    missing = a.model_copy(update={"mask_ref": None, "unavailable_reason": "no_mask"})
    with pytest.raises(ValueError, match="without a canonical"):
        colorize_point_grid(grid(), rgb, manifest([missing]), {}, transform())
