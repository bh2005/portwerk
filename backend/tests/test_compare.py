"""Soll/Ist-Abgleich (LLDP/CDP) und Checkmk-Link."""
import pytest

from conftest import login


def tree(n_ports, lldp=None, cdp=None, with_lldp=True):
    ifs = [{"index": i, "name": f"Gi0/{i}", "port_type": 6, "speed": 1_000_000_000, "admin_status": 1, "oper_status": 1} for i in range(1, n_ports + 1)]
    nodes = {"interfaces": {"Table": {"Rows": ifs}}}
    if with_lldp:
        nodes["lldp_cache"] = {"Nodes": {"neighbors": {"Table": {"Rows": lldp or []}}}}
    if cdp is not None:
        nodes["cdp_cache"] = {"Nodes": {"neighbors": {"Table": {"Rows": cdp}}}}
    return {"Nodes": {"networking": {"Nodes": nodes}}}


def nb(local, name, port, addr=""):
    return {"local_port": local, "neighbor_name": name, "neighbor_port": port, "neighbor_address": addr}


@pytest.fixture()
def lab(client, admin):
    """sw1/sw2 aus dem Checkmk-Import (mit Nachbardaten), pp = Patchfeld mit durchgeschleiften Ports; dokumentierte Kabel dazwischen."""
    s = client.post("/api/sites", headers=admin, json={"code": "S1", "name": "Werk"}).json()["id"]
    imp = client.post("/api/import/checkmk", headers=admin, json={"site_code": "S1", "hosts": [
        {"host": "sw1", "inventory": tree(6, lldp=[nb("Gi0/1", "sw2.example.test", "GigabitEthernet0/1"), nb("Gi0/2", "sw2", "Gi0/2"), nb("Gi0/3", "sw2", "Gi0/4"),
                                                   nb("Gi0/4", "fremd-sw", "Gi1/1"), nb("Gi0/6", "AA:BB:CC:DD:EE:FF", "AA:BB:CC:DD:EE:FF")],
                                          cdp=[nb("Gi0/1", "sw2.example.test", "GigabitEthernet0/1")])},
        {"host": "sw2", "inventory": tree(6, lldp=[nb("Gi0/1", "sw1", "Gi0/1")])},
    ]})
    assert imp.status_code == 200, imp.text
    assert imp.json()["neighbors"]["devices"] == 2
    dev = {d["hostname"]: d for d in client.get("/api/devices?limit=100", headers=admin).json()["items"]}
    port = lambda host, name: [p for p in client.get(f"/api/devices/{dev[host]['id']}/ports", headers=admin).json() if p["name"] == name][0]["id"]  # noqa: E731
    pp = client.post("/api/devices", headers=admin, json={"hostname": "pp1", "type": "patchpanel", "location_id": None}).json()["id"]
    f1 = client.post(f"/api/devices/{pp}/ports", headers=admin, json={"name": "F1"}).json()["id"]
    b1 = client.post(f"/api/devices/{pp}/ports", headers=admin, json={"name": "B1"}).json()["id"]
    assert client.put(f"/api/ports/{f1}/peer", headers=admin, json={"peer_port_id": b1}).status_code == 200
    cab = lambda a, b: client.put(f"/api/ports/{a}/cable", headers=admin, json={"port_b_id": b, "cable_type": "Cat6"}).status_code  # noqa: E731
    assert cab(port("sw1", "Gi0/1"), port("sw2", "Gi0/1")) == 200                 # direkt
    assert cab(port("sw1", "Gi0/2"), f1) == 200 and cab(b1, port("sw2", "Gi0/2")) == 200    # über Patchfeld
    assert cab(port("sw1", "Gi0/3"), port("sw2", "Gi0/3")) == 200                 # dokumentiert Gi0/3, gesehen wird Gi0/4
    assert cab(port("sw1", "Gi0/5"), port("sw2", "Gi0/5")) == 200                 # dokumentiert, aber kein Nachbar gesehen
    return {"site": s}


def by(client, admin, **q):
    r = client.get("/api/compare", headers=admin, params=q)
    assert r.status_code == 200, r.text
    return {(x["device"], x["port"]): x for x in r.json()["rows"]}, r.json()


