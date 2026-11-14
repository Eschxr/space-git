from copy import deepcopy
from io import BytesIO
import json
import struct
import time

from fastapi.testclient import TestClient
import pytest
from PIL import Image

from spacegit_edge.main import make_app
from spacegit_edge.models import Merge, Scene
from spacegit_edge.store import FIXTURE, Store, compare_three, issues, resolve
from worker.mesh import export_mesh
from test_edge import AUTH, TOKEN, synthetic_calibration


def test_live_registration_wizard_ack_and_geometry_change(tmp_path,monkeypatch):
    from spacegit_edge import devices
    from spacegit_edge.camera import Camera
    request,anchors,signature,_=synthetic_calibration()
    monkeypatch.setattr(Camera,"calibration_frame",lambda self:((time.time(),anchors,None),signature))
    monkeypatch.setattr(devices,"monitor_layout",lambda:[dict(id="screen-1",rect=[0,0,1920,1080]),dict(id="screen-2",rect=[1920,0,1600,900])])
    with TestClient(make_app(tmp_path/"live.sqlite3","live",TOKEN)) as client:
        time.sleep(.06)
        def post(route,body):
            return client.post("/api/v1"+route,headers=AUTH,json=body)
        def status():
            return client.get("/api/v1/status",headers=AUTH).json()
        display=dict(id="projector",width=1600,height=900,fullscreen=True,screen=[1920,0],display_key="screen-2")
        assert post("/projector",display).is_success
        cross=post("/calibration/point/0",{}).json()["wizard"]
        assert post("/calibration/point/1",{}).status_code==409
        for i in range(1,12):
            assert post("/projector",{**display,"wizard_key":cross["key"]}).json()["wizard"]["shown"]
            cross=post("/calibration/point/"+str(i),{}).json()["wizard"]
        assert post("/calibration/solve",request.model_dump(mode="json")).status_code==409
        post("/projector",{**display,"wizard_key":cross["key"]}).raise_for_status()
        solved=post("/calibration/solve",request.model_dump(mode="json"))
        assert solved.is_success, solved.text
        time.sleep(.09)
        assert status()["live"]["state"]=="READY"
        ref=post("/calibration/physical-target",{"xy":[1.1,.6]})
        assert ref.is_success, ref.text
        key=ref.json()["key"]
        assert post("/calibration/physical-report",{"key":key,"xy":[1.102,.603]}).status_code==409
        post("/projector",{**display,"wizard_key":key}).raise_for_status()
        measured=post("/calibration/physical-report",{"key":key,"xy":[1.102,.603]})
        assert measured.is_success and measured.json()["error_mm"]==pytest.approx(3.60555,rel=.0001)
        saved=client.get("/api/v1/calibration/diagnostics",headers=AUTH).json()
        assert saved["physical"][0]["provenance"]=="operator_ruler_measurement"
        assert saved["software_latency"]["count"]==0
        assert not post("/projector",{**display,"width":1560}).json()["allow_guidance"]
        time.sleep(.08)
        assert status()["live"]["state"]=="SETUP_REQUIRED"
        assert "resolution" in status()["live"]["calibration_reason"]


def test_merge_rules_and_candidate_hash_preserve_both_histories(tmp_path):
    db=Store(tmp_path/"merge.sqlite3")
    db.seed(True)
    base=db.list()["commits"][0]
    db.branch("incoming",base["id"])
    left,right=deepcopy(FIXTURE),deepcopy(FIXTURE)
    left["constraints"]={"clearance_mm":15,"keep_out":[dict(id="zone",name="Protected trim",x=.76,y=.96,w=.18,h=.14)]}
    right["constraints"]={"clearance_mm":16,"keep_out":[]}
    right["objects"][0]["x"]=.69
    lc=db.save("main",base["id"],Scene.model_validate(left),"Protected trim",None)
    rc=db.save("incoming",base["id"],Scene.model_validate(right),"Move card",None)
    request=Merge(target="main",source="incoming")
    assert db.merge(request)["candidate"] is None
    request.rule_choice="target"
    preview=db.merge(request)
    assert preview["candidate"] and not issues(Scene.model_validate(preview["candidate"]))
    assert {"keep-out","placement-rules"}<={c["kind"] for c in preview["conflicts"]}
    request.approve=request.accept_candidate=True
    request.base_target,request.base_source=lc["id"],rc["id"]
    request.candidate_id="stale"
    with pytest.raises(ValueError,match="candidate changed"):
        db.merge(request)
    request.candidate_id=preview["candidate_id"]
    result=db.merge(request)["commit"]
    assert result["parents"]==[lc["id"],rc["id"]]
    assert db.list()["branches"]["incoming"]==rc["id"]


