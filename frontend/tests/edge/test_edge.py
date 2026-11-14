from io import BytesIO
import json
import math
import sqlite3
import time

import cv2
from fastapi.testclient import TestClient
import numpy as np
from PIL import Image
import pytest

from spacegit_edge.camera import Tracker, detect
from spacegit_edge.geometry import FIT, CHECK, mapped, solve
from spacegit_edge.main import make_app
from spacegit_edge.models import CalibrationInput, Scene
from spacegit_edge.navigation import Plan
from spacegit_edge.store import FIXTURE, issues
from worker.main import process_one

TOKEN="test-only-local-operator-token-1234"
AUTH={"Authorization":f"Bearer {TOKEN}"}
ORIGIN="http://127.0.0.1:3000"


def synthetic_calibration():
    w2c=np.array([[360,20,150],[10,-365,652],[.015,.023,1.]])
    p2c=np.array([[.61,.02,90],[-.012,.68,78],[.00002,.00002,1.]])
    sig=dict(index=0,resolution=[1280,800],dictionary="DICT_4X4_250")
    anchors={}
    for i,(x,y) in enumerate([(0,0),(2.4,0),(2.4,1.4),(0,1.4)]):
        anchors[i]=mapped(w2c,[(x-.03,y+.03),(x+.03,y+.03),(x+.03,y-.03),(x-.03,y-.03)]).tolist()
    fit=mapped(p2c,np.array(FIT)*[1600,900]).tolist()
    check=mapped(p2c,np.array(CHECK)*[1600,900]).tolist()
    req=CalibrationInput(wall=(2.4,1.4),marker_m=.06,output=(1600,900),fit=fit,check=check)
    return req,anchors,sig,w2c


def test_calibration_independent_validation_and_missing_anchor():
    req,anchors,sig,w2c=synthetic_calibration()
    cal=solve(req,anchors,sig)
    print(f"synthetic calibration mean={cal['mean_px']:.7f} px max={cal['max_px']:.7f} px")
    assert cal["max_px"]<.001
    known=[(.4,.63),(1.9,1.14)]
    assert np.allclose(mapped(cal["camera_to_wall"],mapped(w2c,known)),known,atol=1e-6)
    check=list(req.check)
    check[3]=(check[3][0]+27,check[3][1])
    with pytest.raises(ValueError,match="Validation failed"):
        solve(req.model_copy(update={"check":check}),anchors,sig)
    with pytest.raises(ValueError,match="four wall markers"):
        solve(req,{k:v for k,v in anchors.items() if k!=2},sig)


def test_generated_camera_frame_detects_markers_and_motion():
    dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
    frame=np.full((720,1000,3),255,np.uint8)
    for idx,(x,y) in enumerate([(80,620),(840,620),(840,40),(80,40),(400,300),(570,300),(690,300),(440,470)]):
        marker=cv2.aruco.generateImageMarker(dictionary,idx if idx<4 else idx+13,45)
        frame[y:y+45,x:x+45]=cv2.cvtColor(marker,cv2.COLOR_GRAY2BGR)
    markers=detect(frame,"DICT_4X4_250")
    assert sorted(markers)==[0,1,2,3,17,18,19,20]
    req,anchors,sig,w2c=synthetic_calibration()
    cal=solve(req,anchors,sig)
    tracker=Tracker()
    def card(x):
        return mapped(w2c,[(x-.03,.7),(x+.03,.7),(x+.03,.64),(x-.03,.64)]).tolist()
    tracker.ingest(1,{**anchors,17:card(.5)},cal)
    assert tracker.poses[0]["x"]==pytest.approx(.5,abs=.001)
    tracker.ingest(.9,{17:card(.6)},cal)
    assert tracker.poses[0]["x"]==pytest.approx(.5,abs=.001)
    tracker.ingest(1.05,{**anchors,17:card(.85)},cal)
    assert not tracker.poses
    tracker.ingest(1.1,{**anchors,17:card(.855)},cal)
    assert tracker.poses[0]["x"]==pytest.approx(.855,abs=.001)
    shifted={**anchors,0:(np.array(anchors[0])+20).tolist()}
    tracker.ingest(1.2,shifted,cal)
    assert tracker.drift


