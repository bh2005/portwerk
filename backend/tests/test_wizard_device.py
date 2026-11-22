import pytest

from conftest import login


def model_id(client, admin, name):
    return [m for m in client.get("/api/device-models?q=Generisch", headers=admin).json() if m["model"] == name][0]["id"]


@pytest.fixture()
def rack(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    r = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 10}).json()
    room = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "room", "name": "Raum"}).json()
    pp = client.post("/api/devices", headers=admin, json={"hostname": "pp-1", "type": "patchpanel", "location_id": r["id"], "rack_position": 10}).json()
    port = client.post(f"/api/devices/{pp['id']}/ports", headers=admin, json={"name": "P1", "medium": "RJ45"}).json()
    port2 = client.post(f"/api/devices/{pp['id']}/ports", headers=admin, json={"name": "P2", "medium": "RJ45"}).json()
    return {"site": s["id"], "rack": r["id"], "room": room["id"], "pp_port": port["id"], "pp_port2": port2["id"]}


def body(rack, **kw):
    return {"hostname": "sw-neu", "type": "switch", "location_id": rack["rack"], "rack_position": 1, **kw}


def test_rack_slots(client, admin, rack):
    r = client.get(f"/api/wizards/rack-slots/{rack['rack']}?height_u=2", headers=admin).json()
    assert r["rack_units"] == 10 and r["devices"][0]["hostname"] == "pp-1"
    assert r["free_starts"] == list(range(1, 9))                       # HE 10 belegt: Start 9 würde HE 9–10 überlappen
    assert client.get(f"/api/wizards/rack-slots/{rack['room']}", headers=admin).status_code == 400
    assert client.get("/api/wizards/rack-slots/999", headers=admin).status_code == 404


def test_direct_with_model_and_uplink(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port + 2 SFP")
    uplink = {"port_name": "SFP1", "target_port_id": rack["pp_port"], "cable_type": "LWL-SM-OS2", "cable_label": "UL-1", "fiber_count": 2}
    r = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, uplink=uplink, mgmt_ip="192.0.2.10"))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ports_created"] == 10 and d["cable_id"] and d["workorder"] is None
    dev = client.get(f"/api/devices/{d['device_id']}", headers=admin).json()
    assert dev["status"] == "active" and dev["vendor"] == "Generisch" and dev["model_id"] == mid and dev["rack_position"] == 1
    sfp = [p for p in dev["ports"] if p["name"] == "SFP1"][0]
    assert sfp["cable"]["device_hostname"] == "pp-1" and sfp["cable"]["cable_type"] == "LWL-SM-OS2" and sfp["cable"]["fiber_count"] == 2


def test_dry_run_writes_nothing(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    r = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, dry_run=True))
    assert r.status_code == 200 and r.json()["dry_run"] and r.json()["ports"]["count"] == 8
    assert r.json()["device"]["location_path"] == "W1 / R1"
    assert client.get("/api/devices?q=sw-neu", headers=admin).json()["total"] == 0


def test_custom_ports_without_model(client, admin, rack):
    r = client.post("/api/wizards/device", headers=admin, json=body(rack, vendor="X", model="Y", height_u=2,
                    ports=[{"prefix": "e", "count": 4, "medium": "RJ45"}, {"prefix": "x", "count": 1, "medium": "SFP+"}]))
    assert r.status_code == 200, r.text
    dev = client.get(f"/api/devices/{r.json()['device_id']}", headers=admin).json()
    assert dev["height_u"] == 2 and len(dev["ports"]) == 5 and dev["model_id"] is None