def test_statuses(client, admin, lab):
    rows, res = by(client, admin)
    assert rows[("sw1", "Gi0/1")]["status"] == "ok"                              # LLDP und CDP, lange Portnamen werden normalisiert
    assert ("sw2", "Gi0/1") not in rows                                           # dieselbe Strecke vom anderen Ende: nur einmal
    p = rows[("sw1", "Gi0/2")]
    assert p["status"] == "ok" and p["soll"]["via"] == ["pp1:F1"] and p["soll"]["label"] == "sw2:Gi0/2"
    assert rows[("sw1", "Gi0/3")]["status"] == "port_mismatch" and rows[("sw1", "Gi0/3")]["soll"]["label"] == "sw2:Gi0/3"
    assert rows[("sw1", "Gi0/4")]["status"] == "undocumented"
    assert rows[("sw1", "Gi0/5")]["status"] == "not_seen"
    assert ("sw1", "Gi0/6") not in rows                                           # reine MAC-Nachbarn zählen nicht
    assert res["summary"]["ok"] == 2 and res["summary"]["port_mismatch"] == 1 and res["devices"] == 2
    assert [r["status"] for r in res["rows"]][0] in ("port_mismatch", "mismatch")  # Abweichungen zuerst


def test_other_device_and_filter(client, admin, lab):
    rows, _ = by(client, admin)
    dev = {d["hostname"]: d for d in client.get("/api/devices?limit=100", headers=admin).json()["items"]}
    # Gi0/1 jetzt auf ein anderes Gerät umdokumentieren: sw1:Gi0/6 ↔ sw2:Gi0/6 und Nachbar-Meldung fremd-sw auf Gi0/6
    client.post("/api/import/checkmk", headers=admin, json={"site_code": "S1", "hosts": [
        {"host": "sw1", "inventory": tree(6, lldp=[nb("Gi0/6", "sw2", "Gi0/1")])}]})
    p6 = [p for p in client.get(f"/api/devices/{dev['sw1']['id']}/ports", headers=admin).json() if p["name"] == "Gi0/6"][0]["id"]
    q6 = [p for p in client.get(f"/api/devices/{dev['sw2']['id']}/ports", headers=admin).json() if p["name"] == "Gi0/6"][0]["id"]
    client.put(f"/api/ports/{p6}/cable", headers=admin, json={"port_b_id": q6, "cable_type": "Cat6"})
    rows, res = by(client, admin)
    assert rows[("sw1", "Gi0/6")]["status"] == "port_mismatch"                    # richtiges Gerät, falscher Port
    only = client.get("/api/compare?status=port_mismatch,mismatch", headers=admin).json()["rows"]
    assert {r["status"] for r in only} <= {"port_mismatch", "mismatch"} and len(only) == 1
    csv = client.get("/api/compare/export.csv?status=port_mismatch", headers=admin).text
    assert "anderer Port" in csv and "sw1" in csv


def test_unknown_when_no_neighbor_data_and_replace(client, admin, lab):
    client.post("/api/import/checkmk", headers=admin, json={"site_code": "S1", "hosts": [{"host": "sw1", "inventory": tree(6, lldp=[])}]})
    rows, _ = by(client, admin)
    assert rows[("sw1", "Gi0/1")]["status"] == "not_seen"                         # Daten ersetzt: nichts mehr gesehen
    # Host ohne Nachbartabellen: Bestand bleibt, es gibt keine neuen Aussagen
    client.post("/api/import/checkmk", headers=admin, json={"site_code": "S1", "hosts": [{"host": "sw1", "inventory": tree(6, with_lldp=False)}]})
    rows, _ = by(client, admin)
    assert rows[("sw1", "Gi0/1")]["status"] == "not_seen"


def test_scopes(client, admin, lab):
    other = client.post("/api/sites", headers=admin, json={"code": "S2", "name": "Anderes"}).json()["id"]
    client.post("/api/users", headers=admin, json={"username": "v2", "password": "Passwort-123", "roles": [], "scopes": [{"role": "viewer", "site_id": other}]})
    h = login(client, "v2", "Passwort-123")
    assert client.get("/api/compare", headers=h).json()["rows"] == []              # fremder Standort: nichts sichtbar
    assert len(client.get(f"/api/compare?site_id={lab['site']}", headers=admin).json()["rows"]) >= 4


