"""Telefonie: Gerätetypen/Port-Medien, SIP-Trunks (Verzeichnis, Prüfungen, Rechte) und Aufträge (in Betrieb nehmen / ändern / kündigen)."""
import pytest

from conftest import login


@pytest.fixture()
def world(client, admin):
    out = {}
    for code in ("A", "B"):
        s = client.post("/api/sites", headers=admin, json={"code": code, "name": f"Standort {code}"}).json()
        loc = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": f"R-{code}", "rack_units": 20}).json()
        dev = lambda name, typ: client.post("/api/devices", headers=admin, json={"hostname": name, "type": typ, "location_id": loc["id"]}).json()["id"]  # noqa: E731
        out[code] = {"site": s["id"], "loc": loc["id"], "sbc": dev(f"sbc-{code.lower()}", "sbc"), "pbx": dev(f"hipath-{code.lower()}", "pbx"),
                     "sw": dev(f"sw-{code.lower()}", "switch")}
    wan = client.post("/api/wan", headers=admin, json={"name": "Internet A", "site_a_id": out["A"]["site"], "remote_label": "Internet"})
    assert wan.status_code == 201, wan.text
    out["wan"] = wan.json()["id"]
    return out


def mk(client, admin, w, **kw):
    body = {"name": "Telekom CompanyFlex", "site_id": w["A"]["site"], "provider": "Telekom", "trunk_ident": "T-4711", "channels": 30,
            "numbers": "+49 6181 1234-0…99\n+49 6181 5555", "sbc_device_id": w["A"]["sbc"], "pbx_device_id": w["A"]["pbx"], "wan_link_id": w["wan"], **kw}
    r = client.post("/api/sip-trunks", headers=admin, json=body)
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


def test_telephony_device_types_and_media(client, admin, world):
    for medium in ("UP0E", "S0", "S2M", "a/b", "TAE", "LSA"):
        r = client.post(f"/api/devices/{world['A']['pbx']}/ports", headers=admin, json={"name": f"P-{medium}", "medium": medium})
        assert r.status_code == 201, r.text
    for typ in ("voice_gateway", "dect_base", "phone"):
        assert client.post("/api/devices", headers=admin, json={"hostname": f"x-{typ}", "type": typ, "location_id": world["A"]["loc"]}).status_code == 201


def test_crud_list_and_csv(client, admin, world):
    t = mk(client, admin, world)
    assert t["status"] == "planned" and t["mode"] == "registration" and t["site"].startswith("A")
    assert t["sbc"]["hostname"] == "sbc-a" and t["pbx"]["hostname"] == "hipath-a" and t["wan"]["name"] == "Internet A"
    mk(client, admin, world, name="Fallback B", site_id=world["B"]["site"], sbc_device_id=world["B"]["sbc"], pbx_device_id=None, wan_link_id=None,
       mode="static", trunk_ident="", numbers="+49 69 100")
    assert len(client.get("/api/sip-trunks", headers=admin).json()) == 2
    assert [x["name"] for x in client.get("/api/sip-trunks?q=5555", headers=admin).json()] == ["Telekom CompanyFlex"]       # Suche in Rufnummern
    assert [x["name"] for x in client.get(f"/api/sip-trunks?device_id={world['B']['sbc']}", headers=admin).json()] == ["Fallback B"]
    assert [x["name"] for x in client.get(f"/api/sip-trunks?wan_link_id={world['wan']}", headers=admin).json()] == ["Telekom CompanyFlex"]
    csv = client.get("/api/sip-trunks/export.csv", headers=admin).text
    assert csv.count("\n") == 3 and "+49 6181 1234-0…99 | +49 6181 5555" in csv
    assert [x["name"] for x in client.get(f"/api/wan/{world['wan']}", headers=admin).json()["sip_trunks"]] == ["Telekom CompanyFlex"]
    assert client.get("/api/search?q=T-4711", headers=admin).json()["trunks"][0]["name"] == "Telekom CompanyFlex"
    r = client.put(f"/api/sip-trunks/{t['id']}", headers=admin, json={**t, "channels": 60, "status": "active"})
    assert r.status_code == 200 and r.json()["channels"] == 60 and r.json()["activated_at"]
    assert client.delete(f"/api/sip-trunks/{t['id']}", headers=admin).status_code == 409                                 # läuft: nur per Auftrag kündigen


