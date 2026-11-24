"""Geräte aus OpenPlan übernehmen: Zuordnung von Standort, Rack/HE, Raum, Typ und Katalogmodell; Anlegen als „geplant“ mit Ports,
Verknüpfen vorhandener Geräte, Rückverweis in OpenPlan, erneuter Abruf, Rechte."""
import pytest

from conftest import login, make_user
from test_openplan import enable, op  # noqa: F401  (Fixture)


@pytest.fixture()
def world(client, admin, op):  # noqa: F811
    enable(client, admin)
    s = client.post("/api/sites", headers=admin, json={"code": "LOC024", "name": "Zentrale Kassel"}).json()["id"]
    s2 = client.post("/api/sites", headers=admin, json={"code": "HAT", "name": "Werk Hattorf"}).json()["id"]
    loc = lambda site, kind, name, parent=None, units=None: client.post("/api/locations", headers=admin, json={  # noqa: E731
        "site_id": site, "kind": kind, "name": name, "parent_id": parent, "rack_units": units}).json()["id"]
    ga = loc(s, "building", "Geb. A")
    r112 = loc(s, "room", "R1.12", ga)
    r3 = loc(s, "rack", "R3", r112, 42)
    gb = loc(s, "building", "Geb. B")
    r203 = loc(s, "room", "R2.03", gb)
    r1a, r1b = loc(s, "rack", "R1", r112, 42), loc(s, "rack", "R1", r203, 42)               # gleichnamige Racks
    sr1 = loc(s2, "room", "SR1")
    m = client.post("/api/device-models", headers=admin, json={"vendor": "Extreme", "model": "5520-24T", "type": "switch", "height_u": 1,
                                                                  "ports": [{"prefix": "1:", "start": 1, "count": 24, "medium": "RJ45"}]})
    assert m.status_code == 201, m.text
    client.post("/api/devices", headers=admin, json={"hostname": "sw-kas-alt-01", "type": "switch", "location_id": r3, "rack_position": 14})
    client.post("/api/devices", headers=admin, json={"hostname": "sw-vorhanden", "type": "switch", "location_id": r3})
    base = {"standort": "Zentrale Kassel", "loc": "LOC024", "typ": "Switch"}
    t = {
        "z01": op.add_device(1, hostname="sw-kas-z-01", modell="Extreme 5520-24T", alt_host="sw-kas-alt-01", raum="Geb. A / R1.12", rack="R3 / HE 12",
                             ip="10.20.1.11", seriennummer="SN1", **base),
        "z02": op.add_device(1, hostname="sw-kas-z-02", modell="Extreme 5520-24T", raum="Geb. A / R1.12", rack="R3 / HE 14", **base),   # HE belegt
        "z03": op.add_device(1, hostname="sw-kas-z-03", modell="Unbekannt X", raum="Geb. B / R2.03", rack="R1 / HE 20", **base),     # R1 über Raum
        "ap": op.add_device(1, hostname="ap-hat-01", standort="Werk Hattorf", typ="Access Point", raum="Halle 3 / SR1", rack="R9 / HE 1"),
        "fremd": op.add_device(1, hostname="fw-xyz", standort="Nirgendwo", typ="Firewall"),
        "da": op.add_device(1, hostname="SW-VORHANDEN", **base),
        "offen": op.add_device(1, hostname="sw-ohne-ort", **base),
    }
    return {"s": s, "s2": s2, "r3": r3, "r1b": r1b, "sr1": sr1, "r112": r112, "t": t, "model": m.json()["id"]}


def test_preview_matches(client, admin, op, world):  # noqa: F811
    r = client.get("/api/openplan/projects/1/devices", headers=admin)
    assert r.status_code == 200, r.text
    d = r.json()
    by = {i["hostname"]: i for i in d["items"]}
    assert len(d["items"]) == 7 and "Planung" not in by                                           # nur Geräte-Vorgänge
    z1 = by["sw-kas-z-01"]
    assert (z1["state"], z1["site_id"], z1["location_id"], z1["rack_position"], z1["type"], z1["model_id"]) == ("new", world["s"], world["r3"], 12, "switch", world["model"])
    assert "ersetzt sw-kas-alt-01" in z1["hint"]
    z3 = by["sw-kas-z-03"]
    assert z3["location_id"] == world["r1b"] and z3["model_id"] is None and z3["type"] == "switch"      # gleichnamiges Rack über den Raum
    ap = by["ap-hat-01"]
    assert ap["location_id"] == world["sr1"] and ap["rack_position"] is None and ap["type"] == "ap" and "Raum gewählt" in ap["hint"]
    assert by["fw-xyz"]["state"] == "no_site" and by["SW-VORHANDEN"]["state"] == "exists"
    assert by["sw-ohne-ort"]["location_id"] is None and "bitte wählen" in by["sw-ohne-ort"]["hint"]
    assert d["counts"] == {"new": 5, "exists": 1, "no_site": 1, "linked": 0}
    assert any(p["path"].endswith("R3") for p in d["places"][str(world["s"])])