def test_checkmk_link_settings(client, admin):
    assert client.get("/api/integrations/checkmk", headers=admin).json() == {"enabled": False, "base_url": "", "link_all": True}
    r = client.put("/api/admin/checkmk", headers=admin, json={"base_url": "https://cmk.example.test/prod/", "link_all": False})
    assert r.status_code == 200 and r.json() == {"enabled": True, "base_url": "https://cmk.example.test/prod", "link_all": False}
    assert client.put("/api/admin/checkmk", headers=admin, json={"base_url": "javascript:alert(1)"}).status_code == 422
    assert client.put("/api/admin/checkmk", headers=admin, json={"base_url": "https://x.test/a?b=1"}).status_code == 422
    client.post("/api/users", headers=admin, json={"username": "v", "password": "Passwort-123", "roles": ["viewer"]})
    h = login(client, "v", "Passwort-123")
    assert client.get("/api/integrations/checkmk", headers=h).json()["enabled"] is True        # lesen darf jeder
    assert client.put("/api/admin/checkmk", headers=h, json={"base_url": ""}).status_code == 403


def test_control_characters_and_duplicates(client, admin):
    r = client.post("/api/import/checkmk", headers=admin, json={"hosts": [
        {"host": "swx", "inventory": tree(2, lldp=[nb("Gi0/1", "ap-1\x00", "ge1")], cdp=[nb("Gi0/1", "ap-1.example.test", "ge1")])}]})
    assert r.status_code == 200, r.text
    rows = client.get("/api/compare", headers=admin).json()["rows"]
    assert len(rows) == 1 and len(rows[0]["ist"]) == 1                              # LLDP+CDP zusammengefasst
    assert "\x00" not in rows[0]["ist"][0]["name"] and rows[0]["ist"][0]["protocol"] == "cdp/lldp"
    assert rows[0]["ist"][0]["name"] == "ap-1.example.test"                         # der vollständigere Name


def test_location_from_checkmk_tag(client, admin):
    """Standort-Hinweis aus dem Tag: legt Standort (Code + Name) an, setzt fehlende Orte, lässt genauere Platzierung am selben Standort in Ruhe."""
    hosts = lambda *names: [{"host": n, "inventory": tree(2), "location": {"code": "SITE01", "name": "Werk Nord"}} for n in names]  # noqa: E731
    assert client.post("/api/import/checkmk", headers=admin, json={"hosts": hosts("swa", "swb")}).status_code == 200
    site = [s for s in client.get("/api/sites", headers=admin).json() if s["code"] == "SITE01"][0]
    assert site["name"] == "Werk Nord"
    dev = {d["hostname"]: d for d in client.get("/api/devices?limit=50", headers=admin).json()["items"]}
    assert dev["swa"]["location_path"] == "SITE01 / Allgemein"
    # swa wird manuell in ein Rack am selben Standort gesetzt; ein erneuter Import darf das nicht zurücksetzen
    rack = client.post("/api/locations", headers=admin, json={"site_id": site["id"], "kind": "rack", "name": "R1", "rack_units": 20}).json()["id"]
    d = client.get(f"/api/devices/{dev['swa']['id']}", headers=admin).json()
    client.put(f"/api/devices/{d['id']}", headers=admin, json={**{k: d[k] for k in ("hostname", "type")}, "location_id": rack})
    r = client.post("/api/import/checkmk", headers=admin, json={"hosts": hosts("swa", "swb")})
    assert r.status_code == 200, r.text
    now = {x["hostname"]: x for x in client.get("/api/devices?limit=50", headers=admin).json()["items"]}
    assert now["swa"]["location_path"] == "SITE01 / R1" and now["swb"]["location_path"] == "SITE01 / Allgemein"
    # ein explizit angegebener site_code hat Vorrang vor dem Tag
    client.post("/api/import/checkmk", headers=admin, json={"site_code": "FIX", "hosts": hosts("swc")})
    assert {x["hostname"]: x for x in client.get("/api/devices?limit=50", headers=admin).json()["items"]}["swc"]["location_path"].startswith("FIX /")
    # Platzhalter-Name wird ersetzt
    client.post("/api/import/checkmk", headers=admin, json={"site_code": "PH", "hosts": [{"host": "swp", "inventory": tree(2)}]})
    assert [s["name"] for s in client.get("/api/sites", headers=admin).json() if s["code"] == "PH"] == ["PH"]
    client.post("/api/import/checkmk", headers=admin, json={"hosts": [{"host": "swp", "inventory": tree(2), "location": {"code": "PH", "name": "Phoenix"}}]})
    assert [s["name"] for s in client.get("/api/sites", headers=admin).json() if s["code"] == "PH"] == ["Phoenix"]


