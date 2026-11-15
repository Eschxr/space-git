"""Report active vision configuration without loading model libraries in the API."""

from fastapi import APIRouter, Request

from scene_tracker.vision.readiness import ModelUnavailable, preflight

router = APIRouter(prefix="/api/v1/vision")


@router.get("/status")
def vision_status(request: Request):
    settings = request.app.state.settings
    real = settings.vision_provider == "real"
    result = {
        "provider": settings.vision_provider,
        "detector": "YOLOE 11s prompt-free" if real else "Synthetic fixture detector",
        "embedder": "DINOv2 ViT-S/14" if real else "Synthetic appearance features",
        "device": settings.vision.yoloe_device if real else "cpu",
        "assets_verified": False,
        "reason": None,
    }
    if real:
        try:
            preflight(settings.vision)
            result["assets_verified"] = True
        except ModelUnavailable as error:
            result["reason"] = error.message
    return result