def test_three_way_keeps_independent_fields_and_requires_choice_for_collision():
    a,b=deepcopy(FIXTURE),deepcopy(FIXTURE)
    a["objects"][0]["x"]+=.08
    b["objects"][0]["angle"]=.12
    candidate,conflicts=compare_three(FIXTURE,a,b)
    assert not conflicts
    assert candidate.objects[0].x==a["objects"][0]["x"] and candidate.objects[0].angle==.12
    b["objects"][0]["x"]-=.07
    candidate,conflicts=compare_three(FIXTURE,a,b,{"a":"source"})
    assert conflicts[0]["kind"]=="same-object"
    assert resolve(candidate)["objects"][0]["x"]==b["objects"][0]["x"]


def test_textured_glb_export_and_separate_asset_placement(tmp_path):
    mesh=tmp_path/"input.ply"
    header=(b"ply\nformat binary_little_endian 1.0\nelement vertex 4\nproperty float x\nproperty float y\nproperty float z\n"
            b"element face 4\nproperty list uchar int vertex_indices\nproperty list uchar float texcoord\nend_header\n")
    pts=((0,0,0),(1,0,0),(0,1,0),(0,0,1))
    tri=((0,1,2),(0,2,3),(0,3,1),(1,3,2))
    mesh.write_bytes(header+b"".join(struct.pack("<3f",*p) for p in pts)+
                     b"".join(struct.pack("<B3iB6f",3,*f,6,0,0,1,0,0,1) for f in tri))
    atlas=tmp_path/"atlas.png"
    Image.new("RGB",(12,12),(100,150,200)).save(atlas)
    path=tmp_path/"demo.sqlite3"
    asset="genuine-test-tetra"
    with TestClient(make_app(path,"demo",TOKEN)) as client:
        before=client.get("/api/v1/commits",headers=AUTH).json()
        commit=before["branches"]["main"]
        folder=tmp_path/"demo-files"/"jobs"/asset
        folder.mkdir(parents=True)
        names,n=export_mesh(mesh,folder,atlas)
        assert n==4 and set(names)=={"model.obj","model.glb","textured-obj.zip"}
        with Store(path).tx(True) as db:
            body=dict(id=asset,asset=asset,commit=commit,artifacts=[{"name":name} for name in names])
            db.execute("INSERT INTO jobs VALUES(?,?,?)",(asset,"complete",json.dumps(body)))
        root="/api/v1/assets/"+asset
        assert client.get(root+"/model.glb").status_code==401
        assert client.get(root+"/texture.png",headers=AUTH).status_code==404
        out=client.get(root+"/model.glb",headers=AUTH)
        assert out.is_success
        n=struct.unpack_from("<I",out.content,12)[0]
        gltf=json.loads(out.content[20:20+n])
        assert gltf["images"][0]["mimeType"]=="image/png"
        assert gltf["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"] is not None
        assert gltf["accessors"][2]["count"]==12
        save=client.post(root+"/placement",headers=AUTH,json={"commit":commit,"reference_m":.4,"reference_units":2})
        assert save.is_success and save.json()["scale"]==.2
        assert client.get(root+"/placement/"+commit,headers=AUTH).json()==save.json()
        assert client.get("/api/v1/commits",headers=AUTH).json()==before


def test_phone_session_scopes_requests_and_records_exif_metadata(tmp_path,monkeypatch):
    origin="https://capture.example.test"
    monkeypatch.setenv("SPACEGIT_MOBILE_ORIGIN",origin)
    with TestClient(make_app(tmp_path/"demo.sqlite3","demo",TOKEN)) as client:
        commit=client.get("/api/v1/commits",headers=AUTH).json()["branches"]["main"]
        pair=client.post("/api/v1/capture/pair/"+commit,headers=AUTH).json()
        lease=pair["url"].split("#pair=")[-1]
        phone={"Origin":origin,"Authorization":"Bearer "+lease,"User-Agent":"Safari on iPhone"}
        assert client.get("/api/v1/capture/paired",headers=phone).json()["count"]==0
        assert client.post("/api/v1/capture/paired/request",headers=phone,json={"quality":"mesh"}).status_code==409
        exif=Image.Exif()
        exif[274]=6
        for i in range(6):
            image=BytesIO()
            Image.new("RGB",(600,480),(20*i,22,40)).save(image,format="JPEG",exif=exif)
            r=client.post("/api/v1/capture/photos",headers=phone,files={"image":("scan.jpg",image.getvalue(),"image/jpeg")})
            assert r.is_success, r.text
            assert r.json()["metadata"]["display_resolution"]==[480,600]
            assert r.json()["metadata"]["device"]=="iPhone"
            assert r.json()["session"]==pair["session"]
        assert client.post("/api/v1/capture/paired/request",headers=phone,json={"quality":"mesh"}).is_success
        assert client.post("/api/v1/reconstructions",headers=phone,json={"photos":["a"]*6}).status_code==403
        sess=client.get("/api/v1/capture/sessions",headers=AUTH).json()[0]
        assert sess["count"]==6 and sess["request_quality"]=="mesh" and sess["commit"]==commit
