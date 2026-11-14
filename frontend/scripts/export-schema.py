"""Regenerate the shared scene JSON schema from the edge validator."""
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/"apps/edge"))
from spacegit_edge.models import Scene

schema={"$schema":"https://json-schema.org/draft/2020-12/schema",
        "$id":"urn:spacegit:schema:scene:1",**Scene.model_json_schema()}
(root/"packages/protocol/scene.v1.schema.json").write_text(json.dumps(schema,indent=2)+"\n",encoding="utf-8")
