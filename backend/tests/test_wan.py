"""WAN-Verbindungen: Leitungsverzeichnis, Rechte je Standort, Aufträge (in Betrieb nehmen / ändern / kündigen)."""
import pytest

from conftest import login


@pytest.fixture()
def world(client, admin):
    out = {}
    for code in ("A", "B", "C"):
        s = client.post("/api/sites", headers=admin, json={"code": code, "name": f"Standort {code}"}).json()
        loc = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": f"R-{code}", "rack_units": 20}).json()
        d = client.post("/api/devices", headers=admin, json={"hostname": f"rtr-{code.lower()}", "type": "router", "location_id": loc["id"]}).json()
        ports = [client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": f"W{i}"}).json()["id"] for i in (1, 2)]
        out[code] = {"site": s["id"], "loc": loc["id"], "ports": ports}
    return out


def mk(client, admin, w, **kw):
    body = {"name": "MPLS A-B", "technology": "mpls", "site_a_id": w["A"]["site"], "site_b_id": w["B"]["site"], "provider": "Telco", "circuit_id": "C-1",
            "bandwidth_down": 100, "bandwidth_up": 100, **kw}
    r = client.post("/api/wan", headers=admin, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def order(client, admin, title="WAN"):
    r = client.post("/api/workorders", headers=admin, json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def run(client, admin, wid):
    for act in ("submit", "approve", "start"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200
    for it in client.get(f"/api/workorders/{wid}", headers=admin).json()["items"]:
        assert client.post(f"/api/workorders/{wid}/items/{it['id']}/execute", headers=admin, json={"item_status": "done"}).status_code == 200
    for act in ("finish", "confirm"):
        r = client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"})
        assert r.status_code == 200, r.text


def test_crud_and_list_filters(client, admin, world):
    a = mk(client, admin, world)
    assert a["status"] == "planned" and a["site_a"].startswith("A") and a["site_b"].startswith("B") and a["technology_label"] == "MPLS"
    mk(client, admin, world, name="Internet C", technology="fiber", site_a_id=world["C"]["site"], site_b_id=None, remote_label="Internet", circuit_id="C-2")
    assert len(client.get("/api/wan", headers=admin).json()) == 2
    assert [x["name"] for x in client.get("/api/wan?q=internet", headers=admin).json()] == ["Internet C"]
    assert [x["name"] for x in client.get(f"/api/wan?site_id={world['B']['site']}", headers=admin).json()] == ["MPLS A-B"]
    assert client.get("/api/wan/export.csv", headers=admin).text.count("\n") == 3
    body = {**a, "name": "MPLS A-B neu"}
    r = client.put(f"/api/wan/{a['id']}", headers=admin, json=body)
    assert r.status_code == 200 and r.json()["name"] == "MPLS A-B neu"
    assert client.delete(f"/api/wan/{a['id']}", headers=admin).status_code == 200
    assert client.get(f"/api/wan/{a['id']}", headers=admin).status_code == 404


def test_validation(client, admin, world):
    base = {"name": "x", "site_a_id": world["A"]["site"]}
    assert client.post("/api/wan", headers=admin, json={**base, "technology": "warp"}).status_code == 422
    assert client.post("/api/wan", headers=admin, json={**base, "status": "kaputt"}).status_code == 422
    assert client.post("/api/wan", headers=admin, json={**base, "contract_end": "31.12.2027"}).status_code == 422
    assert client.post("/api/wan", headers=admin, json={**base, "contract_start": "2027-02-01", "contract_end": "2027-01-01"}).status_code == 422
    # Port muss zum Standort gehören
    assert client.post("/api/wan", headers=admin, json={**base, "port_a_id": world["B"]["ports"][0]}).status_code == 422


def test_port_not_used_twice(client, admin, world):
    p = world["A"]["ports"][0]
    mk(client, admin, world, port_a_id=p)
    r = client.post("/api/wan", headers=admin, json={"name": "zweite", "site_a_id": world["A"]["site"], "port_a_id": p})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "port_busy"
    # gekündigte Verbindungen geben den Port frei
    first = client.get("/api/wan", headers=admin).json()[0]
    client.put(f"/api/wan/{first['id']}", headers=admin, json={**first, "status": "terminated"})
    assert client.post("/api/wan", headers=admin, json={"name": "zweite", "site_a_id": world["A"]["site"], "port_a_id": p}).status_code == 201


def test_expiring_contracts(client, admin, world):
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=30)).isoformat()
    late = (date.today() + timedelta(days=400)).isoformat()
    mk(client, admin, world, name="bald", contract_end=soon)
    mk(client, admin, world, name="spaeter", contract_end=late)
    got = client.get("/api/wan?expiring_days=90", headers=admin).json()
    assert [x["name"] for x in got] == ["bald"] and got[0]["days_left"] == 30


def test_orders_activate_change_terminate(client, admin, world):
    a = mk(client, admin, world)
    w = order(client, admin, "WAN in Betrieb")
    r = client.post(f"/api/workorders/{w['id']}/items", headers=admin, json={"action": "wan_activate", "wan_link_id": a["id"]})
    assert r.status_code == 201 or r.status_code == 200, r.text
    assert r.json()["wan"]["name"] == "MPLS A-B" and r.json()["action_label"] == "WAN in Betrieb nehmen"
    assert client.get(f"/api/wan/{a['id']}", headers=admin).json()["status"] == "planned"            # erst nach Bestätigung
    run(client, admin, w["id"])
    got = client.get(f"/api/wan/{a['id']}", headers=admin).json()
    assert got["status"] == "active" and got["activated_at"] and got["orders"][0]["number"] == w["number"]
    # bereits in Betrieb → nicht nochmal
    w2 = order(client, admin, "nochmal")
    assert client.post(f"/api/workorders/{w2['id']}/items", headers=admin, json={"action": "wan_activate", "wan_link_id": a["id"]}).status_code == 409
    # Änderung der Bandbreite
    r = client.post(f"/api/workorders/{w2['id']}/items", headers=admin, json={"action": "wan_change", "wan_link_id": a["id"],
                                                                              "wan_patch": {"bandwidth_down": 500, "bandwidth_up": 500}})
    assert r.status_code in (200, 201) and r.json()["wan_patch"]["bandwidth_down"] == 500
    assert client.get(f"/api/wan/{a['id']}", headers=admin).json()["bandwidth_down"] == 100
    run(client, admin, w2["id"])
    assert client.get(f"/api/wan/{a['id']}", headers=admin).json()["bandwidth_down"] == 500
    # Kündigung
    w3 = order(client, admin, "kündigen")
    assert client.post(f"/api/workorders/{w3['id']}/items", headers=admin, json={"action": "wan_terminate", "wan_link_id": a["id"]}).status_code in (200, 201)
    run(client, admin, w3["id"])
    done = client.get(f"/api/wan/{a['id']}", headers=admin).json()
    assert done["status"] == "terminated" and done["terminated_at"]
    assert client.post(f"/api/workorders/{order(client, admin)['id']}/items", headers=admin,
                       json={"action": "wan_change", "wan_link_id": a["id"], "wan_patch": {"note": "x"}}).status_code == 409


def test_item_validation(client, admin, world):
    a = mk(client, admin, world)
    w = order(client, admin)
    add = lambda **kw: client.post(f"/api/workorders/{w['id']}/items", headers=admin, json=kw)  # noqa: E731
    assert add(action="wan_activate").status_code == 400                                            # keine Verbindung
    assert add(action="wan_activate", wan_link_id=9999).status_code == 400
    assert add(action="wan_change", wan_link_id=a["id"], wan_patch={}).status_code == 422
    assert add(action="wan_change", wan_link_id=a["id"], wan_patch={"status": "active"}).status_code == 422      # Status nur über Aktionen
    assert add(action="wan_change", wan_link_id=a["id"], wan_patch={"contract_end": "morgen"}).status_code == 422


def test_scopes(client, admin, world):
    a = mk(client, admin, world)                                                                   # A ↔ B
    c = mk(client, admin, world, name="nur C", site_a_id=world["C"]["site"], site_b_id=None)
    client.post("/api/users", headers=admin, json={"username": "pa", "password": "Passwort-123", "roles": [],
                                                   "scopes": [{"role": "planer", "site_id": world["A"]["site"]}]})
    h = login(client, "pa", "Passwort-123")
    assert [x["name"] for x in client.get("/api/wan", headers=h).json()] == ["MPLS A-B"]            # sieht auch Verbindungen mit A als Gegenstelle
    assert client.get(f"/api/wan/{c['id']}", headers=h).status_code == 404
    assert client.post("/api/wan", headers=h, json={"name": "neu", "site_a_id": world["A"]["site"]}).status_code == 403   # Planer ≠ Bereichs-Admin
    w = client.post("/api/workorders", headers=h, json={"title": "WAN", "location_id": world["A"]["loc"]}).json()
    ok = client.post(f"/api/workorders/{w['id']}/items", headers=h, json={"action": "wan_activate", "wan_link_id": a["id"]})
    assert ok.status_code in (200, 201), ok.text
    assert client.post(f"/api/workorders/{w['id']}/items", headers=h, json={"action": "wan_activate", "wan_link_id": c["id"]}).status_code == 403


def test_patchlist_shows_wan(client, admin, world):
    a = mk(client, admin, world)
    w = order(client, admin)
    client.post(f"/api/workorders/{w['id']}/items", headers=admin, json={"action": "wan_activate", "wan_link_id": a["id"]})
    r = client.get(f"/api/patchlists?ids={w['id']}", headers=admin)
    assert r.status_code == 200, r.text
    assert "WAN MPLS A-B" in r.text