def test_apply_creates_links_and_refs(client, admin, op, world):  # noqa: F811
    t = world["t"]
    picks = [{"task_id": t["z01"]}, {"task_id": t["z02"]}, {"task_id": t["da"]}, {"task_id": t["fremd"]}, {"task_id": t["offen"]},
             {"task_id": t["ap"], "location_id": world["r3"]}]                                       # Ort an fremdem Standort
    r = client.post("/api/openplan/projects/1/devices", headers=admin, json={"items": picks})
    assert r.status_code == 200, r.text
    res = r.json()
    assert sorted(c["hostname"] for c in res["created"]) == ["sw-kas-z-01", "sw-kas-z-02"]
    assert [x["hostname"] for x in res["linked"]] == ["sw-vorhanden"]
    assert sorted(x["hostname"] for x in res["skipped"]) == ["ap-hat-01", "fw-xyz", "sw-ohne-ort"]
    assert any("sw-kas-z-02" in w and "HE 14" in w for w in res["warnings"])
    z1 = next(c for c in res["created"] if c["hostname"] == "sw-kas-z-01")
    dev = client.get(f"/api/devices/{z1['id']}", headers=admin).json()
    assert (dev["status"], dev["source"], dev["rack_position"], dev["mgmt_ip"], dev["serial"], dev["model"]) == ("planned", "openplan", 12, "10.20.1.11", "SN1", "5520-24T")
    assert len(client.get(f"/api/devices/{z1['id']}/ports", headers=admin).json()) == 24 and "ersetzt sw-kas-alt-01" in dev["note"]
    assert op.refs[(t["z01"], "portwerk")] == ("sw-kas-z-01", f"https://opp.example.test/devices/{z1['id']}")
    assert op.refs[(t["da"], "portwerk")][0] == "sw-vorhanden"
    # erneuter Abruf: übernommen bzw. verknüpft
    by = {i["hostname"]: i for i in client.get("/api/openplan/projects/1/devices", headers=admin).json()["items"]}
    assert by["sw-kas-z-01"]["state"] == "linked" and by["SW-VORHANDEN"]["state"] == "linked" and by["sw-kas-z-02"]["device"]["status"] == "planned"
    r = client.post("/api/openplan/projects/1/devices", headers=admin, json={"items": [{"task_id": t["z01"]}, {"task_id": t["offen"], "location_id": world["r112"]}]})
    assert [c["hostname"] for c in r.json()["created"]] == ["sw-ohne-ort"] and r.json()["skipped"][0]["hostname"] == "sw-kas-z-01"
    log = client.get("/api/audit", headers=admin).json()
    assert any(e["action"] == "device.from_openplan" for e in (log["items"] if isinstance(log, dict) else log))


def test_link_back_failure_and_rights(client, admin, op, world, monkeypatch):  # noqa: F811
    from app.openplan import OpenPlanError
    real = op.__call__

    def flaky(method, path, body=None, cfg=None):
        if method == "PUT" and "/refs/" in path:
            raise OpenPlanError(403, "OpenPlan antwortet 403")
        return real(method, path, body, cfg)
    import app.openplan as o
    monkeypatch.setattr(o, "request", flaky)
    r = client.post("/api/openplan/projects/1/devices", headers=admin, json={"items": [{"task_id": world["t"]["z03"]}]})
    assert r.status_code == 200, r.text
    r = r.json()
    assert [c["hostname"] for c in r["created"]] == ["sw-kas-z-03"] and "Rückverweis" in r["warnings"][0]
    make_user(client, admin, "leser", roles=("viewer",))
    h = login(client, "leser", "Passwort-123")
    assert client.get("/api/openplan/projects/1/devices", headers=h).status_code == 403
    client.post("/api/users", headers=admin, json={"username": "p2", "password": "Passwort-123", "roles": [], "scopes": [{"site_id": world["s2"], "role": "planer"}]})
    h2 = login(client, "p2", "Passwort-123")
    items = client.get("/api/openplan/projects/1/devices", headers=h2).json()["items"]
    assert {i["hostname"]: i["state"] for i in items}["sw-kas-z-01"] == "no_site"                   # Standort nicht sichtbar
    r = client.post("/api/openplan/projects/1/devices", headers=h2, json={"items": [{"task_id": world["t"]["ap"]}]})
    assert r.status_code == 200 and r.json()["created"][0]["hostname"] == "ap-hat-01", r.text
