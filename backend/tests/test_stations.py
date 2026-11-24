"""Zwischenstationen einfügen und entfernen (Strecken-Editor)."""
import pytest


@pytest.fixture()
def net(client, admin):
    """sw-a:Gi1 ↔ sw-b:Gi1 direkt; pp1 (F1↔B1) und pp2 (F1↔B1) frei."""
    def dev(host, typ, ports):
        d = client.post("/api/devices", headers=admin, json={"hostname": host, "type": typ}).json()["id"]
        ids = {n: client.post(f"/api/devices/{d}/ports", headers=admin, json={"name": n}).json()["id"] for n in ports}
        return d, ids
    a, pa = dev("sw-a", "switch", ["Gi1"])
    b, pb = dev("sw-b", "switch", ["Gi1"])
    _, p1 = dev("pp1", "patchpanel", ["F1", "B1"])
    _, p2 = dev("pp2", "patchpanel", ["F1", "B1"])
    for p in (p1, p2):
        assert client.put(f"/api/ports/{p['F1']}/peer", headers=admin, json={"peer_port_id": p["B1"]}).status_code == 200
    r = client.put(f"/api/ports/{pa['Gi1']}/cable", headers=admin, json={"port_b_id": pb["Gi1"], "cable_type": "Cat6", "cable_label": "K-1", "length_m": 5, "color": "blau"})
    assert r.status_code == 200, r.text
    cid = r.json()["cable"]["id"]
    return {"a": pa["Gi1"], "b": pb["Gi1"], "p1": p1, "p2": p2, "cid": cid}


def path(client, admin, port):
    r = client.get(f"/api/ports/{port}/path", headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


def hosts(p):
    return [n["device"]["hostname"] for n in p["nodes"]]


def test_path_has_cable_fields(client, admin, net):
    p = path(client, admin, net["a"])
    assert hosts(p) == ["sw-a", "sw-b"] and p["complete"]
    lk = p["links"][0]
    assert lk["cable_id"] == net["cid"] and lk["cable_type"] == "Cat6" and lk["length_m"] == 5 and lk["provisional"] is False and "note" in lk


def test_insert_and_remove_station(client, admin, net):
    r = client.post(f"/api/cables/{net['cid']}/insert-station", headers=admin, json={"port_id": net["p1"]["F1"], "side_port_id": net["a"]})
    assert r.status_code == 201, r.text
    p = path(client, admin, net["a"])
    assert hosts(p) == ["sw-a", "pp1", "sw-b"] and p["complete"]                       # Strecke läuft jetzt über das Patchfeld
    assert [n["ports"][0]["name"] for n in p["nodes"][1:2]] == ["F1"] and p["nodes"][1]["ports"][1]["name"] == "B1"
    first, second = p["links"]
    assert first["label"] == "K-1" and first["length_m"] == 5 and second["label"] == "" and second["cable_type"] == "Cat6" and second["color"] == "blau"
    # zweite Station dazu (hinter dem Patchfeld) – das zweite Kabel wird geteilt
    r2 = client.post(f"/api/cables/{second['cable_id']}/insert-station", headers=admin, json={"port_id": net["p2"]["F1"], "side_port_id": net["p1"]["B1"]})
    assert r2.status_code == 201, r2.text
    assert hosts(path(client, admin, net["a"])) == ["sw-a", "pp1", "pp2", "sw-b"]
    # Station bereits belegt
    assert client.post(f"/api/cables/{first['cable_id']}/insert-station", headers=admin, json={"port_id": net["p1"]["F1"]}).status_code in (400, 409)
    # Historie: altes Kabel beendet, neue stecken
    hist = client.get("/api/cable-history", headers=admin, params={"port_id": net["a"]}).json()
    assert any(not h["active"] for h in hist) and any(h["active"] for h in hist)
    # pp1 wieder entfernen → Direktkabel pp1.B1-Seite zu sw-a? Nein: sw-a ↔ pp2.F1
    rm = client.post("/api/stations/remove", headers=admin, json={"port_id": net["p1"]["B1"]})
    assert rm.status_code == 201, rm.text
    p = path(client, admin, net["a"])
    assert hosts(p) == ["sw-a", "pp2", "sw-b"]
    assert p["links"][0]["provisional"] is True                                           # Direktkabel ist vorläufig
    rm2 = client.post("/api/stations/remove", headers=admin, json={"port_id": net["p2"]["F1"]})
    assert rm2.status_code == 201
    p = path(client, admin, net["a"])
    assert hosts(p) == ["sw-a", "sw-b"] and p["links"][0]["provisional"] is True


def test_station_errors(client, admin, net):
    cid = net["cid"]
    assert client.post(f"/api/cables/{cid}/insert-station", headers=admin, json={"port_id": net["b"]}).status_code == 400           # Switch ist keine Station
    assert client.post(f"/api/cables/{cid}/insert-station", headers=admin, json={"port_id": net["p1"]["F1"], "side_port_id": 999999}).status_code == 400
    assert client.post("/api/cables/999999/insert-station", headers=admin, json={"port_id": net["p1"]["F1"]}).status_code == 404
    assert client.post("/api/stations/remove", headers=admin, json={"port_id": net["p1"]["F1"]}).status_code == 409           # nicht verbunden
    assert client.post("/api/stations/remove", headers=admin, json={"port_id": net["a"]}).status_code == 400                   # kein Patchfeld
