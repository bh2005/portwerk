"""Zurückgebaute Geräte geben ihren Hostnamen frei; ein Ersatzgerät kann denselben Namen tragen."""
import pytest


def model_id(client, admin, name):
    return [m for m in client.get("/api/device-models?q=Generisch", headers=admin).json() if m["model"] == name][0]["id"]


@pytest.fixture()
def rack(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    r = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 10}).json()
    return {"rack": r["id"], "site": s["id"]}


def body(rack, **kw):
    return {"hostname": "sw-01", "type": "switch", "location_id": rack["rack"], "rack_position": 3, **kw}


def run_order(client, admin, wid):
    wo = client.get(f"/api/workorders/{wid}", headers=admin).json()
    for act in ("submit", "approve", "start"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200
    for it in wo["items"]:
        assert client.post(f"/api/workorders/{wid}/items/{it['id']}/execute", headers=admin, json={"item_status": "done"}).status_code == 200
    for act in ("finish", "confirm"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200


def host(client, admin, did):
    return client.get(f"/api/devices/{did}", headers=admin).json()


def test_direct_replacement_keeps_the_name_and_renames_the_old_device(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    old = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid)).json()["device_id"]
    q = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid))
    assert q.status_code == 409 and q.json()["detail"]["code"] == "slot_busy"                 # erst die Rückfrage, nicht „Name existiert“
    new = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, replace_devices=True))
    assert new.status_code == 200, new.text
    assert host(client, admin, new.json()["device_id"])["hostname"] == "sw-01"                # Ersatz trägt den Wunschnamen
    o = host(client, admin, old)
    assert o["status"] == "retired" and o["hostname"].startswith("sw-01~zurückgebaut-") and o["former_hostname"] == "sw-01"
    assert o["retired_at"] and o["planned_hostname"] == ""


def test_workorder_replacement_uses_temporary_name_until_removal(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    old = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid)).json()["device_id"]
    req = body(rack, model_id=mid, mode="workorder", replace_devices=True)
    dry = client.post("/api/wizards/device", headers=admin, json={**req, "dry_run": True}).json()
    assert dry["device"]["hostname"] == "sw-01" and dry["device"]["temporary_hostname"] == "sw-01~geplant"
    r = client.post("/api/wizards/device", headers=admin, json=req)
    assert r.status_code == 200, r.text
    new_id, wo = r.json()["device_id"], r.json()["workorder"]
    n = host(client, admin, new_id)
    assert n["hostname"] == "sw-01~geplant" and n["planned_hostname"] == "sw-01" and n["status"] == "planned"
    assert host(client, admin, old)["hostname"] == "sw-01"                                    # noch nicht ausgebaut
    run_order(client, admin, wo["removal_order"]["id"])                                       # Rückbau bestätigt -> Name wird frei und übernommen
    assert host(client, admin, old)["hostname"].startswith("sw-01~zurückgebaut-")
    n = host(client, admin, new_id)
    assert n["hostname"] == "sw-01" and n["planned_hostname"] == "" and n["status"] == "planned"
    run_order(client, admin, wo["id"])
    assert host(client, admin, new_id)["status"] == "active"


def test_name_is_free_again_after_removal_and_unrelated_duplicates_still_rejected(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    a = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid)).json()["device_id"]
    dup = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, rack_position=6))
    assert dup.status_code == 409 and "existiert bereits" in dup.json()["detail"]             # anderer Platz: echter Namenskonflikt
    # Rückbau per Patchauftrag-Position, danach ist der Name frei
    wo = client.post("/api/workorders", headers=admin, json={"title": "Weg damit", "location_id": rack["rack"]}).json()
    assert client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "remove_device", "device_id": a}).status_code == 201
    run_order(client, admin, wo["id"])
    again = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, rack_position=6))
    assert again.status_code == 200, again.text
    assert host(client, admin, again.json()["device_id"])["hostname"] == "sw-01"
    assert host(client, admin, a)["former_hostname"] == "sw-01"
    # zweiter Rückbau mit gleichem Namen: Namen der Historie kollidieren nicht
    wo2 = client.post("/api/workorders", headers=admin, json={"title": "Nochmal", "location_id": rack["rack"]}).json()
    client.post(f"/api/workorders/{wo2['id']}/items", headers=admin, json={"action": "remove_device", "device_id": again.json()["device_id"]})
    run_order(client, admin, wo2["id"])
    names = sorted(d["hostname"] for d in client.get("/api/devices?q=zurückgebaut", headers=admin).json()["items"])
    assert len(names) == 2 and len(set(names)) == 2


def test_retire_is_idempotent(client, admin, rack):
    from app.routers import workorders
    mid = model_id(client, admin, "Switch 8 Port")
    a = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid)).json()["device_id"]
    workorders.retire_device(a)
    first = host(client, admin, a)["hostname"]
    workorders.retire_device(a)                                                               # zweiter Aufruf ändert den Namen nicht
    assert host(client, admin, a)["hostname"] == first
