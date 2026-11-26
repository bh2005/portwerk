"""Rufnummernplan: Blöcke (Prüfungen, Überschneidung), Vergabe/Reservierung/Freigabe, nächste freie, Suche, CSV, Rechte."""
import pytest

from conftest import login


@pytest.fixture()
def world(client, admin):
    out = {}
    for code in ("A", "B"):
        s = client.post("/api/sites", headers=admin, json={"code": code, "name": f"Standort {code}"}).json()
        loc = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "room", "name": f"Büro {code}"}).json()
        out[code] = {"site": s["id"], "loc": loc["id"]}
    out["phone"] = client.post("/api/devices", headers=admin, json={"hostname": "tel-mueller", "type": "phone", "location_id": out["A"]["loc"]}).json()["id"]
    out["trunk"] = client.post("/api/sip-trunks", headers=admin, json={"name": "CompanyFlex", "site_id": out["A"]["site"]}).json()["id"]
    return out


def block(client, admin, w, **kw):
    r = client.post("/api/numbers/blocks", headers=admin, json={"site_id": w["A"]["site"], "sip_trunk_id": w["trunk"], "name": "Zentrale",
                                                                 "prefix": "+49 6181 1234", "range_from": 0, "range_to": 99, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_block_crud_and_checks(client, admin, world):
    b = block(client, admin, world)
    assert b["first"] == "+49 6181 1234-0" and b["last"] == "+49 6181 1234-99" and b["counts"] == {"total": 100, "assigned": 0, "reserved": 0, "free": 100, "expired": 0}
    assert b["trunk"]["name"] == "CompanyFlex"
    post = lambda **kw: client.post("/api/numbers/blocks", headers=admin, json={"site_id": world["A"]["site"], "prefix": "+49 6181 1234",  # noqa: E731
                                                                                "range_from": 0, "range_to": 9, **kw})
    assert post(range_from=50, range_to=150).status_code == 409                       # überschneidet sich
    assert post(prefix="+49 6181 12 34", range_from=90, range_to=95).status_code == 409   # gleiche Ziffern, anders geschrieben
    assert post(prefix="+49 6181 9999").status_code == 201                           # anderer Präfix: ok
    assert post(prefix="abc").status_code == 422
    assert post(prefix="+49 1", range_from=9, range_to=1).status_code == 422
    assert post(prefix="+49 2", range_to=20000).status_code == 422                   # zu groß
    assert post(prefix="+49 3", sip_trunk_id=world["trunk"], site_id=world["B"]["site"]).status_code == 422   # Trunk an anderem Standort
    w4 = client.post("/api/numbers/blocks", headers=admin, json={"site_id": world["A"]["site"], "prefix": "+49 4", "range_from": 100, "range_to": 199, "width": 4}).json()
    assert w4["first"] == "+49 4-0100"
    assert client.get(f"/api/sip-trunks/{world['trunk']}", headers=admin).json()["number_blocks"][0]["prefix"] == "+49 6181 1234"


def test_assign_reserve_free(client, admin, world):
    b = block(client, admin, world)
    put = lambda ext, **kw: client.put(f"/api/numbers/blocks/{b['id']}/ext/{ext}", headers=admin, json=kw)  # noqa: E731
    r = put(0, kind="function", holder="Zentrale")
    assert r.status_code == 200 and r.json()["number"] == "+49 6181 1234-0" and r.json()["status_label"] == "vergeben"
    assert put(15, holder="Müller", device_id=world["phone"]).json()["device"]["hostname"] == "tel-mueller"
    assert [a["number"] for a in client.get(f"/api/numbers/by-device/{world['phone']}", headers=admin).json()] == ["+49 6181 1234-15"]
    assert put(16, status="reserved", holder="Neue Kollegin", reserved_until="2020-01-01").json()["expired"] is True
    assert put(17).status_code == 422                                                   # vergeben ohne Inhaber
    assert put(100, holder="x").status_code == 422                                      # außerhalb des Bereichs
    assert put(18, holder="x", kind="warp").status_code == 422
    assert put(18, holder="x", status="reserved", reserved_until="morgen").status_code == 422
    assert client.get(f"/api/numbers/blocks/{b['id']}/next-free", headers=admin).json()["extension"] == 1
    assert client.get(f"/api/numbers/blocks/{b['id']}/next-free?after=14", headers=admin).json()["extension"] == 17
    d = client.get(f"/api/numbers/blocks/{b['id']}", headers=admin).json()
    assert [a["extension"] for a in d["assignments"]] == [0, 15, 16] and d["counts"]["free"] == 97 and d["counts"]["expired"] == 1
    assert put(15, holder="Müller-Lüdenscheidt").json()["holder"] == "Müller-Lüdenscheidt"             # umschreiben
    assert client.put(f"/api/numbers/blocks/{b['id']}", headers=admin, json={**{k: b[k] for k in ("site_id", "prefix", "name")}, "range_from": 0, "range_to": 10}).status_code == 409
    assert client.delete(f"/api/numbers/blocks/{b['id']}", headers=admin).status_code == 409             # noch belegt
    for ext in (0, 15, 16):
        assert client.delete(f"/api/numbers/blocks/{b['id']}/ext/{ext}", headers=admin).status_code == 200
    assert client.delete(f"/api/numbers/blocks/{b['id']}/ext/0", headers=admin).status_code == 404
    assert client.delete(f"/api/numbers/blocks/{b['id']}", headers=admin).status_code == 200


def test_search_and_csv(client, admin, world):
    b = block(client, admin, world)
    client.put(f"/api/numbers/blocks/{b['id']}/ext/15", headers=admin, json={"holder": "Erika Müller"})
    client.put(f"/api/numbers/blocks/{b['id']}/ext/42", headers=admin, json={"holder": "Aufzug Halle 2", "kind": "special"})
    assert [a["holder"] for a in client.get("/api/numbers/search?q=müller", headers=admin).json()] == ["Erika Müller"]
    assert [a["holder"] for a in client.get("/api/numbers/search?q=1234-42", headers=admin).json()] == ["Aufzug Halle 2"]
    assert [a["holder"] for a in client.get("/api/numbers/search?q=06181 1234-15", headers=admin).json()] == ["Erika Müller"]   # national geschrieben
    assert client.get("/api/numbers/search?q=0049 6181 1234 42", headers=admin).json()[0]["holder"] == "Aufzug Halle 2"
    assert client.get("/api/search?q=Aufzug", headers=admin).json()["numbers"][0]["number"] == "+49 6181 1234-42"
    csv = client.get("/api/numbers/export.csv", headers=admin).text
    assert csv.count("\n") == 3 and "Sonderanschluss" in csv
    assert client.get(f"/api/numbers/export.csv?block_id={b['id']}&include_free=true", headers=admin).text.count("\n") == 101


def test_rights(client, admin, world):
    b = block(client, admin, world)
    bb = client.post("/api/numbers/blocks", headers=admin, json={"site_id": world["B"]["site"], "prefix": "+49 69 5000", "range_from": 0, "range_to": 9}).json()
    mk = lambda name, role, areas: client.post("/api/users", headers=admin, json={"username": name, "password": "Passwort-123", "roles": [], "areas": areas,  # noqa: E731
                                                                                 "scopes": [{"role": role, "site_id": world["A"]["site"]}]})
    mk("pl", "planer", ["telephony"]); mk("tech", "techniker", ["telephony"]); mk("pz", "planer", [])
    pl, tech, pz = (login(client, n, "Passwort-123") for n in ("pl", "tech", "pz"))
    assert client.get("/api/numbers/blocks", headers=pz).status_code == 403                         # ohne Freigabe Telefonie
    assert [x["id"] for x in client.get("/api/numbers/blocks", headers=pl).json()] == [b["id"]]       # nur Standort A
    assert client.get(f"/api/numbers/blocks/{bb['id']}", headers=pl).status_code == 404
    assert client.put(f"/api/numbers/blocks/{b['id']}/ext/5", headers=pl, json={"holder": "Planer vergibt"}).status_code == 200
    assert client.get(f"/api/numbers/blocks/{b['id']}", headers=pl).json()["can_edit"] is False
    assert client.put(f"/api/numbers/blocks/{b['id']}/ext/6", headers=tech, json={"holder": "x"}).status_code == 403
    assert client.get(f"/api/numbers/blocks/{b['id']}", headers=tech).json()["can_assign"] is False
    assert client.post("/api/numbers/blocks", headers=pl, json={"site_id": world["A"]["site"], "prefix": "+49 7", "range_from": 0, "range_to": 9}).status_code == 403
    assert client.get("/api/numbers/search?q=Planer", headers=pl).json()[0]["number"] == "+49 6181 1234-5"
