"""Kabeletiketten mit QR-Code und Auflösung gescannter Codes (auch für geplante und umgesteckte Kabel)."""
import pytest

from conftest import login


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()
    loc = lambda sid: client.post("/api/locations", headers=admin, json={"site_id": sid, "kind": "rack", "name": "R", "rack_units": 20}).json()["id"]  # noqa: E731
    r1, r2 = loc(s["id"]), loc(s2["id"])

    def dev(name, rack, ports):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": "switch", "location_id": rack}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n, "medium": "RJ45"}).json()["id"]
                                  for n in ports}}
    return {"site1": s["id"], "site2": s2["id"], "sw": dev("sw-1", r1, ["Gi1", "Gi2", "Gi3"]), "pc": dev("pc-1", r1, ["eth0"]),
            "pc2": dev("pc-2", r1, ["eth0"]), "far": dev("sw-far", r2, ["Gi1", "Gi2"])}


def connect(client, h, a, b, label=""):
    assert client.put(f"/api/ports/{a}/cable", headers=h, json={"port_b_id": b, "cable_label": label}).status_code == 200


def labels(client, h, **params):
    r = client.get("/api/labels", headers=h, params={"base": "https://pw.example", **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_device_labels_with_qr(client, admin, lab):
    connect(client, admin, lab["pc"]["eth0"], lab["sw"]["Gi1"], "K/0001 A")
    connect(client, admin, lab["sw"]["Gi2"], lab["pc2"]["eth0"])                   # ohne Nummer
    out = labels(client, admin, device_id=lab["sw"]["id"])
    assert [e["cable_label"] for e in out] == ["", "K/0001 A"]
    no_nr, k1 = out
    assert k1["a"] == {"hostname": "sw-1", "port": "Gi1", "device_id": lab["sw"]["id"]}          # eigenes Gerät zuerst
    assert k1["url"] == "https://pw.example/q/k/K%2F0001%20A"
    assert k1["qr_svg"].startswith("<svg") and "viewBox" in k1["qr_svg"]
    assert no_nr["url"] == f"https://pw.example/q/c/{no_nr['cable_id']}"
    ids = [e["cable_id"] for e in out]
    assert [e["cable_id"] for e in labels(client, admin, cable_ids=ids)] == ids              # sortiert nach Nummer
    assert client.get("/api/labels", headers=admin, params={"base": "javascript:alert(1)", "cable_ids": ids}).status_code == 400
    assert client.get("/api/labels", headers=admin, params={"cable_ids": ids}).json()[0]["url"].startswith("http://testserver/q/")


def test_workorder_labels_before_confirmation_and_resolve(client, admin, lab):
    wo = client.post("/api/workorders", headers=admin, json={"title": "Neu"}).json()
    for a, b, lbl in ((lab["sw"]["Gi3"], lab["pc"]["eth0"], "K-10"), (lab["sw"]["Gi2"], lab["pc2"]["eth0"], "")):
        assert client.post(f"/api/workorders/{wo['id']}/items", headers=admin,
                           json={"action": "connect", "port_a_id": a, "port_b_id": b, "cable_label": lbl}).status_code == 201
    out = labels(client, admin, workorder_id=wo["id"])
    assert [e["source"] for e in out] == ["workitem", "workitem"]
    assert out[0]["url"].endswith("/q/k/K-10") and out[0]["qr_svg"]
    assert out[1]["url"] is None and out[1]["qr_svg"] is None                       # ohne Nummer kein Ziel
    r = client.get("/api/labels/resolve", headers=admin, params={"label": "K-10"}).json()
    assert r["cables"] == [] and r["planned"][0]["workorder"]["number"] == wo["number"]
    assert r["planned"][0]["a"]["hostname"] == "sw-1" and r["planned"][0]["workorder"]["status_label"] == "Entwurf"


def test_resolve_follows_replug_and_shows_history(client, admin, lab):
    connect(client, admin, lab["sw"]["Gi1"], lab["pc"]["eth0"], "K-7")
    connect(client, admin, lab["sw"]["Gi1"], lab["pc2"]["eth0"], "K-7")              # umgesteckt, gleiche Nummer
    r = client.get("/api/labels/resolve", headers=admin, params={"label": "K-7"}).json()
    assert len(r["cables"]) == 1 and r["cables"][0]["b"]["hostname"] == "pc-2"
    assert [h["b"]["hostname"] for h in r["history"]] == ["pc-1"]
    old_id = r["history"][0]["cable_id"]
    by_id = client.get("/api/labels/resolve", headers=admin, params={"cable_id": old_id}).json()
    assert by_id["cables"] == [] and by_id["history"][0]["cable_label"] == "K-7"     # alter Code (per ID) zeigt, dass es entfernt ist
    assert client.get("/api/labels/resolve", headers=admin).status_code == 400


def test_scoped_user_sees_only_own_site(client, admin, lab):
    connect(client, admin, lab["far"]["Gi1"], lab["far"]["Gi2"], "FREMD")
    connect(client, admin, lab["sw"]["Gi1"], lab["pc"]["eth0"], "EIGEN")
    r = client.post("/api/users", headers=admin, json={"username": "w1", "password": "Passwort-123", "roles": [],
                                                       "scopes": [{"site_id": lab["site1"], "role": "viewer"}]})
    assert r.status_code == 201, r.text
    h = login(client, "w1", "Passwort-123")
    ids = [c["id"] for c in client.get("/api/cables", headers=admin).json()]
    assert [e["cable_label"] for e in labels(client, h, cable_ids=ids)] == ["EIGEN"]
    assert client.get("/api/labels", headers=h, params={"device_id": lab["far"]["id"]}).status_code == 404
    assert client.get("/api/labels/resolve", headers=h, params={"label": "FREMD"}).json()["cables"] == []
