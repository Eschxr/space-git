from uuid import uuid5

from scene_tracker.vision.contracts import DetectionBox


class FakeDetector:
    def detect(self, rgb_image, prompts, config):
        context, scenario = config
        return [
            DetectionBox(
                **context.model_dump(),
                id=uuid5(context.run_id, f"{context.frame_id}:{obj.id}"),
                fixture_id=obj.id,
                label=obj.label,
                score=1.0,
                box_xyxy=obj.box_xyxy,
            )
            for obj in sorted(scenario.objects, key=lambda obj: obj.id)
        ]
