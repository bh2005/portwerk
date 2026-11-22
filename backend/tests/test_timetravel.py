"""Zeitreise: Stand zu einem Zeitpunkt, Vergleich zweier Zeitpunkte (neu/entfernt/umgesteckt/zwischenzeitlich), Pfad zu einem Zeitpunkt."""
from datetime import datetime

import pytest

from conftest import login


def ts(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


@pytest.fixture()
def lab(client, admin):
    from app import db
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()
    rack = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]
    far = client.post("/api/locations", headers=admin, json={"site_id": s2["id"], "kind": "rack", "name": "X", "rack_units": 20}).json()["id"]

    def dev(name, ports, loc=rack):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": "switch", "location_id": loc}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n}).json()["id"] for n in ports}}
    sw = dev("sw-1", ["Gi1", "Gi2", "Gi3", "Gi4"])
    pcs = {i: dev(f"pc-{i}", ["eth0"]) for i in range(1, 6)}
    fx = dev("sw-fremd", ["Gi1", "Gi2"], far)

    def cab(a, b, label):
        assert client.put(f"/api/ports/{a}/cable", headers=admin, json={"port_b_id": b, "cable_label": label}).status_code == 200

    def when(label, start, end=None):
        db.execute("UPDATE cable_history SET valid_from = ?, valid_to = CASE WHEN valid_to IS NULL THEN NULL ELSE ? END WHERE cable_label = ?",
                   (ts(start), ts(end) if end else None, label))
    cab(sw["Gi4"], pcs[5]["eth0"], "K-5"); when("K-5", "2026-01-01T08:00")
    cab(sw["Gi1"], pcs[1]["eth0"], "K-1")
    cab(sw["Gi1"], pcs[2]["eth0"], "K-2")                       # umgesteckt: K-1 endet
    when("K-1", "2026-01-01T08:00", "2026-03-10T12:00"); when("K-2", "2026-03-10T12:00")
    cab(sw["Gi2"], pcs[3]["eth0"], "K-3"); when("K-3", "2026-02-15T09:00")
    cab(sw["Gi3"], pcs[4]["eth0"], "K-4")
    client.put(f"/api/ports/{sw['Gi3']}/cable", headers=admin, json={"port_b_id": None})
    when("K-4", "2026-02-01T10:00", "2026-02-05T10:00")         # nur zwischenzeitlich
    cab(fx["Gi1"], fx["Gi2"], "F-1"); when("F-1", "2026-01-01T08:00")
    return {"site": s["id"], "site2": s2["id"], "sw": sw, "pcs": pcs, "fx": fx}


def labels(rows):
    return sorted(r["cable_label"] for r in rows)


def test_snapshot_at_points_in_time(client, admin, lab):
    snap = lambda at, **kw: client.get("/api/cable-history/snapshot", headers=admin, params={"at": at, **kw}).json()["connections"]  # noqa: E731
    assert labels(snap("2025-12-31")) == []
    assert labels(snap("2026-01-15")) == ["F-1", "K-1", "K-5"]
    assert labels(snap("2026-02-03")) == ["F-1", "K-1", "K-4", "K-5"]
    assert labels(snap("2026-03-01", site_id=lab["site"])) == ["K-1", "K-3", "K-5"]
    assert labels(snap("2026-03-10T12:00", device_id=lab["sw"]["id"])) == ["K-2", "K-3", "K-5"]          # Ende exklusiv
    assert client.get("/api/cable-history/snapshot", headers=admin, params={"at": "gestern"}).status_code == 400


def test_diff_classifies_changes(client, admin, lab):
    r = client.get("/api/cable-history/diff", headers=admin, params={"from": "2026-01-15", "to": "2026-04-01", "site_id": lab["site"]}).json()
    assert r["summary"] == {"added": 1, "removed": 0, "moved": 1, "changed": 0, "temporary": 1, "before": 2, "after": 3}
    m = r["moved"][0]
    assert (m["port"]["hostname"], m["port"]["port"]) == ("sw-1", "Gi1")
    assert m["from"]["hostname"] == "pc-1" and m["to"]["hostname"] == "pc-2"
    assert m["before"]["ended_by"] == "admin" and m["after"]["cable_label"] == "K-2"
    assert labels(r["added"]) == ["K-3"] and labels(r["temporary"]) == ["K-4"]
    rev = client.get("/api/cable-history/diff", headers=admin, params={"from": "2026-04-01", "to": "2026-01-15", "site_id": lab["site"]}).json()
    assert rev["summary"]["moved"] == 1 and rev["from"] < rev["to"]                                     # Reihenfolge egal
    only = client.get("/api/cable-history/diff", headers=admin, params={"from": "2026-01-15", "device_id": lab["pcs"][3]["id"]}).json()
    assert labels(only["added"]) == ["K-3"] and not only["moved"] and not only["temporary"]          # „to“ leer = jetzt


def test_removed_connection(client, admin, lab):
    from app import db
    client.put(f"/api/ports/{lab['sw']['Gi4']}/cable", headers=admin, json={"port_b_id": None})
    db.execute("UPDATE cable_history SET valid_to = ? WHERE cable_label = 'K-5'", (ts("2026-05-01T10:00"),))
    r = client.get("/api/cable-history/diff", headers=admin, params={"from": "2026-04-01", "to": "2026-06-01", "site_id": lab["site"]}).json()
    assert labels(r["removed"]) == ["K-5"] and r["removed"][0]["end_reason"] == "manual"


def test_path_at_point_in_time(client, admin, lab):
    pc1 = lab["pcs"][1]["eth0"]
    then = client.get(f"/api/ports/{pc1}/path", headers=admin, params={"at": "2026-02-01"}).json()
    assert then["complete"] and set(then["summary"].split(" → ")) == {"sw-1:Gi1", "pc-1:eth0"} and then["links"][0]["label"] == "K-1"
    assert then["lldp"] == [] and then["at"]
    now = client.get(f"/api/ports/{pc1}/path", headers=admin).json()
    assert len(now["nodes"]) == 1 and now["at"] is None


def test_scoped_user(client, admin, lab):
    client.post("/api/users", headers=admin, json={"username": "w1", "password": "Passwort-123", "roles": [],
                                                   "scopes": [{"site_id": lab["site"], "role": "viewer"}]})
    h = login(client, "w1", "Passwort-123")
    snap = client.get("/api/cable-history/snapshot", headers=h, params={"at": "2026-01-15"}).json()["connections"]
    assert labels(snap) == ["K-1", "K-5"]
    assert client.get("/api/cable-history/snapshot", headers=h, params={"at": "2026-01-15", "device_id": lab["fx"]["id"]}).status_code == 404
    assert client.get("/api/cable-history/diff", headers=h, params={"from": "2026-01-01", "site_id": lab["site2"]}).status_code == 404


def test_timezone_offset_is_respected(client, admin, lab):
    from app.routers.history import _parse_at
    assert _parse_at("2026-03-10T12:00:00+01:00") == _parse_at("2026-03-10T11:00:00Z") == datetime.fromisoformat("2026-03-10T11:00:00+00:00").timestamp()
    k1_end = ts("2026-03-10T12:00")                                  # in Server-Ortszeit gesetzt
    just_before = datetime.fromtimestamp(k1_end - 60).astimezone().isoformat(timespec="seconds")       # mit Offset
    snap = client.get("/api/cable-history/snapshot", headers=admin, params={"at": just_before, "device_id": lab["sw"]["id"]}).json()
    assert "K-1" in labels(snap["connections"])
