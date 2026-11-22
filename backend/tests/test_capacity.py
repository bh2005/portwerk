"""Kapazitätsplanung: Port-Zustände je Kategorie, HE-Belegung je Rack, Aufsummieren über Orte, Engpässe, Rechte."""
import pytest

from conftest import login


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()
    loc = lambda sid, kind, name, parent=None, units=None: client.post("/api/locations", headers=admin, json={  # noqa: E731
        "site_id": sid, "kind": kind, "name": name, "parent_id": parent, "rack_units": units}).json()["id"]
    b = loc(s["id"], "building", "Halle 1")
    rack = loc(s["id"], "rack", "R1", b, 10)
    room = loc(s["id"], "room", "Büro", b)
    far = loc(s2["id"], "rack", "X", None, 10)

    def dev(name, dtype, where, ports, pos=None, height=1, peers=(), **kw):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": dtype, "location_id": where,
                                                             "rack_position": pos, "height_u": height, **kw})
        assert d.status_code == 201, d.text
        d = d.json()
        ids = {n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n, "medium": "RJ45"}).json()["id"] for n in ports}
        for f, bk in peers:
            client.put(f"/api/ports/{ids[f]}/peer", headers=admin, json={"peer_port_id": ids[bk]})
        return {"id": d["id"], **ids}
    sw = dev("sw-1", "switch", rack, [f"Gi{i}" for i in range(1, 11)], pos=1, height=2)               # HE 1-2
    pp = dev("pf-1", "patchpanel", rack, ["P1", "P1-back", "P2", "P2-back"], pos=3, peers=[("P1", "P1-back"), ("P2", "P2-back")])
    dose = dev("do-1", "outlet", room, ["1"])
    srv = dev("srv-1", "server", rack, ["eth0"], pos=5, height=2, mount_side="front")                # HE 5-6 nur vorne
    fx = dev("sw-fremd", "switch", far, ["Gi1"], pos=1)
    return {"site": s["id"], "site2": s2["id"], "rack": rack, "room": room, "b": b, "sw": sw, "pp": pp, "dose": dose, "srv": srv, "fx": fx}


def cap(client, h, **params):
    r = client.get("/api/capacity", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def find(nodes, name):
    for n in nodes:
        if n["name"] == name:
            return n
        hit = find(n["children"], name)
        if hit:
            return hit


def test_port_states_and_rollup(client, admin, lab):
    sw, pp = lab["sw"], lab["pp"]
    client.put(f"/api/ports/{sw['Gi1']}/cable", headers=admin, json={"port_b_id": pp["P1"]})                  # belegt
    wo = client.post("/api/workorders", headers=admin, json={"title": "Plan"}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "connect", "port_a_id": sw["Gi2"], "port_b_id": pp["P2"]})
    client.post("/api/reservations", headers=admin, json={"port_ids": [sw["Gi3"], sw["Gi4"]], "purpose": "Kamera"})
    r = cap(client, admin)
    site = next(s for s in r["sites"] if s["code"] == "W1")
    rack = find(site["children"], "R1")
    assert rack["stats"]["switch"] == {"used": 1, "planned": 1, "reserved": 2, "free": 6, "total": 10}
    assert rack["stats"]["patchpanel"] == {"used": 1, "planned": 1, "reserved": 0, "free": 0, "total": 2}     # nur Vorderseite
    hall = find(site["children"], "Halle 1")
    assert hall["stats"]["outlet"]["total"] == 1 and hall["stats"]["switch"]["total"] == 10                    # aufsummiert
    assert site["stats"]["switch"]["total"] == 10 and "srv" not in str(rack["stats"])                          # Server zählt nicht


def test_rack_units(client, admin, lab):
    u = find(cap(client, admin)["sites"][0]["children"], "R1")["units"]
    # belegt: 1-2 (Switch, beide Seiten), 3 (Patchfeld, beide), 5-6 (Server nur vorne) -> 5 HE belegt, ganz frei: 4, 7-10
    assert u["total"] == 10 and u["used"] == 5 and u["free"] == 5 and u["largest_block"] == 4 and u["half_free"] == 2
    wo = client.post("/api/workorders", headers=admin, json={"title": "Rückbau"}).json()
    client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json={"action": "remove_device", "device_id": lab["srv"]["id"]})
    client.post("/api/devices", headers=admin, json={"hostname": "neu", "type": "switch", "location_id": lab["rack"], "rack_position": 9,
                                                     "height_u": 2, "status": "planned"})
    u = find(cap(client, admin)["sites"][0]["children"], "R1")["units"]
    assert u["freed"] == 2 and u["planned"] == 2 and u["largest_block"] == 2


def test_alerts_by_threshold(client, admin, lab):
    for i in range(1, 10):                                                     # 9 von 10 Switchports belegt -> 10 % frei
        client.put(f"/api/ports/{lab['sw'][f'Gi{i}']}/cable", headers=admin, json={"port_b_id": None})
    pc = client.post("/api/devices", headers=admin, json={"hostname": "pcs", "type": "endpoint", "location_id": lab["room"]}).json()
    for i in range(1, 10):
        p = client.post(f"/api/devices/{pc['id']}/ports", headers=admin, json={"name": f"e{i}"}).json()["id"]
        client.put(f"/api/ports/{lab['sw'][f'Gi{i}']}/cable", headers=admin, json={"port_b_id": p})
    alerts = cap(client, admin, warn=10)["alerts"]
    assert not any(a.get("category") == "switch" for a in alerts)                # genau 10 % ist kein Engpass (< 10)
    alerts = cap(client, admin, warn=20)["alerts"]
    sw = [a for a in alerts if a.get("category") == "switch"]
    assert len(sw) == 1 and sw[0]["free_pct"] == 10.0 and sw[0]["path"] == "W1 / Halle 1 / R1" and sw[0]["location_id"] == lab["rack"]
    units = [a for a in cap(client, admin, warn=60)["alerts"] if a["kind"] == "units"]
    assert {a["path"] for a in units} == {"W1 / Halle 1 / R1"} and units[0]["largest_block"] == 4    # X: 90 % frei
    s = client.get("/api/capacity/summary", headers=admin, params={"warn": 60}).json()
    assert s["alerts"] >= 2 and 2 <= len(s["worst"]) <= 3 and s["worst"][0]["free_pct"] <= s["worst"][-1]["free_pct"]


def test_scoped_user_sees_own_site_only(client, admin, lab):
    client.post("/api/users", headers=admin, json={"username": "w1", "password": "Passwort-123", "roles": [],
                                                   "scopes": [{"site_id": lab["site"], "role": "viewer"}]})
    h = login(client, "w1", "Passwort-123")
    r = cap(client, h)
    assert [s["code"] for s in r["sites"]] == ["W1"] and "sw-fremd" not in str(r) and "W2" not in str(r)
    assert [s["code"] for s in cap(client, admin, site_id=lab["site2"])["sites"]] == ["W2"]
    assert client.get("/api/capacity", headers=admin, params={"warn": 150}).status_code == 422
