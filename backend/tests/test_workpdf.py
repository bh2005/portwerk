"""Arbeitsanweisung als PDF: Inhalt, Warnhinweise, Patchliste, Zugriff."""
import io

import pytest
from pypdf import PdfReader

from conftest import login


@pytest.fixture()
def lab(client, admin):
    s = client.post("/api/sites", headers=admin, json={"code": "W1", "name": "Werk"}).json()
    s2 = client.post("/api/sites", headers=admin, json={"code": "W2", "name": "Fremd"}).json()
    rack = client.post("/api/locations", headers=admin, json={"site_id": s["id"], "kind": "rack", "name": "R-Süd", "rack_units": 20}).json()["id"]
    rack2 = client.post("/api/locations", headers=admin, json={"site_id": s2["id"], "kind": "rack", "name": "R2", "rack_units": 20}).json()["id"]

    def dev(name, ports, loc=rack):
        d = client.post("/api/devices", headers=admin, json={"hostname": name, "type": "switch", "location_id": loc}).json()
        return {"id": d["id"], **{n: client.post(f"/api/devices/{d['id']}/ports", headers=admin, json={"name": n, "medium": "RJ45"}).json()["id"]
                                  for n in ports}}
    sw, pc, pc2 = dev("sw-1", ["Gi1", "Gi2"]), dev("pc-ä", ["eth0"]), dev("pc-2", ["eth0"])
    far = dev("sw-far", ["Gi1", "Gi2"], rack2)
    assert client.put(f"/api/ports/{sw['Gi2']}/cable", headers=admin, json={"port_b_id": pc2["eth0"]}).status_code == 200
    wo = client.post("/api/workorders", headers=admin, json={"title": "Umbau Etage 2", "description": "Bitte vorsichtig.",
                                                             "location_id": rack, "planned_from": "2026-12-01"}).json()
    add = lambda **b: client.post(f"/api/workorders/{wo['id']}/items", headers=admin, json=b)  # noqa: E731
    assert add(action="connect", port_a_id=sw["Gi1"], port_b_id=pc["eth0"], cable_label="K-1", cable_type="Cat6a", length_m=2, color="blau").status_code == 201
    assert add(action="disconnect", port_a_id=sw["Gi2"]).status_code == 201
    wo2 = client.post("/api/workorders", headers=admin, json={"title": "Fremd", "location_id": rack2}).json()
    client.post(f"/api/workorders/{wo2['id']}/items", headers=admin, json={"action": "connect", "port_a_id": far["Gi1"], "port_b_id": far["Gi2"]})
    return {"wo": wo, "wo2": wo2, "site1": s["id"]}


def text_of(content: bytes) -> str:
    assert content.startswith(b"%PDF")
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(content)).pages)


def test_workorder_pdf_content(client, admin, lab):
    r = client.get(f"/api/workorders/{lab['wo']['id']}/pdf", headers=admin, params={"base": "https://pw.example"})
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert f'{lab["wo"]["number"]}-arbeitsanweisung.pdf' in r.headers["content-disposition"]
    t = text_of(r.content)
    for s in (f"Arbeitsanweisung {lab['wo']['number']}", "Umbau Etage 2", "Bitte vorsichtig.", "01.12.2026", "W1 / R-Süd",
              "sw-1:Gi1", "pc-ä:eth0", "K-1 · Cat6A · 2 m · blau", "trennen", "sw-1:Gi2", "pc-2:eth0",
              "Noch nicht freigegeben", "Unterschrift", "Seite 1/"):
        assert s in t, (s, t)


def test_warning_disappears_after_approval(client, admin, lab):
    wid = lab["wo"]["id"]
    for act in ("submit", "approve"):
        assert client.post(f"/api/workorders/{wid}/transition/{act}", headers=admin, json={"override_reason": "Test (allein)"}).status_code == 200
    t = text_of(client.get(f"/api/workorders/{wid}/pdf", headers=admin).content)
    assert "Noch nicht freigegeben" not in t and "Freigegeben von" in t


def test_many_items_span_pages(client, admin, lab):
    wid = lab["wo"]["id"]
    pdf = client.get(f"/api/workorders/{wid}/pdf", headers=admin).content
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1
    for i in range(60):
        client.post(f"/api/workorders/{wid}/items", headers=admin, json={"action": "connect", "cable_label": f"X-{i:03d}", "note": "lang " * 10})
    pages = PdfReader(io.BytesIO(client.get(f"/api/workorders/{wid}/pdf", headers=admin).content)).pages
    assert len(pages) >= 3 and "Nr" in pages[1].extract_text()                          # Tabellenkopf auf Folgeseiten


def test_patchlist_pdf_and_access(client, admin, lab):
    ids = f"{lab['wo']['id']},{lab['wo2']['id']}"
    r = client.get("/api/patchlists/pdf", headers=admin, params={"ids": ids})
    assert r.status_code == 200
    t = text_of(r.content)
    assert "Patchliste" in t and lab["wo"]["number"] in t and lab["wo2"]["number"] in t and "sw-far:Gi1" in t
    r = client.post("/api/users", headers=admin, json={"username": "w1", "password": "Passwort-123", "roles": [],
                                                       "scopes": [{"site_id": lab["site1"], "role": "viewer"}]})
    h = login(client, "w1", "Passwort-123")
    assert client.get(f"/api/workorders/{lab['wo']['id']}/pdf", headers=h).status_code == 200
    assert client.get(f"/api/workorders/{lab['wo2']['id']}/pdf", headers=h).status_code == 404
    assert client.get("/api/patchlists/pdf", headers=h, params={"ids": ids}).status_code == 404
    assert client.get(f"/api/workorders/{lab['wo']['id']}/pdf", headers=admin, params={"base": "ftp://x"}).status_code == 400


def test_fallback_font_without_dejavu(client, admin, lab, monkeypatch):
    from app import workpdf
    monkeypatch.setattr(workpdf, "_font_dir", lambda: None)
    t = text_of(client.get(f"/api/workorders/{lab['wo']['id']}/pdf", headers=admin).content)
    assert "pc-ä:eth0" in t and "[ ]" in t                                              # Latin-1 bleibt, Kästchen als Ersatz


def test_rack_units_in_patchlist_and_pdf_qr_points_to_mobile_view(client, admin, lab, monkeypatch):
    from app import workpdf
    sw = client.get("/api/devices", headers=admin, params={"q": "sw-1"}).json()["items"][0]
    body = {k: sw.get(k) for k in ("hostname", "type", "location_id", "status")} | {"rack_position": 7}
    assert client.put(f"/api/devices/{sw['id']}", headers=admin, json=body).status_code == 200
    items = client.get("/api/patchlists", headers=admin, params={"ids": str(lab["wo"]["id"])}).json()["items"]
    assert {x["a_unit"] for x in items} == {7} and items[0]["a_device_id"] == sw["id"]
    seen, orig = {}, workpdf._qr_png
    monkeypatch.setattr(workpdf, "_qr_png", lambda url: seen.setdefault("url", url) and orig(url))
    t = text_of(client.get(f"/api/workorders/{lab['wo']['id']}/pdf", headers=admin, params={"base": "https://pw.example"}).content)
    assert seen["url"] == f"https://pw.example/m/wo/{lab['wo']['id']}" and "HE 7" in t