def test_guidance_dwell_requires_fresh_uninterrupted_frames():
    scene=Scene.model_validate(FIXTURE)
    a=scene.objects[0]
    cal={"id":"cal","output":[1600,900],"wall_to_projector":[[600,0,80],[0,-600,850],[0,0,1]]}
    plan=Plan({"id":"rev","scene":FIXTURE},[a],"demo")
    logs=[]
    pose=dict(marker=17,x=a.x+.11,y=a.y,angle=0,confidence=1)
    def tick(t,poses,frame=None,health="READY"):
        return plan.update(t,t if frame is None else frame,int(t*100),poses,health,cal,lambda *event:logs.append(event))
    assert tick(1,[pose])=="MOVING"
    assert plan.overlay("MOVING",[pose],cal)["distance_m"]==pytest.approx(.11)
    pose["x"]=a.x
    assert tick(1.1,[pose])=="NEAR_TARGET"
    assert tick(1.2,[])=="TRACKING_LOST"
    assert plan.overlay("TRACKING_LOST",[],cal) is None
    for i in range(10):
        assert tick(1.3+i*.05,[pose],frame=1.3)=="NEAR_TARGET"
    assert tick(1.8,[pose],health="CALIBRATION_DRIFT")=="CALIBRATION_DRIFT"
    assert not logs
    for i in range(8):
        result=tick(2+i*.101,[pose])
    assert result=="VERIFIED"
    assert len(logs)==1 and logs[0][2]["dwell_s"]>=.7


def test_api_revision_merge_restore_replay_and_authorization(tmp_path):
    path=tmp_path/"demo.sqlite3"
    with TestClient(make_app(path,"demo",TOKEN)) as client:
        assert client.get("/health").json()["mode"]=="demo"
        assert client.get("/api/v1/commits").status_code==401
        assert client.get("/api/v1/commits",headers={**AUTH,"Origin":"https://untrusted.example"}).status_code==403
        def get(path):return client.get("/api/v1"+path,headers=AUTH)
        def post(path,payload):return client.post("/api/v1"+path,headers=AUTH,json=payload)
        baseline=get("/commits").json()["commits"][0]
        base=baseline["id"]
        assert post("/branches",{"name":"proposal","commit":base}).is_success
        def save(branch,x):
            scene=json.loads(json.dumps(baseline["scene"]))
            scene["objects"][0]["x"]=x
            return post("/commits",{"branch":branch,"expected":base,"scene":scene,"message":branch})
        left=save("main",.52).json()
        right=save("proposal",.62).json()
        assert save("main",.63).status_code==409
        changes=post("/diff",{"before":base,"after":right["id"]}).json()
        assert changes[0]["fields"]==["x"]
        opts={"target":"main","source":"proposal"}
        preview=post("/merge",opts).json()
        assert preview["conflicts"][0]["kind"]=="same-object"
        approval={**opts,"approve":True,"base_target":left["id"],"base_source":right["id"]}
        assert post("/merge",approval).status_code==409
        merged=post("/merge",{**approval,"accept_candidate":True}).json()["commit"]
        assert merged["parents"]==[left["id"],right["id"]]
        assert get("/scenes/gallery-01").json()==merged["scene"]
        with sqlite3.connect(path) as db,pytest.raises(sqlite3.IntegrityError,match="immutable"):
            db.execute("UPDATE commits SET body='{}' WHERE id=?",(base,))
        with client.websocket_connect("/ws/live",headers={"origin":ORIGIN},subprotocols=["spacegit.v1"]) as ws:
            ws.send_text(TOKEN)
            first=ws.receive_json()
            assert first["mode"]=="demo" and len(first["poses"])==6
            pid=post("/deployments",{"commit":base,"object_id":"a"}).json()["id"]
            assert post("/demo/replay",{}).is_success
            seen=set()
            lags=[]
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                event=ws.receive_json()
                if event["plan"] and event["plan"]["id"]==pid:
                    seen.add(event["state"])
                    lags.append((time.time()-event["timestamp"])*1000)
                    if event["plan"]["done"]:
                        break
            assert {"MOVING","NEAR_TARGET","VERIFIED"}<=seen
            print(f"fixture timestamp to test client median={np.median(lags):.2f} ms; p95={np.percentile(lags,95):.2f} ms")
        result=get("/deployments/"+pid).json()
        assert len(result["events"])==1 and result["events"][0]["mode"]=="demo"
    with TestClient(make_app(path,"demo",TOKEN)) as client:
        assert client.get("/api/v1/deployments/"+pid,headers=AUTH).json()==result


