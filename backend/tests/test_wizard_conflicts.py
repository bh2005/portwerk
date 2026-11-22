"""Logikprüfung beim Planen: belegter Port / belegte HE -> Rückfrage und automatischer Rückbau-Patchauftrag."""
import pytest


def model_id(client, admin, name):
    return [m for m in client.get("/api/device-models?q=Generisch", headers=admin).json() if m["model"] == name][0]["id"]


@pytest.fixture()
def rack(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    r = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 10}).json()
    pp = client.post("/api/devices", headers=admin, json={"hostname": "pp-1", "type": "patchpanel", "location_id": r["id"], "rack_position": 10}).json()
    port = client.post(f"/api/devices/{pp['id']}/ports", headers=admin, json={"name": "P1", "medium": "RJ45"}).json()
    return {"site": s["id"], "rack": r["id"], "pp_port": port["id"]}


def body(rack, **kw):
    return {"hostname": "sw-neu", "type": "switch", "location_id": rack["rack"], "rack_position": 1, **kw}


def run_order(client, admin, wid):
    wo = client.get(f"/api/workorders/{wid}", headers=admin).json()
    for act in ("submit", "approve", "start"):
        r = client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"})
        assert r.status_code == 200, (act, r.text)
    for it in wo["items"]:
        assert client.post(f"/api/workorders/{wid}/items/{it['id']}/execute", headers=admin, json={"item_status": "done"}).status_code == 200
    for act in ("finish", "confirm"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200


def test_port_busy_direct_removes_old_cable_after_confirmation(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    first = client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="alt", model_id=mid, rack_position=1,
                        uplink={"port_name": "Port1", "target_port_id": rack["pp_port"], "cable_label": "ALT"}))
    assert first.status_code == 200
    new = body(rack, hostname="neu", model_id=mid, rack_position=2, uplink={"port_name": "Port1", "target_port_id": rack["pp_port"], "cable_label": "NEU"})
    q = client.post("/api/wizards/device", headers=admin, json=new)
    assert q.status_code == 409 and q.json()["detail"]["code"] == "port_busy" and "sofort" in q.json()["detail"]["message"]
    ok = client.post("/api/wizards/device", headers=admin, json={**new, "remove_old": True})
    assert ok.status_code == 200, ok.text
    assert [c["cable_label"] for c in client.get("/api/cables", headers=admin).json()] == ["NEU"]          # alter Patch ist weg


def test_port_busy_workorder_creates_removal_order_and_blocks_start(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="alt", model_id=mid, rack_position=1,
                uplink={"port_name": "Port1", "target_port_id": rack["pp_port"], "cable_label": "ALT"}))
    new = body(rack, hostname="neu", model_id=mid, rack_position=2, mode="workorder",
               uplink={"port_name": "Port1", "target_port_id": rack["pp_port"], "cable_label": "NEU"})
    q = client.post("/api/wizards/device", headers=admin, json=new)
    assert q.status_code == 409 and "Rückbau-Patchauftrag" in q.json()["detail"]["message"]
    dry = client.post("/api/wizards/device", headers=admin, json={**new, "remove_old": True, "dry_run": True}).json()
    assert dry["removals"]["cables"] == ["pp-1:P1 ↔ alt:Port1"] and dry["removals"]["via"] == "Rückbau-Patchauftrag"
    ok = client.post("/api/wizards/device", headers=admin, json={**new, "remove_old": True})
    assert ok.status_code == 200, ok.text
    wo = ok.json()["workorder"]
    assert wo["removal_order"]
    rem = client.get(f"/api/workorders/{wo['removal_order']['id']}", headers=admin).json()
    assert rem["title"].startswith("Rückbau vor") and rem["status"] == "draft"
    assert [(i["action"], i["port_a"]["device_hostname"]) for i in rem["items"]] == [("disconnect", "pp-1")]
    main = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()
    assert main["depends_on"]["number"] == rem["number"] and main["depends_on"]["blocking"] is True
    assert [r["number"] for r in rem["required_by"]] == [main["number"]]
    # Hauptauftrag darf erst starten, wenn der Rückbau bestätigt ist
    for act in ("submit", "approve"):
        assert client.post(f"/api/workorders/{wo['id']}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200
    blocked = client.post(f"/api/workorders/{wo['id']}/transition/start", headers=admin, json={"override_reason": "Test (allein)"})
    assert blocked.status_code == 409 and rem["number"] in blocked.json()["detail"]
    run_order(client, admin, rem["id"])
    assert client.get("/api/cables", headers=admin).json() == []                                           # alter Patch ist jetzt weg
    assert client.post(f"/api/workorders/{wo['id']}/transition/start", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200


def test_slot_busy_asks_and_replaces_directly(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    old = client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="alt", model_id=mid, rack_position=3,
                      uplink={"port_name": "Port1", "target_port_id": rack["pp_port"]})).json()
    new = body(rack, hostname="neu", model_id=mid, rack_position=3)
    q = client.post("/api/wizards/device", headers=admin, json=new)
    d = q.json()["detail"]
    assert q.status_code == 409 and d["code"] == "slot_busy" and d["conflicts"][0]["hostname"] == "alt" and "sofort" in d["message"]
    ok = client.post("/api/wizards/device", headers=admin, json={**new, "replace_devices": True})
    assert ok.status_code == 200, ok.text
    gone = client.get(f"/api/devices/{old['device_id']}", headers=admin).json()
    assert gone["status"] == "retired" and gone["rack_position"] is None                                   # ausgebaut, bleibt als Historie
    assert all(p["cable"] is None for p in gone["ports"]) and client.get("/api/cables", headers=admin).json() == []
    assert client.get(f"/api/devices/{ok.json()['device_id']}", headers=admin).json()["rack_position"] == 3


def test_slot_busy_workorder_creates_device_removal_order(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    old = client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="alt", model_id=mid, rack_position=3)).json()["device_id"]
    new = body(rack, hostname="neu", model_id=mid, rack_position=3, mode="workorder")
    assert client.post("/api/wizards/device", headers=admin, json=new).status_code == 409
    ok = client.post("/api/wizards/device", headers=admin, json={**new, "replace_devices": True})
    assert ok.status_code == 200, ok.text
    wo = ok.json()["workorder"]
    rem = client.get(f"/api/workorders/{wo['removal_order']['id']}", headers=admin).json()
    assert [(i["action"], i["device"]["hostname"]) for i in rem["items"]] == [("remove_device", "alt")]
    # alt steht noch im Rack, ist aber als „Rückbau geplant“ gekennzeichnet; das neue Gerät ist ebenfalls schon verplant
    assert client.get(f"/api/devices/{old}", headers=admin).json()["rack_position"] == 3
    slots = {d["hostname"]: d["pending_removal"] for d in client.get(f"/api/wizards/rack-slots/{rack['rack']}", headers=admin).json()["devices"]}
    assert slots["alt"] is True and slots["neu"] is False
    # Ausführung: erst Rückbau, dann Einbau
    run_order(client, admin, rem["id"])
    assert client.get(f"/api/devices/{old}", headers=admin).json()["status"] == "retired"
    run_order(client, admin, wo["id"])
    nd = client.get(f"/api/devices/{ok.json()['device_id']}", headers=admin).json()
    assert nd["status"] == "active" and nd["rack_position"] == 3


