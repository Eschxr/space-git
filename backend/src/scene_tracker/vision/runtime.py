"""Worker-only YOLOE + pinned DINOv2 lifecycle. Never downloads model assets."""

import importlib
import importlib.metadata
import os
import sys
from pathlib import Path

from scene_tracker.vision.readiness import ULTRALYTICS_VERSION, ModelUnavailable, preflight


def load_models(settings):
    provenance = preflight(settings)
    try:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["YOLO_AUTOINSTALL"] = "false"
        os.environ["YOLO_CONFIG_DIR"] = str(settings.model_cache_dir.resolve() / "ultralytics")
        import torch
        from ultralytics import YOLOE

        if importlib.metadata.version("ultralytics") != ULTRALYTICS_VERSION:
            raise ModelUnavailable("Ultralytics version does not match pinned runtime")
        for device in (settings.device, settings.yoloe_device):
            if device.startswith("cuda") and (
                not torch.cuda.is_available()
                or int(device.split(":")[1] if ":" in device else 0) >= torch.cuda.device_count()
            ):
                raise ModelUnavailable(f"device {device} is unavailable")
        source = provenance["sources"]["dinov2"]["path"]
        sys.path.insert(0, source)
        module = importlib.import_module("dinov2")
        if not Path(module.__file__).resolve().is_relative_to(source):
            raise ModelUnavailable("DINOv2 imported outside its pinned checkout")
        from dinov2.hub.backbones import dinov2_vits14

        from scene_tracker.vision.detection.yoloe import YOLOEExtractor
        from scene_tracker.vision.embeddings.dinov2 import DINOv2Embedder

        model = YOLOE(provenance["checkpoints"]["yoloe"]["path"])
        backbone = dinov2_vits14(pretrained=False)
        backbone.load_state_dict(
            torch.load(
                provenance["checkpoints"]["dinov2"]["path"], map_location="cpu", weights_only=True
            ),
            strict=True,
        )
        backbone = backbone.eval().to(settings.device)

        def forward(batch):
            with torch.inference_mode():
                return backbone(torch.from_numpy(batch).to(settings.device)).cpu().numpy()

        provenance.update(
            status="models_loaded_inference_unvalidated",
            packages={
                p: importlib.metadata.version(p)
                for p in ["torch", "torchvision", "ultralytics", "numpy", "pillow", "pycocotools"]
            },
            scores="model confidence, not calibrated probability",
        )
        return YOLOEExtractor(model, settings), DINOv2Embedder(forward, settings), provenance
    except ModelUnavailable:
        raise
    except Exception as exc:
        raise ModelUnavailable(
            f"real model initialization failed: {type(exc).__name__}: {exc}"
        ) from exc