def test_merge_geometry_resolves_overlap_and_rejects_impossible():
    import copy
    from spacegit_edge.store import compare_three, resolve
    left,right=copy.deepcopy(FIXTURE),copy.deepcopy(FIXTURE)
    left["objects"][0]["x"]=.71
    right["objects"][1]["x"]=.90
    proposed,conflicts=compare_three(FIXTURE,left,right)
    assert any(c["kind"]=="overlap" for c in conflicts)
    assert not issues(Scene.model_validate(resolve(proposed)))
    bad=proposed.model_copy(update={"wall":(.1,.1)})
    assert resolve(bad) is None


def test_capture_scope_and_worker_missing_colmap(tmp_path,monkeypatch):
    monkeypatch.setenv("SPACEGIT_MOBILE_ORIGIN","https://capture.example.test")
    path=tmp_path/"demo.sqlite3"
    with TestClient(make_app(path,"demo",TOKEN)) as client:
        commit=client.get("/api/v1/commits",headers=AUTH).json()["branches"]["main"]
        paired=client.post("/api/v1/capture/pair/"+commit,headers=AUTH).json()["url"].split("#pair=")[1]
        phone={"Authorization":"Bearer "+paired,"Origin":"https://capture.example.test"}
        assert client.get("/api/v1/commits",headers=phone).status_code==403
        assert client.post("/api/v1/capture/photos",headers=phone,
            files={"image":("invalid.png",b"not a PNG","image/png")}).status_code==422
        ids=[]
        for i in range(6):
            out=BytesIO()
            Image.new("RGB",(640,480),(i,0,0)).save(out,format="PNG")
            file={"image":("photo.png",out.getvalue(),"image/png")}
            r=client.post("/api/v1/capture/photos",files=file,headers=phone)
            assert r.is_success and r.json()["commit"]==commit
            ids.append(r.json()["id"])
        assert client.post("/api/v1/capture/photos",files=file,headers=phone).json()["id"]==ids[-1]
        job=client.post("/api/v1/reconstructions",json={"photos":ids},headers=AUTH)
        assert job.is_success
        assert process_one(path,"missing-spacegit-test-colmap")
        result=client.get("/api/v1/reconstructions",headers=AUTH).json()["jobs"][0]
        assert result["stage"]=="failed" and "COLMAP unavailable" in result["message"]
        assert client.get("/api/v1/assets/"+result["id"],headers=AUTH).status_code==404
        retry = client.post(f"/api/v1/reconstructions/{result['id']}/retry", headers=AUTH)
        assert retry.is_success
        replacement = retry.json()
        assert replacement["id"] != result["id"] and replacement["photos"] == ids
        cancel = f"/api/v1/reconstructions/{replacement['id']}/cancel"
        assert client.post(cancel, headers=phone).status_code == 403
        assert client.post(cancel, headers=AUTH).json()["stage"] == "cancelled"
        assert not process_one(path, "missing-spacegit-test-colmap")
        assert len(list((tmp_path/"demo-files/photos").glob("*.png")))==6