def test_validation_errors_leave_nothing_behind(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    post = lambda **kw: client.post("/api/wizards/device", headers=admin, json=body(rack, **{"model_id": mid, **kw}))  # noqa: E731
    assert post(hostname="pp-1").status_code == 409                                         # Hostname doppelt
    assert post(rack_position=10).status_code == 409                                        # HE belegt
    assert post(rack_position=11).status_code == 400                                        # passt nicht ins Rack
    assert post(type="kaffee").status_code == 400
    assert post(mode="beamen").status_code == 400
    assert post(status="retired").status_code == 400
    assert post(model_id=999).status_code == 400
    assert client.post("/api/wizards/device", headers=admin, json={"hostname": "x", "location_id": 999}).status_code == 400
    assert client.post("/api/wizards/device", headers=admin, json=body(rack, rack_position=None, location_id=rack["room"], hostname="im-raum")).status_code == 200   # ohne Rack/HE möglich
    assert client.post("/api/wizards/device", headers=admin, json=body(rack, location_id=rack["room"], hostname="x2")).status_code == 400   # HE nur im Rack
    up = lambda **kw: post(rack_position=5, uplink={"port_name": "Port1", "target_port_id": rack["pp_port"], **kw})  # noqa: E731
    assert up(port_name="Port99").status_code == 400                                        # Port gibt es nicht
    assert up(target_port_id=999).status_code == 404
    assert up(cable_type="Zauber").status_code == 400
    assert client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, hostname="a", uplink={"port_name": "Port1", "target_port_id": rack["pp_port"]})).status_code == 200
    assert up().status_code == 409                                                          # Zielport inzwischen belegt
    names = [d["hostname"] for d in client.get("/api/devices", headers=admin).json()["items"]]
    assert names.count("sw-neu") == 0 and "x2" not in names


def test_target_port_busy_is_rejected(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    ok = client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="sw-1", model_id=mid, rack_position=1,
                     uplink={"port_name": "Port1", "target_port_id": rack["pp_port"]}))
    assert ok.status_code == 200
    busy = client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="sw-2", model_id=mid, rack_position=2,
                       uplink={"port_name": "Port1", "target_port_id": rack["pp_port"]}))
    d = busy.json()["detail"]
    assert busy.status_code == 409 and d["code"] == "port_busy" and "sw-1:Port1" in d["message"] and d["conflicts"][0]["port"] == "pp-1:P1"
    assert client.get("/api/devices?q=sw-2", headers=admin).json()["total"] == 0


def test_workorder_mode_planned_device_and_confirmation(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    r = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, mode="workorder", status="active",
                    workorder_title="Einbau Test", uplink={"port_name": "Port8", "target_port_id": rack["pp_port"], "cable_type": "Cat6A", "cable_label": "K1"}))
    assert r.status_code == 200, r.text
    d = r.json()
    wid = d["workorder"]["id"]
    assert d["workorder"]["new"] and d["cable_id"] is None
    dev = client.get(f"/api/devices/{d['device_id']}", headers=admin).json()
    assert dev["status"] == "planned"                                                       # trotz status=active: per Auftrag nur „geplant“
    assert all(p["cable"] is None for p in dev["ports"])                                    # noch nicht verkabelt
    wo = client.get(f"/api/workorders/{wid}", headers=admin).json()
    assert wo["status"] == "draft" and wo["title"] == "Einbau Test" and wo["location"]["id"] == rack["rack"]
    assert [i["action"] for i in wo["items"]] == ["install_device", "connect"]
    assert wo["items"][1]["cable_label"] == "K1" and wo["items"][1]["port_a"]["device_hostname"] == "sw-neu" and wo["items"][0]["device"]["hostname"] == "sw-neu"
    for act in ("submit", "approve", "start"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200
    for it in wo["items"]:
        assert client.post(f"/api/workorders/{wid}/items/{it['id']}/execute", headers=admin, json={"item_status": "done"}).status_code == 200
    for act in ("finish", "confirm"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200
    dev = client.get(f"/api/devices/{d['device_id']}", headers=admin).json()
    assert dev["status"] == "active"                                                        # eingebaut
    assert [p for p in dev["ports"] if p["name"] == "Port8"][0]["cable"]["cable_label"] == "K1"


def test_workorder_mode_existing_order_and_requirements(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    no_cable = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, mode="workorder", hostname="nur-einbau", rack_position=6))
    assert no_cable.status_code == 200                                                        # Einbau ohne Kabel: nur die Einbau-Position
    assert [i["action"] for i in client.get(f"/api/workorders/{no_cable.json()['workorder']['id']}", headers=admin).json()["items"]] == ["install_device"]
    wo = client.post("/api/workorders", headers=admin, json={"title": "Sammelauftrag", "location_id": rack["rack"]}).json()
    up = {"port_name": "Port1", "target_port_id": rack["pp_port"]}
    r = client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, mode="workorder", workorder_id=wo["id"], uplink=up))
    assert r.status_code == 200 and r.json()["workorder"] == {"id": wo["id"], "number": wo["number"], "title": "Sammelauftrag", "new": False, "removal_order": None}
    r2 = client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="sw-2", rack_position=2, model_id=mid, mode="workorder",
                     workorder_id=wo["id"], uplink={"port_name": "Port1", "target_port_id": rack["pp_port2"]}))
    assert r2.status_code == 200
    assert len(client.get(f"/api/workorders/{wo['id']}", headers=admin).json()["items"]) == 4          # je Gerät: Einbau + Kabel
    client.post(f"/api/workorders/{wo['id']}/transition/submit", headers=admin, json={"override_reason": "Test (allein)"})
    late = client.post("/api/wizards/device", headers=admin, json=body(rack, hostname="sw-3", rack_position=3, model_id=mid, mode="workorder",
                       workorder_id=wo["id"], uplink={"port_name": "Port1", "target_port_id": rack["pp_port2"]}))
    assert late.status_code == 409                                                          # nur Entwürfe
    assert client.get("/api/devices?q=sw-3", headers=admin).json()["total"] == 0


