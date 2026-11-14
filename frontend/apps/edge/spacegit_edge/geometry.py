"""Planar geometry; all physical decisions depend on validated calibration."""
import math
import uuid

import cv2
import numpy as np

FIT = [(0.14, .16), (.85, .16), (.84, .84), (.14, .82), (.50, .34), (.56, .68)]
CHECK = [(.28, .30), (.72, .29), (.31, .68), (.73, .67), (.50, .52), (.50, .83)]


def mapped(matrix, points):
    return cv2.perspectiveTransform(np.asarray(points, np.float64).reshape(-1, 1, 2),
                                    np.asarray(matrix, np.float64)).reshape(-1, 2)


def corners(o):
    c, s = math.cos(o.angle), math.sin(o.angle)
    return [(o.x+c*x-s*y, o.y+s*x+c*y) for x,y in
            [(-o.w/2,-o.h/2),(o.w/2,-o.h/2),(o.w/2,o.h/2),(-o.w/2,o.h/2)]]


def solve_matrix(src, dst, limit, name):
    src, dst = np.asarray(src, np.float64), np.asarray(dst, np.float64)
    if len(np.unique(src, axis=0)) != len(src):
        raise ValueError(f"{name}: repeated points")
    m, mask = cv2.findHomography(src, dst, cv2.RANSAC, limit)
    if m is None or mask is None or mask.sum() < max(4, int(.8*len(src))) or not np.isfinite(m).all() or np.linalg.cond(m) > 1e9:
        raise ValueError(f"{name}: geometry is degenerate or the points disagree")
    return m


def solve_projector(fit, check, output, resolution, limit_px, intrinsics=None):
    from .quality import correct_pixels

    fit, check, output = np.asarray(fit), np.asarray(check), np.asarray(output)
    points = np.concatenate((fit, check))
    if np.any(points < 0) or np.any(points >= resolution):
        raise ValueError("A projector point is outside the camera image")
    if min(np.linalg.norm(check[:, None] - fit[None, :], axis=-1).ravel()) < 3 or cv2.contourArea(cv2.convexHull(fit.astype("float32"))) < 1000:
        raise ValueError("Use distinct, spread out fit and validation points")
    fit, check = correct_pixels(fit, intrinsics), correct_pixels(check, intrinsics)
    transform = solve_matrix(fit, np.asarray(FIT) * output, 8, "Projector")
    predicted = mapped(transform, check)
    errors = np.linalg.norm(predicted - np.asarray(CHECK) * output, axis=1)
    if max(errors) > limit_px:
        raise ValueError(f"Validation failed: mean {np.mean(errors):.1f}px, worst {max(errors):.1f}px (limit {limit_px:g}px)")
    return transform, dict(mean_px=float(np.mean(errors)), max_px=float(max(errors)),
                           errors_px=errors.tolist(), residuals=[
                               dict(target=list(target), predicted=(point / output).tolist(), error_px=float(error))
                               for target, point, error in zip(CHECK, predicted, errors)])


def solve_workspace(corners_px, size, resolution):
    source = np.asarray(corners_px, np.float32)
    if (np.any(source < 0) or np.any(source >= resolution)
            or not cv2.isContourConvex(source) or cv2.contourArea(source, oriented=True) < 1000):
        raise ValueError("Select a wide, convex workspace in order: top-left, top-right, bottom-right, bottom-left")
    w, h = size
    return solve_matrix(source, [(0, h), (w, h), (w, 0), (0, 0)], .002, "Workspace")


def solve(request, anchors, signature, intrinsics=None):
    from .quality import correct_pixels
    # Anchor IDs: bottom-left, bottom-right, top-right, top-left; all printed upright.
    width, height = request.wall
    aw = [(0,0), (width,0), (width,height), (0,height)]
    if any(i not in anchors for i in range(4)):
        raise ValueError("All four wall markers must be visible together")
    if request.marker_m >= min(width,height)/4:
        raise ValueError("Wall marker size is too large for the measured wall")
    half = request.marker_m/2
    measured = [(x+dx,y+dy) for x,y in aw for dx,dy in
                [(-half,half),(half,half),(half,-half),(-half,-half)]]
    seen = correct_pixels([corner for i in range(4) for corner in anchors[i]],intrinsics)
    hull = np.asarray([np.mean(anchors[i], axis=0) for i in range(4)],np.float32)
    if not cv2.isContourConvex(hull) or cv2.contourArea(hull) < 1000 or cv2.contourArea(hull, oriented=True) >= 0:
        raise ValueError("Check anchor order and leave more camera area around the wall")
    w2c = solve_matrix(measured, seen, 4, "Wall")
    anchor_error = np.linalg.norm(mapped(w2c, measured)-seen,axis=1)
    if max(anchor_error)>8:
        raise ValueError("Measured wall and marker corners disagree by more than 8 camera pixels")
    c2p, residuals = solve_projector(request.fit, request.check, request.output, signature["resolution"],
                                    request.limit_px, intrinsics)
    w2p = c2p @ w2c
    # Ensure there is no projective horizon anywhere in the working region.
    denom = [w2p[2] @ [x,y,1] for x,y in aw]
    if min(abs(v) for v in denom)<1e-8 or min(denom)*max(denom)<=0:
        raise ValueError("Projector transform is unstable across the wall")
    return dict(id=uuid.uuid4().hex, wall=request.wall, output=request.output,
                signature=signature, anchors={str(i):anchors[i] for i in range(4)},
                camera_to_wall=np.linalg.inv(w2c).tolist(), wall_to_projector=w2p.tolist(),
                **residuals,
                intrinsics=intrinsics, marker_m=request.marker_m, limit_px=request.limit_px)


def intersects(a, b, clearance=.012):
    # Separating axis theorem for two oriented footprints, inflated by clearance/2.
    def expanded(o):
        return corners(o.model_copy(update={"w":o.w+clearance, "h":o.h+clearance}))
    pa,pb = expanded(a),expanded(b)
    for o in (a,b):
        c,s = math.cos(o.angle),math.sin(o.angle)
        for u,v in [(c,s),(-s,c)]:
            p,q = [[x*u+y*v for x,y in pts] for pts in (pa,pb)]
            if max(p)<=min(q) or max(q)<=min(p):
                return False
    return True


def fits(card, wall):
    return all(0 <= x <= wall[0] and 0 <= y <= wall[1] for x,y in corners(card))