def test_export_tool_location_helpers(tmp_path):
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("cmk_export", pathlib.Path(__file__).resolve().parents[2] / "tools" / "checkmk_export.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert m.location_of("SITE01", "SITE01 Werk Nord") == {"code": "SITE01", "name": "Werk Nord"}
    assert m.location_of("X1", "") == {"code": "X1", "name": "X1"}
    assert m.location_of("-----", "x") is None and m.location_of("", "x") is None
    f = tmp_path / "etc/check_mk/multisite.d/wato"
    f.mkdir(parents=True)
    (f / "tags.mk").write_text("# Written by Checkmk store\n\nwato_tags.update({'tag_groups': [{'id': 'location', 'title': 'L', 'tags': [{'id': 'LOC1', 'title': 'LOC1 Werk Eins', 'aux_tags': []}]}], 'aux_tags': []})\n")
    assert m.tag_titles(tmp_path, "location") == {"LOC1": "LOC1 Werk Eins"} and m.tag_titles(tmp_path, "nope") == {}


def test_adopt_connection(client, admin, lab):
    """„Verbindung übernehmen“: undokumentierte Verbindung wird als vorläufiges Direktkabel angelegt."""
    rows, _ = by(client, admin)
    r = rows[("sw1", "Gi0/4")]
    assert r["status"] == "undocumented" and r["adopt"] is None                    # Nachbar „fremd-sw“ ist nicht im Bestand → nicht übernehmbar
    assert rows[("sw1", "Gi0/1")]["adopt"] is None                                # bereits dokumentiert
    sw1 = [d for d in client.get("/api/devices?limit=100", headers=admin).json()["items"] if d["hostname"] == "sw1"][0]["id"]
    ports = {p["name"]: p["id"] for p in client.get(f"/api/devices/{sw1}/ports", headers=admin).json()}
    assert client.post("/api/compare/adopt", headers=admin, json={"port_id": ports["Gi0/4"]}).status_code == 409   # keine Gegenstelle im Bestand

    # sw2 meldet Gi0/4 als undokumentierten Nachbarn von sw1: eindeutig und frei → übernehmbar
    imp = client.post("/api/import/checkmk", headers=admin, json={"site_code": "S1", "hosts": [
        {"host": "sw2", "inventory": tree(6, lldp=[nb("Gi0/1", "sw1", "Gi0/1"), nb("Gi0/6", "sw1", "Gi0/6")])}]})
    assert imp.status_code == 200, imp.text
    sw2 = [d for d in client.get("/api/devices?limit=100", headers=admin).json()["items"] if d["hostname"] == "sw2"][0]["id"]
    p2 = {p["name"]: p["id"] for p in client.get(f"/api/devices/{sw2}/ports", headers=admin).json()}
    rows, _ = by(client, admin)
    a = rows[("sw2", "Gi0/6")]
    assert a["status"] == "undocumented" and a["adopt"]["label"] == "sw1:Gi0/6"
    res = client.post("/api/compare/adopt", headers=admin, json={"port_id": p2["Gi0/6"]})
    assert res.status_code == 201, res.text
    cab = client.get("/api/cables", headers=admin, params={"provisional": True}).json()
    assert len(cab) == 1 and cab[0]["provisional"] is True and "Soll/Ist" in cab[0]["note"]
    assert client.post("/api/compare/adopt", headers=admin, json={"port_id": p2["Gi0/6"]}).status_code == 409    # jetzt dokumentiert
    rows, _ = by(client, admin)
    assert ("sw2", "Gi0/6") not in rows or rows[("sw2", "Gi0/6")]["status"] == "unmapped" or rows[("sw2", "Gi0/6")]["status"] != "undocumented"
    # Vorläufig-Kennzeichen aufheben („Strecke vollständig“)
    up = client.put(f"/api/cables/{cab[0]['id']}", headers=admin, json={"cable_type": "other", "provisional": False})
    assert up.status_code == 200, up.text
    assert client.get("/api/cables", headers=admin, params={"provisional": True}).json() == []
    assert client.get("/api/cables", headers=admin, params={"provisional": False}).json()


def test_releases(client, admin):
    from app import releases
    r = releases.parse("# Änderungen\n\n## 1.2.0 – 2026-01-02\n- Titel A: Text A\n- ohne Doppelpunkt\n\n## 1.1.0 – 2026-01-01\n- B: x\n")
    assert [x["version"] for x in r] == ["1.2.0", "1.1.0"]
    assert r[0]["items"] == [{"title": "Titel A", "text": "Text A"}, {"title": "", "text": "ohne Doppelpunkt"}]
    res = client.get("/api/releases", headers=admin)
    assert res.status_code == 200, res.text
    d = res.json()
    assert d["version"] == d["releases"][0]["version"] and all(x["items"] for x in d["releases"])
    assert client.get("/api/releases").status_code in (401, 403)