def test_failure_rolls_back_device_and_new_workorder(client, admin, rack, monkeypatch):
    from app.routers import workorders
    mid = model_id(client, admin, "Switch 8 Port")

    def boom():
        raise RuntimeError("Nummernkreis kaputt")
    monkeypatch.setattr(workorders, "_next_number", boom)
    with pytest.raises(RuntimeError):
        client.post("/api/wizards/device", headers=admin, json=body(rack, model_id=mid, mode="workorder",
                    uplink={"port_name": "Port1", "target_port_id": rack["pp_port"]}))
    assert client.get("/api/devices?q=sw-neu", headers=admin).json()["total"] == 0
    assert client.get("/api/workorders", headers=admin).json() == []


# ── Berechtigungen je Standort ────────────────────────────────────────────────

def user(client, admin, name, scopes):
    client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": [],
                                                   "scopes": [{"role": r, "site_id": s} for r, s in scopes]})
    return login(client, name, "Passwort-123")


def test_scoped_permissions(client, admin, rack):
    mid = model_id(client, admin, "Switch 8 Port")
    other = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Anderes Werk"}).json()
    rack2 = client.post("/api/locations", headers=admin, json={"site_id": other["id"], "kind": "rack", "name": "R2", "rack_units": 42}).json()
    up = {"port_name": "Port1", "target_port_id": rack["pp_port"]}
    adm = user(client, admin, "adm", [("admin", rack["site"])])
    pl = user(client, admin, "pl", [("planer", rack["site"])])
    vw = user(client, admin, "vw", [("viewer", rack["site"])])
    # Bereichs-Admin: direkt im eigenen Standort, nicht im fremden
    assert client.post("/api/wizards/device", headers=adm, json=body(rack, model_id=mid, hostname="d1")).status_code == 200
    assert client.post("/api/wizards/device", headers=adm, json={"hostname": "d2", "location_id": rack2["id"], "model_id": mid}).status_code == 403
    # Planer: nicht direkt, aber per Patchauftrag (Gerät „geplant“)
    assert client.post("/api/wizards/device", headers=pl, json=body(rack, hostname="d3", rack_position=2, model_id=mid)).status_code == 403
    ok = client.post("/api/wizards/device", headers=pl, json=body(rack, hostname="d4", rack_position=2, model_id=mid, mode="workorder", uplink=up))
    assert ok.status_code == 200, ok.text
    assert client.get(f"/api/devices/{ok.json()['device_id']}", headers=pl).json()["status"] == "planned"
    # fremder Standort / fehlende Rolle
    assert client.post("/api/wizards/device", headers=pl, json={"hostname": "d5", "location_id": rack2["id"], "model_id": mid, "mode": "workorder", "uplink": up}).status_code == 403
    assert client.post("/api/wizards/device", headers=vw, json=body(rack, hostname="d6", rack_position=3, model_id=mid, mode="workorder", uplink=up)).status_code == 403
    # Zielport außerhalb des Bereichs
    pp2 = client.post("/api/devices", headers=admin, json={"hostname": "pp-x", "location_id": rack2["id"]}).json()
    px = client.post(f"/api/devices/{pp2['id']}/ports", headers=admin, json={"name": "P1"}).json()
    assert client.post("/api/wizards/device", headers=adm, json=body(rack, hostname="d7", rack_position=4, model_id=mid,
                       uplink={"port_name": "Port1", "target_port_id": px["id"]})).status_code == 403
    # Rack-Belegung nur im eigenen Bereich
    assert client.get(f"/api/wizards/rack-slots/{rack['rack']}", headers=vw).status_code == 200
    assert client.get(f"/api/wizards/rack-slots/{rack2['id']}", headers=vw).status_code == 404
