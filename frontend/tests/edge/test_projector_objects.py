from fastapi import HTTPException
from fastapi.testclient import TestClient

from spacegit_edge.main import make_app
from spacegit_edge.projector_chat import (
    ChairDesign,
    FurnitureDesign,
    GridPart,
    build_chair,
    build_furniture,
    disconnected_parts,
)


def dining_chair():
    return build_chair(ChairDesign(name="Red chair", placement="left", style="dining", seat_color="#be242a",
                                   frame_color="#704432", surface="wood"))


def test_dining_chair_has_connected_legs_seat_and_backrest():
    chair = dining_chair()
    seat, *rest = chair.parts
    legs = [part for part in rest if part.position[1] < .3]
    assert len(legs) == 4
    assert {(part.position[0] > 0, part.position[2] > 0) for part in legs} == {
        (False, False), (False, True), (True, False), (True, True)
    }
    for leg in legs:
        assert leg.position[1] - leg.size[1] / 2 == 0
        assert leg.position[1] + leg.size[1] / 2 > seat.position[1] - seat.size[1] / 2
    posts = [part for part in rest if .5 < part.position[1] < .7]
    back = next(part for part in rest if part.position[1] > .7)
    assert len(posts) == 2
    assert back.position[2] < 0 and back.color == seat.color
    assert all(post.position[1] + post.size[1] / 2 > back.position[1] - back.size[1] / 2 for post in posts)


def test_failed_regeneration_preserves_the_previous_generated_object(tmp_path, monkeypatch):
    token = "projector-objects-test-token"
    headers = {"Authorization": "Bearer " + token}
    url = "/api/v1/projector/scenes/rig-one/objects"
    monkeypatch.setattr("spacegit_edge.main.generate_projector_object", lambda _: dining_chair())
    with TestClient(make_app(path=tmp_path / "objects.sqlite3", mode="demo", token=token)) as client:
        created = client.post(url, json={"prompt":"add a red dining chair", "request_id":"chair1"}, headers=headers)
        assert created.status_code == 201

        def fail(_):
            raise HTTPException(503, "Ollama unavailable")

        monkeypatch.setattr("spacegit_edge.main.generate_projector_object", fail)
        assert client.post(url + "/chair1/regenerate", headers=headers).status_code == 503
        assert client.get(url, headers=headers).json() == [created.json()]


def test_saved_position_is_version_scoped_and_survives_regeneration(tmp_path, monkeypatch):
    token = "projector-objects-test-token"
    headers = {"Authorization": "Bearer " + token}
    url = "/api/v1/projector/scenes/rig-one/objects"
    path = tmp_path / "objects.sqlite3"
    monkeypatch.setattr("spacegit_edge.main.generate_projector_object", lambda _: dining_chair())
    with TestClient(make_app(path=path, mode="demo", token=token)) as client:
        assert client.post(url, json={"prompt":"add a red dining chair", "request_id":"chair1"}, headers=headers).status_code == 201
        move = url + "/chair1/position"
        assert client.post(move, json={"offset":[101, 0, 0]}, headers=headers).status_code == 422
        assert client.post(move.replace("rig-one", "rig-two"), json={"offset":[1.25, .2, -.1]}, headers=headers).status_code == 404
        assert client.post(move, json={"offset":[1.25, .2, -.1]}, headers=headers).json()["offset"] == [1.25, .2, -.1]
        renewed = client.post(url + "/chair1/regenerate", headers=headers)
        assert renewed.status_code == 200 and renewed.json()["offset"] == [1.25, .2, -.1]
    with TestClient(make_app(path=path, mode="demo", token=token)) as client:
        assert client.get(url, headers=headers).json()[0]["offset"] == [1.25, .2, -.1]


def test_round_table_has_a_connected_top_pedestal_and_base():
    table = build_furniture("table", FurnitureDesign(name="Round oak table", placement="center", style="round",
                            primary_color="#b68d56", secondary_color="#222222", accent_color="#777777", finish="wood"))
    top, pedestal, base = table.parts
    assert [part.shape for part in table.parts] == ["cylinder"] * 3
    assert pedestal.position[1] + pedestal.size[1] / 2 >= top.position[1] - top.size[1] / 2
    assert pedestal.position[1] - pedestal.size[1] / 2 <= base.position[1] + base.size[1] / 2
    assert top.size[0] > base.size[0] > pedestal.size[0]


def test_freeform_connectivity_rejects_floating_parts():
    base = GridPart(role="mounting plate", shape="rounded-box", x=0, z=0, bottom=0, size=(36, 4, 36), color="#222222")
    cone = GridPart(role="pointed body", shape="cone", x=0, z=0, bottom=4, size=(32, 48, 32), color="#ff7518")
    floating = GridPart(role="ornament", shape="sphere", x=0, z=0, bottom=100, size=(20, 20, 20), color="#ff7518")
    assert disconnected_parts([base, cone]) == []
    assert disconnected_parts([floating, cone, base]) == ["ornament"]
