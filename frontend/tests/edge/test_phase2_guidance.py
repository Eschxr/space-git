from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from spacegit_edge.geometry import mapped
from spacegit_edge.models import Scene
from spacegit_edge.navigation import Plan
from spacegit_edge.quality import (Timing, correct_pixels, estimate_intrinsics, fingerprint,
                                   geometry_reason, physical_point, residuals, topology_id)
from spacegit_edge.store import FIXTURE, Store


def test_projector_binding_fails_on_resolution_topology_or_display_change():
    signature={"index":0,"resolution":[1280,720]}
    display={"width":1920,"height":1080,"screen":[-1920,0],"display_key":"display2","fullscreen":True}
    layout=[{"id":"a","rect":[0,0,1920,1080]},{"id":"b","rect":[-1920,0,1920,1080]}]
    topology=topology_id(layout)
    cal={"signature":signature,"display_fingerprint":fingerprint(display,topology)}
    assert geometry_reason(cal,signature,display,topology) is None
    assert topology_id(list(reversed(layout)))==topology
    for changed in (dict(width=1600),dict(display_key="display3"),dict(screen=[0,0]),dict(fullscreen=False)):
        assert geometry_reason(cal,signature,{**display,**changed},topology)
    assert geometry_reason(cal,signature,display,topology_id(layout[:1]))
    assert geometry_reason(cal,dict(index=1,resolution=[1280,720]),display,topology)
    assert geometry_reason({"signature":signature},signature,display,topology)


def test_guidance_direction_configured_dwell_and_occlusion():
    card=Scene.model_validate(FIXTURE).objects[0]
    cal={"id":"test","wall":[2.4,1.4],"output":[1200,700],"wall_to_projector":[[430,20,40],[10,-430,640],[.01,.02,1]]}
    plan=Plan({"id":"r","scene":FIXTURE},[card],"demo",tolerance_mm=10,dwell_s=1.2)
    saved=[]
    p={"x":card.x+.03,"y":card.y-.05,"marker":card.marker,"angle":0,"confidence":1}
    def tick(t,health="READY"):
        return plan.update(t,t,int(t*1000),[p],health,cal,lambda *v:saved.append(v))
    assert tick(10)=="MOVING"
    overlay=plan.overlay("MOVING",[p],cal)
    assert overlay["arrow"][0]==pytest.approx(overlay["from"])
    assert overlay["arrow"][-1]==pytest.approx(overlay["to"])
    assert overlay["to"]==pytest.approx(physical_point(cal,(card.x,card.y)))
    p.update(x=card.x+.009,y=card.y)
    assert tick(10.1)=="NEAR_TARGET"
    for i in range(1,8):
        assert tick(10.1+i*.1)=="NEAR_TARGET"
    p["confidence"]=.3
    assert tick(11)=="TRACKING_LOST"
    assert plan.overlay("TRACKING_LOST",[p],cal) is None
    assert plan.overlay("MOVING",[],cal) is None
    p["confidence"]=1
    for i in range(12):
        assert tick(11.1+i*.1)=="NEAR_TARGET"
    assert tick(12.4)=="VERIFIED"
    assert saved[0][2]["tolerance_mm"]==10
    assert saved[0][2]["required_dwell_s"]==1.2
    assert tick(12.5,"CALIBRATION_DRIFT")=="CALIBRATION_DRIFT"


def test_software_timing_dedup_and_physical_provenance():
    t=Timing()
    for seq in range(1,6):
        t.observe(seq,100+seq/100,"projector")
    t.collect([SimpleNamespace(seq=i,paint_ms=100000+i*20) for i in range(1,6)],"wrong-projector",100150)
    assert t.summary()["count"]==0
    hits=[SimpleNamespace(seq=i,paint_ms=100000+i*20) for i in range(1,6)]
    t.collect(hits,"projector",100150)
    t.collect(hits,"projector",100150)
    assert t.summary()["count"]==5
    assert t.summary()["p50_ms"]==pytest.approx(30)
    assert t.summary()["p95_ms"]==pytest.approx(48)
    assert residuals((.5,.4),(.503,.404))["error_mm"]==pytest.approx(5)


def test_intrinsics_solver_recovers_synthetic_camera():
    rng=np.random.default_rng(42)
    model=np.zeros((54,3),np.float32)
    model[:,:2]=np.mgrid[0:9,0:6].T.reshape(-1,2)
    k=np.array([[1050.,0,640],[0,1040,360],[0,0,1.]])
    dist=np.array([.07,-.04,.001,-.003,.008])
    views=[]
    for i in range(22):
        r=rng.uniform(-.32,.32,3)
        t=np.array([rng.uniform(-9,3),rng.uniform(-5,1),rng.uniform(15,27)])
        views.append(cv2.projectPoints(model,r,t,k,dist)[0].reshape(-1,2))
    result=estimate_intrinsics(views,[1280,720])
    assert result["rms_px"]<.001
    assert result["matrix"][0][0]==pytest.approx(1050,rel=.002)
    raw=cv2.projectPoints(model,np.zeros(3),np.array([-4.,-2,16]),k,dist)[0]
    ideal=cv2.projectPoints(model,np.zeros(3),np.array([-4.,-2,16]),k,np.zeros(5))[0].reshape(-1,2)
    assert np.max(np.linalg.norm(correct_pixels(raw,result)-ideal,axis=1))<.05
    with pytest.raises(ValueError,match="Move the board"):
        estimate_intrinsics([views[0]]*10,[1280,720])


def test_verified_layout_commit_is_immutable_and_does_not_move_main(tmp_path):
    db=Store(tmp_path/"test.db")
    db.seed(True)
    before=db.list()
    target=before["commits"][0]
    cards=Scene.model_validate(target["scene"]).objects
    plan=Plan(target,cards,"live")
    plan.completed=True
    db.save_plan(plan)
    poses=[dict(marker=o.marker,x=o.x+.002,y=o.y,angle=o.angle,confidence=.9) for o in cards]
    cid=db.save_verified(plan,poses,"cal",91,1234.)
    assert db.save_verified(plan,poses,"cal",91,1234.)==cid
    after=db.list()
    assert after["branches"]["main"]==target["id"]
    assert after["commits"][0]["parents"]==[target["id"]]
    assert after["commits"][0]["scene"]["objects"][0]["x"]==pytest.approx(cards[0].x+.002)
    assert db.evidence(plan.id)["verified_revision"]==cid
