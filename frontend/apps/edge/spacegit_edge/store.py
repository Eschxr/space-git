from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
import uuid

from .geometry import fits, intersects
from .models import Card, PlacementRules, Scene

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads((ROOT/"fixtures/gallery.json").read_text(encoding="utf-8"))


def compact(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False)


class Store:
    def __init__(self, path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.tx() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS commits(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS branches(name TEXT PRIMARY KEY, tip TEXT NOT NULL REFERENCES commits(id));
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS verification(plan TEXT, object TEXT, body TEXT NOT NULL, PRIMARY KEY(plan,object));
            CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS wall_checks(id INTEGER PRIMARY KEY, calibration TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS verified_layouts(plan TEXT PRIMARY KEY REFERENCES plans(id), revision TEXT NOT NULL REFERENCES commits(id));
            CREATE TABLE IF NOT EXISTS photos(id TEXT PRIMARY KEY, commit_id TEXT NOT NULL REFERENCES commits(id), mime TEXT NOT NULL, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, stage TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS visual_placements(asset TEXT NOT NULL REFERENCES jobs(id), revision TEXT NOT NULL REFERENCES commits(id),
                body TEXT NOT NULL, PRIMARY KEY(asset,revision));
            CREATE TABLE IF NOT EXISTS capture_sessions(id TEXT PRIMARY KEY, revision TEXT NOT NULL REFERENCES commits(id),
                created REAL NOT NULL, source TEXT NOT NULL, request_quality TEXT);
            CREATE TABLE IF NOT EXISTS photo_metadata(id TEXT PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS capture_entries(session TEXT REFERENCES capture_sessions(id), photo TEXT REFERENCES photos(id) ON DELETE CASCADE,
                PRIMARY KEY(session,photo));
            CREATE TABLE IF NOT EXISTS pole_captures(id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS pole_frames(capture TEXT NOT NULL REFERENCES pole_captures(id), slot INTEGER NOT NULL, jpeg BLOB NOT NULL, PRIMARY KEY(capture,slot));
            CREATE TRIGGER IF NOT EXISTS immutable_commit_update BEFORE UPDATE ON commits BEGIN SELECT RAISE(ABORT,'Commit is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_commit_delete BEFORE DELETE ON commits BEGIN SELECT RAISE(ABORT,'Commit is immutable'); END;
            """)

    @contextmanager
    def tx(self, write=False):
        db=sqlite3.connect(self.path,timeout=5)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("BEGIN IMMEDIATE")
            with db:
                yield db
        finally:
            db.close()

    def seed(self, demo):
        with self.tx(True) as db:
            if self.branches(db):
                return
            scene=FIXTURE if demo else {**FIXTURE,"id":"wall","name":"Untitled wall","objects":[]}
            c=self.insert(db,scene,"Gallery baseline" if demo else "Initialize wall",[],{"mode":"demo"} if demo else None)
            db.execute("INSERT INTO branches VALUES('main',?)",(c["id"],))

    def insert(self, db, scene, message, parents, evidence=None):
        body=dict(message=message, parents=parents, time=time.time(),scene=scene,evidence=evidence)
        body["id"]=hashlib.sha256(compact(body).encode()).hexdigest()[:20]
        db.execute("INSERT INTO commits VALUES(?,?)",(body["id"],compact(body)))
        return body

    def branches(self, db):
        return dict(db.execute("SELECT name,tip FROM branches ORDER BY name"))

    def commit(self, db, cid):
        row=db.execute("SELECT body FROM commits WHERE id=?",(cid,)).fetchone()
        if not row:
            raise ValueError("Unknown revision")
        return json.loads(row[0])

    def list(self):
        with self.tx() as db:
            return dict(branches=self.branches(db),
                        commits=[json.loads(r[0]) for r in db.execute("SELECT body FROM commits ORDER BY rowid DESC")])

    def branch(self, name, commit):
        with self.tx(True) as db:
            self.commit(db,commit)
            if name in self.branches(db):
                raise ValueError("Branch already exists")
            db.execute("INSERT INTO branches VALUES(?,?)",(name,commit))

    def save(self, name, expected, scene, message, evidence):
        with self.tx(True) as db:
            tip=self.branches(db).get(name)
            if not tip or tip!=expected:
                raise ValueError("Branch moved. Refresh the revision before saving.")
            prior=self.commit(db,tip)["scene"]
            if prior["id"]!=scene.id or issues(scene):
                raise ValueError("Scene identity, wall bounds, or spacing is invalid")
            c=self.insert(db,scene.model_dump(mode="json"),message,[tip],evidence)
            db.execute("UPDATE branches SET tip=? WHERE name=?",(c["id"],name))
            return c

    def setting(self,key,value=None):
        with self.tx(value is not None) as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)",(key,compact(value)))
                return value
            row=db.execute("SELECT body FROM settings WHERE key=?",(key,)).fetchone()
            return json.loads(row[0]) if row else None

    def clear_setting(self,key):
        with self.tx(True) as db:
            db.execute("DELETE FROM settings WHERE key=?",(key,))

    def add_reference(self,calibration,evidence):
        with self.tx(True) as db:
            db.execute("INSERT INTO wall_checks(calibration,body) VALUES(?,?)",(calibration,compact(evidence)))

    def references(self,calibration):
        with self.tx() as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT body FROM wall_checks WHERE calibration=? ORDER BY id DESC LIMIT 40",(calibration,))]

    def save_verified(self,plan,poses,calibration,seq,stamp):
        if plan.mode!="live" or not plan.completed or plan.all_aligned(poses)!="VERIFIED":
            raise ValueError("A complete live deployment is required to save measured positions")
        scene=Scene.model_validate(plan.commit["scene"])
        by_marker={p["marker"]:p for p in poses if p["confidence"]>=.65}
        if len(plan.objects)!=len(scene.objects) or any(o.marker not in by_marker for o in scene.objects):
            raise ValueError("All revision objects must be verified")
        scene=scene.model_copy(update={"objects":[o.model_copy(update={k:by_marker[o.marker][k] for k in ("x","y","angle")})
                                                  for o in scene.objects]})
        if issues(scene):
            raise ValueError("Measured layout violates placement constraints; no revision was saved")
        with self.tx(True) as db:
            old=db.execute("SELECT revision FROM verified_layouts WHERE plan=?",(plan.id,)).fetchone()
            if old:
                return old[0]
            c=self.insert(db,scene.model_dump(mode="json"),"Verified placement: "+plan.commit["message"][:95],
                          [plan.commit["id"]],{"mode":"live","plan":plan.id,"calibration":calibration,"seq":seq,
                                               "timestamp":stamp,"tolerance_mm":plan.tolerance*1000,"dwell_s":plan.dwell_s})
            db.execute("INSERT INTO verified_layouts VALUES(?,?)",(plan.id,c["id"]))
            db.execute("INSERT INTO branches VALUES(?,?)",("verified-"+plan.id[:12],c["id"]))
            return c["id"]

    def record(self,plan,obj,event):
        with self.tx(True) as db:
            db.execute("INSERT OR IGNORE INTO verification VALUES(?,?,?)",(plan,obj,compact(event)))

    def save_plan(self, plan, wall=None):
        with self.tx(True) as db:
            db.execute("INSERT INTO plans VALUES(?,?)",(plan.id,compact({"id":plan.id,"commit":plan.commit["id"],
                       "objects":[o.id for o in plan.objects],"mode":plan.mode,"wall":wall,"created":time.time(),
                       "tolerance_mm":plan.tolerance*1000,"dwell_s":plan.dwell_s})))

    def evidence(self,plan):
        with self.tx() as db:
            row=db.execute("SELECT body FROM plans WHERE id=?",(plan,)).fetchone()
            if not row:
                raise ValueError("Unknown plan")
            saved=db.execute("SELECT revision FROM verified_layouts WHERE plan=?",(plan,)).fetchone()
            return {**json.loads(row[0]),"verified_revision":saved[0] if saved else None,"events":[{"object":r[0],**json.loads(r[1])} for r in
                    db.execute("SELECT object,body FROM verification WHERE plan=? ORDER BY rowid",(plan,))]}

    def compare(self, before, after):
        with self.tx() as db:
            return changes(self.commit(db,before)["scene"], self.commit(db,after)["scene"])

    def merge(self, req):
        with self.tx(req.approve) as db:
            branches=self.branches(db)
            left,right=branches.get(req.target),branches.get(req.source)
            if not left or not right or req.target==req.source or left==right:
                raise ValueError("Choose two branches with different tips")
            if req.approve and (left!=req.base_target or right!=req.base_source):
                raise ValueError("A branch moved. Preview the merge again.")
            def ancestors(cid):
                seen={}
                q=[(cid,0)]
                while q:
                    cid,d=q.pop(0)
                    if cid not in seen:
                        seen[cid]=d
                        q.extend((p,d+1) for p in self.commit(db,cid)["parents"])
                return seen
            a,b=ancestors(left),ancestors(right)
            common=min(a.keys()&b.keys(),key=lambda k:(a[k]+b[k],max(a[k],b[k]),k))
            base,l,r=[self.commit(db,i)["scene"] for i in (common,left,right)]
            proposal, conflicts=compare_three(base,l,r,req.object_choices,req.rule_choice)
            candidate=resolve(proposal) if proposal is not None else None
            candidate_id=hashlib.sha256(compact(candidate).encode()).hexdigest()[:20] if candidate is not None else None
            result=dict(target=left,source=right,base=common,conflicts=conflicts,candidate=candidate,candidate_id=candidate_id,
                        target_changes=changes(base,l),source_changes=changes(base,r),
                        placement_changed=(base.get("constraints") or None)!=(l.get("constraints") or None) or
                                          (base.get("constraints") or None)!=(r.get("constraints") or None))
            if req.approve:
                if candidate is None or (conflicts and not req.accept_candidate):
                    raise ValueError("Review and explicitly accept a valid resolution")
                if req.candidate_id and req.candidate_id!=candidate_id:
                    raise ValueError("The candidate changed. Review it before approving.")
                c=self.insert(db,candidate,f"Merge {req.source} into {req.target}",[left,right])
                db.execute("UPDATE branches SET tip=? WHERE name=?",(c["id"],req.target))
                result["commit"]=c
            return result


def changes(before,after):
    left,right=({o["id"]:o for o in s["objects"]} for s in (before,after))
    out=[]
    for key in sorted(left.keys()|right.keys()):
        a,b=left.get(key),right.get(key)
        if a!=b:
            out.append(dict(id=key,kind="added" if a is None else "removed" if b is None else "changed",
                            fields=[f for f in a if a[f]!=b[f]] if a and b else [],before=a,after=b))
    return out


def conflict(kind,ids,message):
    return dict(kind=kind,ids=ids,message=message)


def issues(scene):
    result=[]
    spacing,zones=placement_limits(scene)
    for z in zones:
        if not fits(z,scene.wall):
            result.append(conflict("rule-bounds",[],f"Keep-out area {z.name} extends beyond the wall"))
    for i,a in enumerate(scene.objects):
        if not fits(a,scene.wall):
            result.append(conflict("bounds",[a.id],f"{a.name} extends beyond the measured wall"))
        for b in scene.objects[:i]:
            if intersects(a,b,spacing):
                result.append(conflict("overlap",[b.id,a.id],f"{b.name} and {a.name} overlap or have less than {spacing*1000:g} mm clearance"))
        for zone in zones:
            if intersects(a,zone,0):
                result.append(conflict("keep-out",[a.id],f"{a.name} enters {zone.name}"))
    return result


def placement_limits(scene):
    rules=scene.constraints or PlacementRules()
    zones=[Card(id=z.id,marker=249,name=z.name,x=z.x,y=z.y,w=z.w,h=z.h,d=.01,angle=0) for z in rules.keep_out]
    return rules.clearance_mm/1000,zones


def compare_three(base,left,right,choices=None,rule_choice=None):
    if left["wall"]!=right["wall"]:
        return None,[conflict("wall",[],"Branches use different wall dimensions")]
    maps=[{o["id"]:o for o in s["objects"]} for s in (base,left,right)]
    conflicts=[]
    original,ours,theirs=[PlacementRules.model_validate(s.get("constraints") or {}) for s in (base,left,right)]
    selected=theirs if ours==original else ours
    if ours!=original and theirs!=original and ours!=theirs:
        conflicts.append(conflict("placement-rules",[],"Both branches changed placement rules. Choose which rule set applies."))
        if not rule_choice:
            return None,conflicts
        selected=theirs if rule_choice=="source" else ours
    result=[]
    for key in sorted(set().union(*maps)):
        orig,a,b=[m.get(key) for m in maps]
        chosen=b if a==orig else a
        if a!=orig and b!=orig and a!=b:
            preference=(choices or {}).get(key,"target")
            if orig and a and b:
                fields=[f for f in orig if a[f]!=orig[f] and b[f]!=orig[f] and a[f]!=b[f]]
                chosen={f:(b[f] if a[f]==orig[f] or (f in fields and preference=="source") else a[f]) for f in orig}
                if fields:
                    conflicts.append(conflict("same-object",[key],f"Both branches changed {a['name']}: {', '.join(fields)}. Using {preference} for conflicting fields."))
            else:
                conflicts.append(conflict("same-object",[key],f"Branches disagree on addition or removal of {key}. Using {preference}."))
                chosen=b if preference=="source" else a
        if chosen:
            result.append(chosen)
    if len({o["marker"] for o in result})!=len(result):
        return None,conflicts+[conflict("marker",[],"A marker is assigned to multiple objects")]
    scene=Scene.model_validate({**left,"objects":result,"constraints":selected.model_dump(mode="json")})
    return scene,conflicts+issues(scene)


def resolve(scene):
    placed=[]
    spacing,zones=placement_limits(scene)
    if any(not fits(z,scene.wall) for z in zones):
        return None
    for o in scene.objects:
        def valid(c):
            return (fits(c,scene.wall) and not any(intersects(c,p,spacing) for p in placed)
                    and not any(intersects(c,z,0) for z in zones))
        if valid(o):
            placed.append(o)
            continue
        # Bounded deterministic search, nearest 25 mm grid point first.
        found=None
        for n in range(1,25):
            ring=sorted(((dx,dy) for dx in range(-n,n+1) for dy in range(-n,n+1) if max(abs(dx),abs(dy))==n),
                        key=lambda p:(math.hypot(*p),p))
            for dx,dy in ring:
                probe=o.model_copy(update={"x":round(o.x+dx*.025,5),"y":round(o.y+dy*.025,5)})
                if valid(probe):
                    found=probe
                    break
            if found:
                break
        if not found:
            return None
        placed.append(found)
    return scene.model_copy(update={"objects":placed}).model_dump(mode="json")


def new_id():
    return uuid.uuid4().hex
