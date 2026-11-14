"""Single-host COLMAP worker. Run independently of the edge web process."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time

from PIL import Image, ImageOps
from .pipeline import surface

ROOT=Path(__file__).resolve().parents[3]
STEPS=("validating_images","feature_extraction","matching","sparse_mapping","asset_conversion")
OPTIONAL={"sparse":(),"mesh":("meshing",),"mesh_textured":("undistorting","meshing","texturing"),"dense":("undistorting","dense_stereo","dense_fusion","meshing"),
          "textured":("undistorting","dense_stereo","dense_fusion","meshing","texturing")}


class ReconstructionCancelled(Exception):
    pass


@contextmanager
def connection(path,write=False):
    db=sqlite3.connect(path,timeout=10)
    try:
        if write:
            db.execute("BEGIN IMMEDIATE")
        with db:
            yield db
    finally:
        db.close()


def update(path,job,stage,message,output=None):
    job.update(stage=stage,message=message)
    timeline=STEPS+OPTIONAL[job.get("quality","sparse")]
    job["progress"]={"done":len(timeline) if stage=="complete" else timeline.index(stage) if stage in timeline else job.get("progress",{}).get("done",0),
                     "total":len(timeline)}
    if output:
        job["logs"]=(job["logs"]+[line[:320] for line in output.splitlines()[-45:] if line.strip()])[-100:]
    with connection(path,True) as db:
        row = db.execute("SELECT body FROM jobs WHERE id=?", (job["id"],)).fetchone()
        if row and json.loads(row[0]).get("cancel_requested") and stage != "cancelled":
            raise ReconstructionCancelled()
        job.pop("cancel_requested", None)
        db.execute("UPDATE jobs SET stage=?,body=? WHERE id=?",(stage,json.dumps(job),job["id"]))


def process_one(path,binary=None):
    started = time.monotonic()
    with connection(path,True) as db:
        row=db.execute("SELECT body FROM jobs WHERE stage='queued' ORDER BY rowid LIMIT 1").fetchone()
        if not row:
            return False
        job=json.loads(row[0])
        job.update(stage="validating_images",message="Checking images")
        db.execute("UPDATE jobs SET stage=?,body=? WHERE id=?",(job["stage"],json.dumps(job),job["id"]))
        refs=[db.execute("SELECT mime FROM photos WHERE id=?",(p,)).fetchone() for p in job["photos"]]
    data=path.parent/f"{path.stem}-files"
    work=data/"jobs"/job["id"]
    try:
        executable=shutil.which(binary or os.getenv("SPACEGIT_COLMAP","colmap"))
        if not executable:
            raise RuntimeError("COLMAP unavailable. Install COLMAP and set SPACEGIT_COLMAP, then queue this dataset again.")
        if len(refs)<6 or any(r is None for r in refs):
            raise RuntimeError("A multi-view job requires at least six retained photographs")
        work.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="colmap-",dir=work) as temp:
            root=Path(temp)
            images=root/"images"
            sparse=root/"sparse"
            images.mkdir()
            sparse.mkdir()
            for pid,(mime,) in zip(job["photos"],refs):
                update(path, job, "validating_images", "Checking images")
                ext="jpg" if mime=="image/jpeg" else "png"
                with Image.open(data/"photos"/f"{pid}.{ext}") as original:
                    im=ImageOps.exif_transpose(original).convert("RGB")
                    if min(im.size)<480:
                        raise RuntimeError("A photo is smaller than 480 pixels on its short edge")
                    im.thumbnail((2400,2400))
                    im.save(images/f"{pid}.jpg",quality=91)
            dbfile=str(root/"matches.db")

            def publish(source,name):
                if not source.is_file() or source.stat().st_size==0:
                    raise RuntimeError("Output artifact is empty: "+name)
                incoming=work/(name+".incoming")
                shutil.copyfile(source,incoming)
                incoming.replace(work/name)
                entries=job.setdefault("artifacts",[])
                entries[:]=[a for a in entries if a["name"]!=name]
                entries.append({"name":name,"bytes":source.stat().st_size})

            def command(stage,message,args,timeout=1800):
                update(path,job,stage,message)
                logpath=root/"stage.log"
                with logpath.open("wb") as log:
                    p=subprocess.Popen([executable,*args],cwd=root,stdout=log,stderr=subprocess.STDOUT)
                    deadline=time.monotonic()+timeout
                    try:
                        while p.poll() is None:
                            if time.monotonic()>deadline:
                                raise RuntimeError(f"{message} timed out. Reduce the dataset size or choose a lighter job.")
                            with logpath.open("rb") as snapshot:
                                snapshot.seek(max(0,logpath.stat().st_size-6500))
                                job["current_log"]=snapshot.read().decode("utf-8",errors="replace").replace(str(root),"[work]").splitlines()[-18:]
                            update(path,job,stage,message)
                            time.sleep(.65)
                    finally:
                        if p.poll() is None:
                            p.kill()
                            p.wait(timeout=10)
                        with logpath.open("rb") as snapshot:
                            snapshot.seek(max(0,logpath.stat().st_size-18000))
                            tail=snapshot.read().decode("utf-8",errors="replace").replace(str(root),"[work]")
                        job.pop("current_log",None)
                        update(path,job,stage,message,tail)
                if p.returncode:
                    raise RuntimeError(f"{message} failed (COLMAP exit {p.returncode}). Check stage logs, photo overlap, and GPU support/memory.")

            def supported(subcmd, modern, legacy):
                r=subprocess.run([executable,subcmd,"-h"],capture_output=True,text=True,timeout=30,errors="replace")
                return modern if modern in (r.stdout+r.stderr) else legacy

            feature=supported("feature_extractor","FeatureExtraction.use_gpu","SiftExtraction.use_gpu")
            match=supported("exhaustive_matcher","FeatureMatching.use_gpu","SiftMatching.use_gpu")
            command("feature_extraction","Extracting local image features",["feature_extractor","--database_path",dbfile,
                    "--image_path",str(images),"--"+feature,"0"])
            command("matching","Matching overlapping photographs",["exhaustive_matcher","--database_path",dbfile,"--"+match,"0"])
            command("sparse_mapping","Estimating camera poses and sparse points",["mapper","--database_path",dbfile,
                    "--image_path",str(images),"--output_path",str(sparse)])
            models=[]
            for model in sorted(sparse.iterdir()):
                try:
                    import struct
                    with (model/"images.bin").open("rb") as f:
                        n=struct.unpack("<Q",f.read(8))[0]
                    with (model/"points3D.bin").open("rb") as f:
                        points=struct.unpack("<Q",f.read(8))[0]
                    models.append((n,points,model))
                except (OSError,struct.error):
                    continue
            if not models or max(models)[0]<3 or max(models)[1]<20:
                raise RuntimeError("Insufficient reconstruction: need at least three registered views and twenty sparse points. Add overlapping, textured views.")
            registered,points,model=max(models)
            output=root/"sparse.ply"
            command("asset_conversion","Exporting sparse PLY",["model_converter","--input_path",str(model),
                    "--output_path",str(output),"--output_type","PLY"],300)
            if not output.is_file() or output.stat().st_size<100:
                raise RuntimeError("COLMAP returned without producing a usable PLY")
            publish(output,"sparse.ply")
            job.update(asset=job["id"],registered_images=registered,point_count=points,scale="unregistered")
            quality=job.get("quality","sparse")
            summary=f"{registered}/{len(refs)} registered views · {points} sparse points"
            if quality!="sparse":
                triangles,textured=surface(quality,command,root,images,model,publish)
                job.update(triangle_count=triangles,textured=textured)
                summary+=f" · {triangles} {'textured' if textured else 'untextured'} triangles"
            job["duration_s"] = round(time.monotonic()-started, 2)
            update(path,job,"complete",summary+" · arbitrary scale")
    except ReconstructionCancelled:
        job["duration_s"] = round(time.monotonic()-started, 2)
        update(path, job, "cancelled", "Reconstruction cancelled. Uploaded photos were retained.")
    except (RuntimeError,OSError,ValueError,MemoryError,SyntaxError,subprocess.SubprocessError) as exc:
        job["duration_s"] = round(time.monotonic()-started, 2)
        try:
            update(path,job,"partial" if job.get("asset") else "failed",str(exc)[:480] or "Reconstruction ran out of memory")
        except ReconstructionCancelled:
            update(path, job, "cancelled", "Reconstruction cancelled. Uploaded photos were retained.")
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once",action="store_true")
    args=parser.parse_args()
    mode=os.getenv("SPACEGIT_MODE","live")
    if mode not in ("live","demo"):
        parser.error("SPACEGIT_MODE must be live or demo")
    path=Path(os.getenv("SPACEGIT_DATA",ROOT/"data")).resolve()/f"{mode}.sqlite3"
    if not path.is_file():
        parser.error("Start the edge first to initialize the workspace")
    with connection(path, True) as db:
        rows = db.execute("SELECT body FROM jobs WHERE stage NOT IN ('queued','complete','partial','failed','cancelled')").fetchall()
        for row in rows:
            job = json.loads(row[0])
            requested = job.pop("cancel_requested", False)
            stage = "cancelled" if requested else "partial" if job.get("asset") else "failed"
            job.update(stage=stage, message="The previous worker stopped before completing this job. Retry to start again.")
            job.pop("current_log", None)
            db.execute("UPDATE jobs SET stage=?,body=? WHERE id=?", (stage, json.dumps(job), job["id"]))
    print(f"SpaceGit worker watching {path.name}",flush=True)
    while True:
        worked=process_one(path)
        if args.once:
            return
        if not worked:
            time.sleep(2)


if __name__=="__main__":
    main()