def test_validation(client, admin, world):
    base = {"name": "x", "site_id": world["A"]["site"]}
    post = lambda **kw: client.post("/api/sip-trunks", headers=admin, json={**base, **kw})  # noqa: E731
    assert post(mode="isdn").status_code == 422
    assert post(sbc_device_id=world["A"]["sw"]).status_code == 422                       # Switch ist kein SBC
    assert post(sbc_device_id=world["B"]["sbc"]).status_code == 422                      # SBC an anderem Standort
    assert post(pbx_device_id=world["A"]["sbc"]).status_code == 422                      # TK-Anlage muss Typ pbx sein
    assert post(wan_link_id=world["wan"], site_id=world["B"]["site"]).status_code == 422  # Leitung gehört nicht zu B
    assert post(contract_start="2026-05-01", contract_end="2026-01-01").status_code == 422
    assert post(channels=-1).status_code == 422
    assert post(status="active").status_code == 201


def test_orders_activate_change_terminate(client, admin, world):
    t = mk(client, admin, world)
    w = client.post("/api/workorders", headers=admin, json={"title": "Trunk", "location_id": world["A"]["loc"]}).json()
    r = client.post(f"/api/workorders/{w['id']}/items", headers=admin, json={"action": "trunk_activate", "sip_trunk_id": t["id"]})
    assert r.status_code == 201, r.text
    it = r.json()
    assert it["action_label"] == "SIP-Trunk in Betrieb nehmen" and it["trunk"]["name"] == "Telekom CompanyFlex" and it["trunk"]["sbc"] == "sbc-a"
    pl = client.get(f"/api/patchlists?ids={w['id']}", headers=admin).text
    assert "SIP-Trunk Telekom CompanyFlex (T-4711)" in pl and "sbc-a / hipath-a" in pl
    assert client.get(f"/api/workorders/{w['id']}/pdf", headers=admin).status_code == 200
    assert client.get(f"/api/sip-trunks/{t['id']}", headers=admin).json()["status"] == "planned"       # erst beim Bestätigen
    run(client, admin, w["id"])
    got = client.get(f"/api/sip-trunks/{t['id']}", headers=admin).json()
    assert got["status"] == "active" and got["orders"][0]["action"] == "trunk_activate"

    w2 = client.post("/api/workorders", headers=admin, json={"title": "Trunk ändern"}).json()
    assert client.post(f"/api/workorders/{w2['id']}/items", headers=admin,
                       json={"action": "trunk_change", "sip_trunk_id": t["id"], "trunk_patch": {"channels": 60, "numbers": " +49 6181 9999 "}}).status_code == 201
    run(client, admin, w2["id"])
    got = client.get(f"/api/sip-trunks/{t['id']}", headers=admin).json()
    assert got["channels"] == 60 and got["numbers"] == "+49 6181 9999"

    w3 = client.post("/api/workorders", headers=admin, json={"title": "Trunk kündigen"}).json()
    assert client.post(f"/api/workorders/{w3['id']}/items", headers=admin, json={"action": "trunk_terminate", "sip_trunk_id": t["id"]}).status_code == 201
    run(client, admin, w3["id"])
    assert client.get(f"/api/sip-trunks/{t['id']}", headers=admin).json()["status"] == "terminated"
    assert client.delete(f"/api/sip-trunks/{t['id']}", headers=admin).status_code == 200


def test_item_validation(client, admin, world):
    t = mk(client, admin, world)
    w = client.post("/api/workorders", headers=admin, json={"title": "x"}).json()
    add = lambda **b: client.post(f"/api/workorders/{w['id']}/items", headers=admin, json=b)  # noqa: E731
    assert add(action="trunk_activate").status_code == 400                                          # ohne Trunk
    assert add(action="trunk_change", sip_trunk_id=t["id"]).status_code == 422                       # keine Änderung
    assert add(action="trunk_change", sip_trunk_id=t["id"], trunk_patch={"site_id": 1}).status_code == 422
    assert add(action="trunk_change", sip_trunk_id=t["id"], trunk_patch={"sbc_device_id": world["A"]["sw"]}).status_code == 422
    assert add(action="trunk_change", sip_trunk_id=t["id"], trunk_patch={"name": "  "}).status_code == 422


