"""Recognize textured, planar objects using an immutable reference image."""

from threading import Lock

import cv2
import numpy as np

from .geometry import mapped


def tracking_image(jpeg):
    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Could not decode the webcam image")
    # The red channel reduces interference from the green guidance overlay.
    return np.ascontiguousarray(frame[:, :, 2])


class ObjectTracker:
    def __init__(self):
        self.lock = Lock()
        self.targets = {}
        self.observations = {}
        self.stamp = 0
        self.motion_reference = None
        self.drifted_workspace = None

    def check_motion(self, image, profile, stamp, observations):
        workspace = profile["workspace_id"]
        small = cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA)
        reference = self.motion_reference
        if reference and reference[0] == workspace and stamp-reference[1] < .35:
            return
        scale = np.asarray([320/image.shape[1], 180/image.shape[0]])
        mask = np.full(small.shape, 255, np.uint8)
        for observation in observations:
            if observation["confidence"] > 0:
                x1, y1, x2, y2 = np.round(np.asarray(observation["bbox"]) * np.tile(scale, 2)).astype(int)
                cv2.rectangle(mask, (x1-6, y1-6), (x2+6, y2+6), 0, -1)
        points = cv2.goodFeaturesToTrack(small, 100, .02, 8, mask=mask)
        self.motion_reference = workspace, stamp, small, points
        if not reference or reference[0] != workspace or reference[3] is None or len(reference[3]) < 20:
            return
        found, status, error = cv2.calcOpticalFlowPyrLK(reference[2], small, reference[3], None)
        if found is None:
            return
        good = (status.ravel() != 0) & (error.ravel() < 12)
        if good.sum() < max(20, .55 * len(good)):
            return
        shifts = (found[good] - reference[3][good]).reshape(-1, 2)
        typical = np.median(shifts, axis=0)
        consistent = np.mean(np.linalg.norm(shifts - typical, axis=1) < 2.5)
        if np.linalg.norm(typical) >= 3 and consistent >= .7:
            self.drifted_workspace = workspace

    def add(self, name, bbox, frame, profile, key, object_id):
        timestamp, _, jpeg = frame
        image = tracking_image(jpeg)
        x1, y1, x2, y2 = (round(v) for v in bbox)
        if not (0 <= x1 < x2 <= image.shape[1] and 0 <= y1 < y2 <= image.shape[0]) or min(x2-x1, y2-y1) < 28:
            raise ValueError("Select a box at least 28 pixels wide and high inside the camera image")
        roi = image[y1:y2, x1:x2]
        # Detect with context around the ROI so descriptors near its edge match the full frame.
        keypoints, descriptors = cv2.ORB_create(nfeatures=900, edgeThreshold=8, fastThreshold=9).detectAndCompute(roi, None)
        if descriptors is None or len(keypoints) < 16:
            raise ValueError("This selection has too little detail. Improve lighting or select a larger textured area.")
        reference = np.float32([point.pt for point in keypoints])
        outline = np.float32([(0, 0), (x2-x1, 0), (x2-x1, y2-y1), (0, y2-y1)])
        corners = outline + [x1, y1]
        target = dict(name=name, key=key, id=object_id, workspace=profile["workspace_id"],
                      reference=reference, descriptors=descriptors, outline=outline)
        observed = self.pose(target, corners, profile, timestamp, .85, "TRACKING")
        with self.lock:
            if len(self.targets) >= 12 and key not in self.targets:
                raise ValueError("At most twelve objects can be tracked at once")
            self.targets[key] = target
            self.observations[key] = observed
        return observed

    def remove(self, key):
        with self.lock:
            self.targets.pop(key, None)
            self.observations.pop(key, None)

    def snapshot(self, profile, now):
        if not profile:
            return []
        with self.lock:
            return [dict(p, status="LOST", confidence=0) if now-p["timestamp"] > .35 else p
                    for key, p in self.observations.items() if self.targets[key]["workspace"] == profile["workspace_id"]]

    @staticmethod
    def pose(target, outline, profile, stamp, confidence, status):
        image_center = mapped(cv2.getPerspectiveTransform(target["outline"], outline.astype(np.float32)),
                              [np.mean(target["outline"], axis=0)])[0]
        world = mapped(profile["camera_to_wall"], [image_center, *outline])
        dx, dy = world[2] - world[1]
        x1, y1 = outline.min(axis=0)
        x2, y2 = outline.max(axis=0)
        w = (np.linalg.norm(world[2]-world[1])+np.linalg.norm(world[3]-world[4])) / 2
        h = (np.linalg.norm(world[3]-world[2])+np.linalg.norm(world[4]-world[1])) / 2
        if not np.isfinite(world).all() or not (0 <= world[0, 0] <= profile["wall"][0] and 0 <= world[0, 1] <= profile["wall"][1]):
            raise ValueError("Select an object inside the calibrated workspace")
        return dict(id=target["id"], marker=target["key"], name=target["name"], status=status, timestamp=stamp,
                    bbox=[float(v) for v in (x1, y1, x2, y2)], center=image_center.tolist(), contour=outline.tolist(),
                    x=float(world[0, 0]), y=float(world[0, 1]), angle=float(np.arctan2(dy, dx)),
                    w=float(w), h=float(h), confidence=float(confidence))

    def observe(self, frame, profile):
        stamp, _, jpeg = frame
        with self.lock:
            targets = [t for t in self.targets.values() if t["workspace"] == profile["workspace_id"]]
            if stamp <= self.stamp:
                return
            self.stamp = stamp
            previous = self.observations.copy()
        image = tracking_image(jpeg)
        self.check_motion(image, profile, stamp, [previous[t["key"]] for t in targets])
        if not targets or self.drifted_workspace == profile["workspace_id"]:
            return
        points, descriptors = cv2.ORB_create(nfeatures=1800, edgeThreshold=8, fastThreshold=9).detectAndCompute(image, None)
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        for target in targets:
            key = target["key"]
            prior = previous[key]
            result = self.match(target, profile, stamp, image.shape, points, descriptors, matcher, prior)
            with self.lock:
                if self.targets.get(key) is target:
                    self.observations[key] = result

    def match(self, target, profile, stamp, shape, points, descriptors, matcher, prior):
        missing = dict(prior, status="UNCERTAIN" if stamp-prior["timestamp"] < .25 else "LOST", confidence=0)
        if descriptors is None or len(descriptors) < 2:
            return missing
        pairs = matcher.knnMatch(target["descriptors"], descriptors, k=2)
        matches = sorted((pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .72*pair[1].distance),
                         key=lambda match: match.distance)
        unique = {}
        for match in matches:
            unique.setdefault(match.trainIdx, match)
        if len(unique) < 10:
            return missing
        source = np.float32([target["reference"][m.queryIdx] for m in unique.values()])
        destination = np.float32([points[m.trainIdx].pt for m in unique.values()])
        transform, mask = cv2.findHomography(source, destination, cv2.RANSAC, 3)
        if transform is None or mask is None or mask.sum() < 9 or mask.mean() < .55:
            return missing
        inliers = source[mask.ravel().astype(bool)]
        if cv2.contourArea(cv2.convexHull(inliers)) < .12*cv2.contourArea(target["outline"]):
            return missing
        outline = mapped(transform, target["outline"]).astype(np.float32)
        if (not np.isfinite(outline).all() or not cv2.isContourConvex(outline)
                or cv2.contourArea(outline, oriented=True) < .45*cv2.contourArea(target["outline"])
                or cv2.contourArea(outline) > 2.1*cv2.contourArea(target["outline"])
                or np.any(outline < -2) or np.any(outline > np.array(shape[::-1])+1)):
            return missing
        state = "REACQUIRED" if prior["confidence"] == 0 else "TRACKING"
        confidence = min(.98, .45 + .26*float(mask.mean()) + .01*int(mask.sum()))
        try:
            return self.pose(target, outline, profile, stamp, confidence, state)
        except ValueError:
            return missing
