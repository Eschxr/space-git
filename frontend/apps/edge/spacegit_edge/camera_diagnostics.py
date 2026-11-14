"""Measure image quality and delivery timing from camera frames."""

from collections import deque
import time

import cv2
import numpy as np


class CameraDiagnostics:
    def __init__(self):
        self.timestamps = deque(maxlen=120)
        self.sample = None
        self.sample_at = 0.0

    def observe(self, frame, timestamp, nominal_fps):
        self.timestamps.append(timestamp)
        while len(self.timestamps) > 1 and timestamp - self.timestamps[0] > 2:
            self.timestamps.popleft()
        if timestamp - self.sample_at >= .35:
            gray = cv2.cvtColor(cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            self.sample = dict(brightness=float(gray.mean()), sharpness=float(cv2.Laplacian(gray, cv2.CV_32F).var()),
                               underexposed=float(np.mean(gray < 25)), overexposed=float(np.mean(gray > 245)))
            self.sample_at = timestamp
        duration = timestamp - self.timestamps[0]
        fps = (len(self.timestamps) - 1) / duration if duration >= .5 else None
        brightness, sharpness = self.sample["brightness"], self.sample["sharpness"]
        if brightness < 30 or brightness > 230 or (fps is not None and fps < 5):
            grade = "Unsuitable"
        elif sharpness < 35 or not 55 <= brightness <= 205 or (fps is not None and fps < 12):
            grade = "Limited"
        elif sharpness >= 100 and fps is not None and fps >= 22 and 70 <= brightness <= 190:
            grade = "Excellent"
        else:
            grade = "Good"
        return dict(**self.sample, fps=fps, nominal_fps=nominal_fps or None, grade=grade,
                    delivery_shortfall=max(0.0, 1 - fps / nominal_fps) if fps is not None and nominal_fps > 0 else None,
                    processing_ms=max(0.0, (time.time() - timestamp) * 1000))