def test_scopes(client, admin, world):
    a = mk(client, admin, world)
    b = mk(client, admin, world, name="nur B", site_id=world["B"]["site"], sbc_device_id=None, pbx_device_id=None, wan_link_id=None)
    client.post("/api/users", headers=admin, json={"username": "pa", "password": "Passwort-123", "roles": [], "areas": ["telephony"],
                                                   "scopes": [{"role": "planer", "site_id": world["A"]["site"]}]})
    h = login(client, "pa", "Passwort-123")
    assert [x["name"] for x in client.get("/api/sip-trunks", headers=h).json()] == ["Telekom CompanyFlex"]
    assert client.get(f"/api/sip-trunks/{b['id']}", headers=h).status_code == 404
    assert client.post("/api/sip-trunks", headers=h, json={"name": "neu", "site_id": world["A"]["site"]}).status_code == 403
    w = client.post("/api/workorders", headers=h, json={"title": "Trunk", "location_id": world["A"]["loc"]}).json()
    assert client.post(f"/api/workorders/{w['id']}/items", headers=h, json={"action": "trunk_activate", "sip_trunk_id": a["id"]}).status_code == 201
    assert client.post(f"/api/workorders/{w['id']}/items", headers=h, json={"action": "trunk_activate", "sip_trunk_id": b["id"]}).status_code == 403


def test_areas_restrict_wan_and_telephony(client, admin, world):
    """WAN und Telefonie sieht nur, wer ausdrücklich freigeschaltet ist (globale Admins immer)."""
    t = mk(client, admin, world)
    r = client.post("/api/users", headers=admin, json={"username": "pl", "password": "Passwort-123", "roles": ["planer"]})
    assert r.status_code == 201 and r.json()["areas"] == []
    uid = r.json()["id"]
    h = login(client, "pl", "Passwort-123")
    for url in ("/api/wan", f"/api/wan/{world['wan']}", "/api/wan/export.csv", "/api/sip-trunks", f"/api/sip-trunks/{t['id']}", "/api/sip-trunks/meta"):
        assert client.get(url, headers=h).status_code == 403, url
    s = client.get("/api/search?q=Telekom", headers=h).json()
    assert s["trunks"] == [] and s["wan"] == []
    w = client.post("/api/workorders", headers=h, json={"title": "x", "location_id": world["A"]["loc"]}).json()
    assert client.post(f"/api/workorders/{w['id']}/items", headers=h, json={"action": "trunk_activate", "sip_trunk_id": t["id"]}).status_code == 403
    assert client.post(f"/api/workorders/{w['id']}/items", headers=h, json={"action": "wan_activate", "wan_link_id": world["wan"]}).status_code == 403

    # nur WAN freigeben: WAN ja, Telefonie weiterhin nein; Trunks erscheinen nicht an der Leitung
    r = client.put(f"/api/users/{uid}", headers=admin, json={"areas": ["wan"]})
    assert r.status_code == 200 and r.json()["areas"] == ["wan"]
    assert client.get("/api/auth/me".replace("/api", ""), headers=h).json()["areas"] == ["wan"]          # gilt sofort, ohne neue Anmeldung
    assert client.get(f"/api/wan/{world['wan']}", headers=h).json()["sip_trunks"] == []
    assert client.get("/api/sip-trunks", headers=h).status_code == 403
    client.put(f"/api/users/{uid}", headers=admin, json={"areas": ["wan", "telephony"]})
    assert [x["name"] for x in client.get("/api/sip-trunks", headers=h).json()] == ["Telekom CompanyFlex"]
    assert client.put(f"/api/users/{uid}", headers=admin, json={"areas": ["fax"]}).status_code == 400


def test_areas_only_global_admin_grants_and_tokens(client, admin, world):
    mk(client, admin, world)
    client.post("/api/users", headers=admin, json={"username": "ba", "password": "Passwort-123", "roles": [],
                                                   "scopes": [{"role": "admin", "site_id": world["A"]["site"]}]})
    h = login(client, "ba", "Passwort-123")                                                       # Bereichs-Admin
    assert client.post("/api/users", headers=h, json={"username": "x1", "password": "Passwort-123", "roles": [], "areas": ["wan"],
                                                      "scopes": [{"role": "viewer", "site_id": world["A"]["site"]}]}).status_code == 403
    assert client.get("/api/sip-trunks", headers=h).status_code == 403                             # Bereichs-Admin braucht auch die Freigabe
    plain = client.post("/api/tokens", headers=admin, json={"name": "ohne"}).json()
    tel = client.post("/api/tokens", headers=admin, json={"name": "tel", "areas": ["telephony"]}).json()
    assert tel["areas"] == ["telephony"]
    assert client.get("/api/sip-trunks", headers={"Authorization": f"Bearer {plain['token']}"}).status_code == 403
    assert client.get("/api/sip-trunks", headers={"Authorization": f"Bearer {tel['token']}"}).status_code == 200
    assert client.get("/api/wan", headers={"Authorization": f"Bearer {tel['token']}"}).status_code == 403
