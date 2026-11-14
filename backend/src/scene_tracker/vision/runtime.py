"""Worker-only official model initialization. No downloads and no fake fallback."""

import importlib
import importlib.metadata
import os
import sys
from pathlib import Path

from scene_tracker.vision.readiness import ModelUnavailable, preflight


def initialize(settings):
    provenance = preflight(settings)
    # Force all Hugging Face reads to locally installed assets, including BERT.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TORCH_HOME"] = str(settings.model_cache_dir.resolve())
    for source in provenance["sources"].values():
        sys.path.insert(0, source["path"])
    try:
        import torch
        import torchvision  # noqa: F401 - validates the compiled Torch/Torchvision pair

        if settings.device.startswith("cuda"):
            index = int(settings.device.split(":")[1]) if ":" in settings.device else 0
            if not torch.cuda.is_available() or index >= torch.cuda.device_count():
                raise ModelUnavailable(f"CUDA device {settings.device} is unavailable")
            extension = importlib.import_module("groundingdino._C")
            from scene_tracker.vision.readiness import sha256_file

            provenance["cuda_extension_sha256"] = sha256_file(extension.__file__)
            provenance["cuda_runtime"] = torch.version.cuda
            provenance["cuda_device_name"] = torch.cuda.get_device_name(index)
        for name, source in provenance["sources"].items():
            module = importlib.import_module(name)
            if not Path(module.__file__).resolve().is_relative_to(source["path"]):
                raise ModelUnavailable(f"{name} imported from a different source checkout")
        provenance["packages"] = {
            name: importlib.metadata.version(name)
            for name in ["torch", "torchvision", "transformers", "numpy", "pillow", "pycocotools"]
        }
        return torch, provenance
    except ModelUnavailable:
        raise
    except Exception as exc:
        raise ModelUnavailable(
            f"real runtime import/device failure: {type(exc).__name__}: {exc}"
        ) from exc


def load_models(settings):
    try:
        torch, provenance = initialize(settings)
        from dinov2.hub.backbones import dinov2_vits14
        from groundingdino.datasets import transforms as transforms
        from groundingdino.models import build_model
        from groundingdino.util.slconfig import SLConfig
        from groundingdino.util.utils import clean_state_dict, get_phrases_from_posmap
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        from scene_tracker.vision.detection.grounding_dino import GroundingDINO
        from scene_tracker.vision.embeddings.dinov2 import DINOv2Embedder
        from scene_tracker.vision.segmentation.sam2 import SAM2Segmenter

        config = (
            Path(provenance["sources"]["groundingdino"]["path"])
            / "groundingdino/config/GroundingDINO_SwinT_OGC.py"
        )
        args = SLConfig.fromfile(str(config))
        args.device = settings.device
        args.text_encoder_type = provenance["bert"]["path"]
        detector = build_model(args)
        checkpoint = torch.load(
            provenance["checkpoints"]["groundingdino"]["path"],
            map_location="cpu",
            weights_only=True,
        )
        incompatible = detector.load_state_dict(clean_state_dict(checkpoint["model"]), strict=False)
        # Official checkpoints can omit training-only keys; record all differences.
        provenance["grounding_state_keys"] = {
            "missing": incompatible.missing_keys,
            "unexpected": incompatible.unexpected_keys,
        }
        if any(k for k in incompatible.missing_keys if not k.startswith("label_enc.")):
            raise ModelUnavailable(
                "Grounding DINO checkpoint is missing inference model parameters"
            )
        detector = detector.eval().to(settings.device)
        transform = transforms.Compose(
            [
                transforms.RandomResize([800], max_size=1333),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

        def predict(rgb, caption, box_threshold, text_threshold):
            transformed, _ = transform(rgb, None)
            tokenizer = detector.tokenizer
            tokenized = tokenizer(caption)
            if len(tokenized["input_ids"]) > 256:
                raise ValueError("prompt catalogue exceeds Grounding DINO's 256-token limit")
            with torch.inference_mode():
                outputs = detector(transformed[None].to(settings.device), captions=[caption])
            logits = outputs["pred_logits"].cpu().sigmoid()[0]
            boxes = outputs["pred_boxes"].cpu()[0]
            # Preserve every raw model query for diagnosis, including threshold-rejected ones.
            phrases = [
                get_phrases_from_posmap(logit > text_threshold, tokenized, tokenizer)
                for logit in logits
            ]
            return boxes.numpy(), logits.max(dim=1)[0].numpy(), phrases

        sam_model = build_sam2(
            "configs/sam2.1/sam2.1_hiera_s.yaml",
            provenance["checkpoints"]["sam2"]["path"],
            device=settings.device,
            apply_postprocessing=False,
        )
        predictor = SAM2ImagePredictor(sam_model, max_hole_area=0, max_sprinkle_area=0)
        embedding_model = dinov2_vits14(pretrained=False)
        embedding_model.load_state_dict(
            torch.load(
                provenance["checkpoints"]["dinov2"]["path"], map_location="cpu", weights_only=True
            ),
            strict=True,
        )
        embedding_model = embedding_model.eval().to(settings.device)

        def forward(array):
            with torch.inference_mode():
                return embedding_model(torch.from_numpy(array).to(settings.device)).cpu().numpy()

        provenance["status"] = "models_loaded_inference_unvalidated"
        provenance["scores"] = "upstream confidence/quality scores, not calibrated probabilities"
        return (
            GroundingDINO(predict, settings),
            SAM2Segmenter(predictor),
            DINOv2Embedder(forward, settings),
            provenance,
        )
    except ModelUnavailable:
        raise
    except Exception as exc:
        raise ModelUnavailable(
            f"real model initialization failed: {type(exc).__name__}: {exc}"
        ) from exc
