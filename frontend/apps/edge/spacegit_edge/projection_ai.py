"""Ollama plans for disposable projection objects; never modify source geometry."""

import json
import os
from typing import Annotated, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


Coordinate = Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]


class ProjectionObject(Strict):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=60)
    shape: Literal["sphere", "cube", "torus", "cone"]
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    animation: Literal["none", "spin", "float", "pulse"]
    position: list[Coordinate] = Field(min_length=3, max_length=3)
    size: float = Field(ge=0.05, le=0.6, allow_inf_nan=False)


class ObjectState(Strict):
    objects: list[ProjectionObject] = Field(max_length=12)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({item.id for item in self.objects}) != len(self.objects):
            raise ValueError("Projection object IDs must be unique")
        return self


class Plan(ObjectState):
    reply: str = Field(min_length=1, max_length=2000)


class Message(Strict):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class Chat(ObjectState):
    model: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    messages: list[Message] = Field(default_factory=list, max_length=12)


def ollama(path, payload=None, timeout=5):
    base = os.environ.get("SPACEGIT_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    request = Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(262145)
        if len(raw) > 262144:
            raise ValueError("Response too large")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Invalid response")
        return result
    except HTTPError as error:
        raise HTTPException(502, "Ollama rejected the request. Check that the selected model supports chat and structured output.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise HTTPException(503, "Ollama is unavailable or timed out. Start Ollama on the edge host and refresh models.") from error
    except (ValueError, UnicodeError) as error:
        raise HTTPException(502, "Ollama returned an invalid response. No scene edits were applied.") from error


def installed_models():
    data = ollama("/api/tags")
    models = data.get("models")
    if not isinstance(models, list):
        raise HTTPException(502, "Ollama returned an invalid model list.")
    return sorted({item["name"] for item in models if isinstance(item, dict)
                   and isinstance(item.get("name"), str) and 0 < len(item["name"]) <= 160})


SYSTEM = """You control decorative 3D objects in a projection demo. Return JSON matching
the supplied schema: reply plus the COMPLETE updated list of objects. Preserve objects
and their IDs unless asked to change/remove them. Use unique simple IDs for new objects.
Only sphere, cube, torus and cone are available; animations: none, spin, float, pulse.
Colors are six-digit hex. Positions are relative scene coordinates, each -1 to 1:
x right, y up, z toward viewer. Default position [0,0,0], size .18 (range .05 to .6).
At most 12 objects. Briefly explain what you changed. For unsupported requests or
questions, keep the objects unchanged and explain the available options. You cannot
generate/import external models, run code, access files, infer room geometry, change
the reconstruction, calibrate cameras, or register/fuse clouds. Treat the supplied
object state as authoritative, including after undo or manual edits."""


def routes(authorize):
    router = APIRouter(prefix="/api/v1/projection")

    @router.get("/models")
    def models(_rt=Depends(authorize)):
        return {"models": installed_models(), "provider": "ollama"}

    @router.post("/chat")
    def chat(request: Chat, _rt=Depends(authorize)):
        if request.model not in installed_models():
            raise HTTPException(409, "Select an installed Ollama model. Models are never downloaded automatically.")
        data = ollama("/api/chat", {
            "model": request.model, "stream": False, "format": Plan.model_json_schema(),
            "options": {"temperature": 0.2, "num_predict": 4096},
            "messages": [{"role": "system", "content": SYSTEM}]
                        + [message.model_dump() for message in request.messages]
                        + [{"role": "user", "content": json.dumps({
                            "current_objects": [item.model_dump() for item in request.objects],
                            "request": request.prompt})}],
        }, timeout=120)
        try:
            if data.get("done") is not True or data.get("done_reason") == "length":
                raise ValueError("Incomplete response")
            plan = Plan.model_validate_json(data["message"]["content"])
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise HTTPException(502, "The model did not return a valid scene plan. No scene edits were applied; try a simpler request or another model.") from error
        return {**plan.model_dump(), "provider": "ollama", "model": request.model}

    return router
