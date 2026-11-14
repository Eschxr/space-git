"""Reduce manually annotated wall measurements; never creates observations."""
import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

def latency(path, fps):
    with path.open(newline="",encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    frames=[]
    for r in rows:
        before,after=int(r["motion_frame"]),int(r["arrow_frame"])
        if before<0 or after<before:
            raise ValueError("Frame numbers must be ordered and nonnegative")
        frames.append(after-before)
    if len(frames)<10:
        raise ValueError("Annotate at least ten independent moves")
    ms=np.asarray(frames)*1000/fps
    return {"source":"operator_annotated_external_video","fps":fps,"frame_resolution_ms":1000/fps,
            "samples":len(ms),"p50_ms":float(np.percentile(ms,50)),"p95_ms":float(np.percentile(ms,95)),
            "min_ms":float(min(ms)),"max_ms":float(max(ms)),"frame_deltas":frames}

def repeatability(path):
    with path.open(newline="",encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    points={}
    for r in rows:
        coords=[float(r[k]) for k in ("x_expected_m","y_expected_m","x_observed_m","y_observed_m")]
        if not all(math.isfinite(v) for v in coords):
            raise ValueError("Measurements must be finite")
        points.setdefault(tuple(coords[:2]),{})[r["run"]]=tuple(coords[2:])
    if len(points)<3 or any(len(v)<3 for v in points.values()):
        raise ValueError("Measure at least three reference points across three separate calibrations each")
    samples=[]
    for target, runs in sorted(points.items()):
        observed=np.asarray(list(runs.values()))
        error=np.linalg.norm(observed-target,axis=1)*1000
        spread=np.linalg.norm(observed-np.median(observed,axis=0),axis=1)*1000
        samples.append({"reference_m":target,"runs":len(runs),"p50_error_mm":float(np.percentile(error,50)),
                        "p95_error_mm":float(np.percentile(error,95)),"p95_repeatability_mm":float(np.percentile(spread,95))})
    return {"source":"operator_ruler_measurements","points":samples}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    timing=commands.add_parser("latency")
    timing.add_argument("csv",type=Path)
    timing.add_argument("--fps",type=float,required=True)
    repeat=commands.add_parser("repeatability")
    repeat.add_argument("csv",type=Path)
    args=parser.parse_args()
    try:
        if args.command=="latency" and not (24<=args.fps<=1000):
            raise ValueError("Use the measured video frame rate (24–1000 fps)")
        print(json.dumps(latency(args.csv,args.fps) if args.command=="latency" else repeatability(args.csv),indent=2))
    except (OSError,ValueError,KeyError) as exc:
        parser.error(str(exc))
