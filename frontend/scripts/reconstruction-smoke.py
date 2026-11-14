"""Run the real COLMAP worker on generated, textured multi-view imagery."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
for directory in ("apps/edge","apps/worker-3d","fixtures"):
    sys.path.insert(0,str(ROOT/directory))
from fastapi.testclient import TestClient
from PIL import Image, ImageOps
from generate_multiview import render
from spacegit_edge.main import make_app
from worker.main import process_one

token="local-reconstruction-fixture-only"
auth={"Authorization":"Bearer "+token}
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--images",type=Path,help="Optional local folder of authorized JPEG photos")
parser.add_argument("--quality",choices=["sparse","mesh","mesh_textured","dense","textured"],default="sparse")
parser.add_argument("--output",type=Path,help="Optional workspace folder for tested reconstruction artifacts")
args=parser.parse_args()
start=time.monotonic()
(ROOT/".cache").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="spacegit-sfm-",dir=ROOT/".cache") as tmp:
    folder=Path(tmp)
    views=folder/"views"
    if args.images:
        views.mkdir()
        for image in sorted(args.images.glob("*.jpg")):
            with Image.open(image) as original:
                im=ImageOps.exif_transpose(original).convert("RGB")
                im.thumbnail((1700,1700))
                im.save(views/image.name,quality=93)
    else:
        render(views)
    database=folder/"demo.sqlite3"
    with TestClient(make_app(database,"demo",token)) as client:
        commit=client.get("/api/v1/commits",headers=auth).json()["branches"]["main"]
        photos=[]
        for image in sorted(views.glob("*.jpg")):
            response=client.post("/api/v1/capture/photos",headers=auth,
                files={"image":(image.name,image.read_bytes(),"image/jpeg")},data={"commit":commit})
            response.raise_for_status()
            photos.append(response.json()["id"])
        queued=client.post("/api/v1/reconstructions",headers=auth,json={"photos":photos,"quality":args.quality})
        queued.raise_for_status()
        assert process_one(database,os.getenv("SPACEGIT_COLMAP"))
        job=client.get("/api/v1/reconstructions",headers=auth).json()["jobs"][0]
        if job["stage"]!="complete":
            print(json.dumps({"stage":job["stage"],"message":job["message"],"artifacts":job.get("artifacts",[]),
                              "log_tail":job["logs"][-16:]},indent=2))
            raise SystemExit(1)
        assert client.get("/api/v1/assets/"+job["id"]).status_code==401
        asset=client.get("/api/v1/assets/"+job["id"],headers=auth)
        assert asset.is_success and len(asset.content)>100 and asset.content.split(b"\n",1)[0].rstrip(b"\r")==b"ply", (asset.status_code,asset.content[:100])
        if args.quality!="sparse":
            glb=client.get("/api/v1/assets/"+job["id"]+"/model.glb",headers=auth)
            assert glb.is_success and glb.content[:4]==b"glTF", (glb.status_code,glb.content[:100])
        if args.output:
            args.output.mkdir(parents=True,exist_ok=True)
            for info in job.get("artifacts",[]):
                name=info["name"]
                shutil.copyfile(folder/"demo-files/jobs"/job["id"]/name,args.output/name)
        print(json.dumps({"provenance":"provided photographs / real COLMAP" if args.images else "synthetic rendered views / real COLMAP",
              "photos":len(photos),"registered":job["registered_images"],"points":job["point_count"],
              "asset_bytes":len(asset.content),"runtime_s":round(time.monotonic()-start,2),
              "quality":args.quality,"triangles":job.get("triangle_count"),"textured":job.get("textured",False),
              "artifacts":job.get("artifacts",[])},indent=2))
