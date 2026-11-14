import math
import uuid

import numpy as np
from .geometry import corners, intersects, mapped
from .models import Card


class Plan:
    def __init__(self, commit, objects, mode, tolerance_mm=25, dwell_s=.7):
        self.id=uuid.uuid4().hex
        self.commit=commit
        self.objects=objects
        self.mode=mode
        self.index=0
        self.enter=None
        self.last=None
        self.verified_at=None
        self.completed=False
        self.state="READY"
        self.tolerance=tolerance_mm/1000
        self.dwell_s=dwell_s
        self.stable_origin=None
        self.saved=None
        self.save_error=None
        self.final_enter=None
        self.final_frame=None

    def close(self, o, p):
        return math.hypot(o.x-p["x"],o.y-p["y"])<=self.tolerance and abs(math.remainder(o.angle-p["angle"],2*math.pi))<=.12

    def reset_dwell(self):
        self.enter=self.last=self.stable_origin=None

    @staticmethod
    def inside_capture(p,calibration):
        x,y=p["x"],p["y"]
        wall=calibration.get("wall")
        if wall and not (0<=x<=wall[0] and 0<=y<=wall[1]):
            return False
        px,py=mapped(calibration["wall_to_projector"],[(x,y)])[0]
        w,h=calibration["output"]
        return math.isfinite(px) and math.isfinite(py) and 0<=px<w and 0<=py<h

    def all_aligned(self, poses):
        by_marker={p["marker"]:p for p in poses if p["confidence"]>=.65}
        for o in self.objects:
            if o.marker not in by_marker:
                return "TRACKING_LOST"
        for o in self.objects:
            p=by_marker[o.marker]
            if not self.close(o,p):
                return "CONFLICT"
        return "VERIFIED"

    def update(self, now, frame, seq, poses, health, calibration, record):
        if health != "READY":
            self.reset_dwell()
            self.final_enter=self.final_frame=None
            self.state=health
            return health
        footprint_poses=poses
        poses=[p for p in poses if p["confidence"]>=.65 and self.inside_capture(p,calibration)]
        if self.completed:
            return self.all_aligned(poses)
        if self.index==len(self.objects):
            # Previously verified cards can move while another card is guided.
            # Require all cards to hold together before saving a whole layout.
            aligned=self.all_aligned(poses)
            if aligned!="VERIFIED":
                self.final_enter=self.final_frame=None
                by_marker={p["marker"]:p for p in poses if p["confidence"]>=.65}
                self.index=next(i for i,o in enumerate(self.objects)
                    if o.marker not in by_marker or not self.close(o,by_marker[o.marker]))
                self.reset_dwell()
            elif len(self.objects)==1:
                self.completed=True
                return "VERIFIED"
            else:
                if frame is not None and frame!=self.final_frame:
                    if self.final_frame is None or frame-self.final_frame>.25:
                        self.final_enter=frame
                    self.final_frame=frame
                    self.completed=frame-self.final_enter>=self.dwell_s
                return "VERIFIED" if self.completed else "NEAR_TARGET"
        if self.verified_at is not None:
            if now-self.verified_at<1:
                target=self.objects[self.index]
                pose=next((p for p in poses if p["marker"]==target.marker and p["confidence"]>=.65),None)
                return "VERIFIED" if pose and frame is not None and self.close(target,pose) else ("MOVING" if pose else "TRACKING_LOST")
            self.verified_at=None
            self.index+=1
            if self.index==len(self.objects):
                return self.update(now,frame,seq,poses,health,calibration,record)
        target=self.objects[self.index]
        pose=next((p for p in poses if p["marker"]==target.marker and p["confidence"]>=.65),None)
        if not pose or frame is None:
            self.reset_dwell()
            self.state="TRACKING_LOST"
        else:
            # A target blocked by another card must never receive a check.
            footprint = {p["marker"]: p for p in footprint_poses}
            blocked = False
            for other in self.commit["scene"]["objects"]:
                marker = other["marker"]
                if marker != target.marker and marker in footprint:
                    p = footprint[marker]
                    card = Card.model_validate(other).model_copy(update={k:p[k] for k in ("x","y","angle")})
                    blocked |= intersects(card,target)
            distance=math.hypot(target.x-pose["x"],target.y-pose["y"])
            yaw=abs(math.remainder(target.angle-pose["angle"],2*math.pi))
            if blocked or not self.close(target,pose):
                self.reset_dwell()
                self.state="CONFLICT" if blocked else "MOVING"
            else:
                self.state="NEAR_TARGET"
                if self.last is None or frame > self.last:
                    if (self.last is None or frame-self.last>.25 or
                        math.hypot(pose["x"]-self.stable_origin[0],pose["y"]-self.stable_origin[1])>max(.003,self.tolerance*.65)):
                        self.enter=frame
                        self.stable_origin=(pose["x"],pose["y"])
                    self.last=frame
                    if frame-self.enter>=self.dwell_s:
                        record(self.id,target.id,dict(mode=self.mode,commit=self.commit["id"], marker=target.marker,
                               sequence=seq,timestamp=frame,calibration=calibration["id"],distance_m=distance,yaw_rad=yaw,
                               dwell_s=frame-self.enter,tolerance_mm=self.tolerance*1000,required_dwell_s=self.dwell_s))
                        self.verified_at=now
                        self.state="VERIFIED"
        return self.state

    def overlay(self, state, poses, calibration):
        if self.completed or self.index>=len(self.objects) or not calibration or state not in ("MOVING","NEAR_TARGET","VERIFIED"):
            return None
        o=self.objects[self.index]
        matrix=calibration["wall_to_projector"]
        size=np.array(calibration["output"])
        def project(pts):
            return (mapped(matrix,pts)/size).tolist()
        result=dict(outline=project(corners(o)),to=project([(o.x,o.y)])[0],name=o.name,
                    progress=(self.index+(1 if state=="VERIFIED" else 0))/len(self.objects), ticks=[],
                    dwell=min(1,max(0,(self.last-self.enter)/self.dwell_s)) if self.enter is not None and self.last is not None else 0)
        result["ticks"]=[project([(o.x-.03,o.y),(o.x+.03,o.y)]),project([(o.x,o.y-.03),(o.x,o.y+.03)])]
        p=next((p for p in poses if p["marker"]==o.marker and p["confidence"]>=.65),None)
        if not p or not self.inside_capture(p,calibration):
            return None
        if p and state in ("MOVING","NEAR_TARGET","VERIFIED"):
            distance=math.hypot(o.x-p["x"],o.y-p["y"])
            start=project([(p["x"],p["y"])])[0]
            if not all(math.isfinite(v) and 0<=v<=1 for v in start):
                return None
            result.update({"from":start,"distance_m":distance,"confidence":p["confidence"]})
            if distance>self.tolerance and state=="MOVING":
                px,py=p["x"],p["y"]
                mid=((px+o.x)/2,(py+o.y)/2 + min(.12,distance/3))
                path=project([(px,py),mid,(o.x,o.y)])
                if not all(0<=v<=1 for v in path[1]):
                    path[1]=[(a+b)/2 for a,b in zip(path[0],path[2])]
                result["arrow"]=path
        return result
