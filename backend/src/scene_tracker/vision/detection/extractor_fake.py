from scene_tracker.vision.detection.fake import FakeDetector
from scene_tracker.vision.segmentation.fake import FakeSegmenter


class FakeExtractor:
    def __init__(self, detector=None, segmenter=None):
        self.detector = detector or FakeDetector()
        self.segmenter = segmenter or FakeSegmenter()

    def extract(self, image, config):
        _, scenario = config
        boxes = self.detector.detect(image, [o.label for o in scenario.objects], config)
        return boxes, self.segmenter.segment(image, boxes, config)