def test_removal_order_is_reused_for_multiple_conflicts(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="alt1", model_id=mid, rack_position=1))
    client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="alt2", model_id=mid, rack_position=2,
                uplink={"port_name": "Port1", "target_port_id": rack["pp_port"]}))
    new = body(rack, hostname="gross", model_id=mid, rack_position=1, height_u=2, mode="workorder",
               uplink={"port_name": "Port1", "target_port_id": rack["pp_port"]})
    ok = client.post("/api/wizards/device", headers=admin, json={**new, "replace_devices": True, "remove_old": True})
    assert ok.status_code == 200, ok.text
    rem = client.get(f"/api/workorders/{ok.json()['workorder']['removal_order']['id']}", headers=admin).json()
    assert sorted(i["action"] for i in rem["items"]) == ["disconnect", "remove_device", "remove_device"]   # ein Rückbau-Auftrag für alles


def test_placeholders_get_auto_name_and_occupy_rack_space(client, admin, rack):
    models = {m["model"]: m["id"] for m in client.get("/api/device-models?type=cable_mgmt,blank_panel,shelf", headers=admin).json()}
    assert {"Kabelführung 1 HE", "Blindblende 2 HE", "Fachboden 1 HE"} <= set(models)
    a = client.post("/api/wizards/device", headers=admin, json={"type": "cable_mgmt", "model_id": models["Kabelführung 1 HE"],
                                                               "location_id": rack["rack"], "rack_position": 2})
    assert a.status_code == 200, a.text
    dev = client.get(f"/api/devices/{a.json()['device_id']}", headers=admin).json()
    assert dev["hostname"] == "KF-R1-HE2" and dev["type"] == "cable_mgmt" and dev["ports"] == []
    b = client.post("/api/wizards/device", headers=admin, json={"type": "blank_panel", "model_id": models["Blindblende 2 HE"],
                                                               "location_id": rack["rack"], "rack_position": 2})
    assert b.status_code == 409 and b.json()["detail"]["code"] == "slot_busy"                       # Platzhalter blockiert die HE wie jedes Gerät
    assert client.post("/api/wizards/device", headers=admin, json={"type": "switch", "location_id": rack["rack"], "rack_position": 5}).status_code == 400   # Hostname fehlt


def test_workitem_api_busy_port_question(client, admin, rack):
    """Auch beim manuellen Planen einer Verbindung im Patchauftrag gilt die Rückfrage."""
    a = client.post("/api/devices", headers=admin, json={"hostname": "a1"}).json()
    pa = [client.post(f"/api/devices/{a['id']}/ports", headers=admin, json={"name": f"p{i}"}).json()["id"] for i in (1, 2)]
    client.put(f"/api/ports/{pa[0]}/cable", headers=admin, json={"port_b_id": rack["pp_port"], "cable_type": "Cat6", "cable_label": "ALT"})
    wo = client.post("/api/workorders", headers=admin, json={"title": "Umbau", "location_id": rack["rack"]}).json()
    item = {"action": "connect", "port_a_id": pa[1], "port_b_id": rack["pp_port"], "cable_type": "Cat6", "cable_label": "NEU"}
    q = client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json=item)
    assert q.status_code == 409 and q.json()["detail"]["code"] == "port_busy"
    assert q.json()["detail"]["conflicts"][0]["cable_label"] == "ALT"
    assert client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["items"] == []                # nichts angelegt
    ok = client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={**item, "remove_old": True})
    assert ok.status_code == 201, ok.text
    dep = client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["depends_on"]
    assert dep and dep["blocking"]
    # zweite Verbindung auf demselben Port: Rückbau ist schon geplant -> keine erneute Rückfrage, derselbe Rückbau-Auftrag
    again = client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={**item, "cable_label": "NEU2"})
    assert again.status_code == 201
    rem = client.get(f"/api/workorders/{dep['id']}", headers=admin).json()
    assert len(rem["items"]) == 1
    # Einbau/Rückbau von Geräten als Position: Gerät Pflicht
    assert client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "remove_device"}).status_code == 400
    assert client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "remove_device", "device_id": a["id"]}).status_code == 201
