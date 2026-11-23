#!/usr/bin/env python3
"""Checkmk-Inventar nach Portwerk übertragen.

Läuft auf dem Checkmk-Server (als Site-Benutzer oder root), liest die HW/SW-Inventar-JSON-Dateien
(``<site>/var/check_mk/inventory/<host>.json``) und schickt Hosts mit Interfaces an ``POST /api/import/checkmk``.
Nur die Standardbibliothek wird benötigt (Python >= 3.8).

Beispiele
  # Trockenlauf (Standard-Verzeichnis der Site „test“): zeigt, was passieren würde
  ./checkmk_export.py --site test --url https://opp.example.com --token opp_... --dry-run

  # echter Import, nur Hosts passend zu einem Muster, mit Standort-Zuordnung
  ./checkmk_export.py --site test --url https://opp.example.com --token opp_... --hosts '^sw-' --site-code SITE-A

  # nur ausgeben, nichts senden (z. B. zum Prüfen oder für den JSON-Import)
  ./checkmk_export.py --site test --print > export.json

  # Standort aus dem Host-Tag „location“ (Tag-Gruppe) übernehmen: Tag-ID = Standort-Code, Tag-Titel = Name
  ./checkmk_export.py --site test --url https://opp.example.com --token opp_... --location-tag location

Den API-Zugang (Umfang „write“) legt ein Administrator in Portwerk unter Verwaltung → API-Zugänge an.
Das Token kann auch über die Umgebungsvariable OPP_TOKEN gesetzt werden (dann taucht es nicht in der Prozessliste auf).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path


def has_interfaces(tree: dict) -> bool:
    try:
        return bool(tree["Nodes"]["networking"]["Nodes"]["interfaces"]["Table"]["Rows"])
    except (KeyError, TypeError):
        return False


def load_hosts(inv_dir: Path, pattern: str = "", only_with_interfaces: bool = True) -> list[dict]:
    """Liest alle ``*.json`` (Host = Dateiname ohne Endung); ``*.json.gz`` wird ignoriert."""
    rx = re.compile(pattern) if pattern else None
    out = []
    for f in sorted(inv_dir.glob("*.json")):
        host = f.name[:-5]
        if rx and not rx.search(host):
            continue
        try:
            tree = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"übersprungen: {f.name}: {e}", file=sys.stderr)
            continue
        if only_with_interfaces and not has_interfaces(tree):
            continue
        out.append({"host": host, "inventory": tree})
    return out


def tag_titles(site_dir: Path, group: str) -> dict:
    """Titel der Tags einer Tag-Gruppe aus ``etc/check_mk/multisite.d/wato/tags.mk`` ({tag-id: titel}); leer, wenn nicht lesbar."""
    f = site_dir / "etc/check_mk/multisite.d/wato/tags.mk"
    try:
        text = f.read_text(encoding="utf-8")
        data = ast.literal_eval(text[text.index("(", text.index("wato_tags.update")) + 1:text.rindex(")")])
    except (OSError, ValueError, SyntaxError) as e:
        print(f"Tag-Titel nicht lesbar ({f}): {e}", file=sys.stderr)
        return {}
    for g in data.get("tag_groups", []):
        if g.get("id") == group:
            return {t["id"]: str(t.get("title") or "") for t in g.get("tags", []) if t.get("id")}
    return {}


def livestatus_tags(sock_path: Path, group: str) -> dict:
    """{host: tag-wert} für eine Tag-Gruppe per Livestatus (Unix-Socket der Site)."""
    q = "GET hosts\nColumns: name tags\nOutputFormat: json\n\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(str(sock_path))
        s.sendall(q.encode())
        s.shutdown(socket.SHUT_WR)
        data = b""
        while chunk := s.recv(65536):
            data += chunk
    return {name: tags.get(group, "") for name, tags in json.loads(data.decode("utf-8"))}


def location_of(code: str, title: str) -> dict | None:
    """Tag -> Standort. Leere Werte und reine Striche („-----“ = kein Wert) gelten als „kein Standort“; ein führender Code im Titel wird entfernt."""
    code = (code or "").strip()
    if not code or not code.strip("-_ "):
        return None
    name = (title or "").strip()
    if name.upper().startswith(code.upper()):
        name = name[len(code):].strip(" -–:")
    return {"code": code, "name": name or code}


def attach_locations(hosts: list[dict], site_dir: Path, sock: Path, group: str) -> int:
    try:
        values = livestatus_tags(sock, group)
    except (OSError, ValueError) as e:
        print(f"Livestatus nicht lesbar ({sock}): {e} – Standorte werden nicht übernommen", file=sys.stderr)
        return 0
    titles = tag_titles(site_dir, group)
    n = 0
    for h in hosts:
        code = values.get(h["host"], "")
        loc = location_of(code, titles.get(code, ""))
        if loc:
            h["location"] = loc
            n += 1
    return n


def post(url: str, token: str, payload: dict, ca_file: str = "", insecure: bool = False, timeout: int = 300) -> dict:
    ctx = ssl.create_default_context(cafile=ca_file or None)
    if ca_file:                         # interne CAs (z. B. step-ca) setzen oft pathLen ohne keyCertSign; Python >= 3.13 prüft das streng (Kette und Hostname werden weiter geprüft)
        ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url.rstrip("/") + "/api/import/checkmk", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + token}, method="POST")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"Fehler {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise SystemExit(f"Verbindung fehlgeschlagen: {e.reason}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=os.environ.get("OMD_SITE", ""), help="Checkmk-Site (bestimmt das Standardverzeichnis)")
    ap.add_argument("--inventory-dir", default="", help="Verzeichnis der Inventar-JSONs (Standard: /omd/sites/<site>/var/check_mk/inventory)")
    ap.add_argument("--url", default=os.environ.get("OPP_URL", ""), help="Adresse von Portwerk, z. B. https://opp.example.com")
    ap.add_argument("--token", default=os.environ.get("OPP_TOKEN", ""), help="API-Zugang (opp_…), besser per OPP_TOKEN setzen")
    ap.add_argument("--hosts", default="", help="Regulärer Ausdruck für Hostnamen (Standard: alle mit Interfaces)")
    ap.add_argument("--site-code", default="", help="Standort-Code, dem alle Geräte zugeordnet werden")
    ap.add_argument("--location-tag", default="", help="Tag-Gruppe (ID) mit dem Standort, z. B. location: Tag-ID = Standort-Code, Titel = Name (gelesen per Livestatus)")
    ap.add_argument("--all-interfaces", action="store_true", help="auch Loopbacks, VLANs und Tunnel als Ports übernehmen")
    ap.add_argument("--dry-run", action="store_true", help="nichts speichern, nur das Ergebnis anzeigen")
    ap.add_argument("--no-atomic", action="store_true", help="fehlerhafte Hosts überspringen statt den ganzen Stapel abzulehnen")
    ap.add_argument("--batch", type=int, default=300, help="Hosts je Anfrage (Standard 300)")
    ap.add_argument("--ca-file", default="", help="CA-Zertifikat für HTTPS (interne CA)")
    ap.add_argument("--insecure", action="store_true", help="Zertifikat nicht prüfen (nur für Tests)")
    ap.add_argument("--print", dest="print_only", action="store_true", help="nur als JSON ausgeben, nichts senden")
    a = ap.parse_args(argv)

    inv = Path(a.inventory_dir or f"/omd/sites/{a.site}/var/check_mk/inventory")
    if not inv.is_dir():
        raise SystemExit(f"Inventarverzeichnis nicht gefunden: {inv} (--site oder --inventory-dir angeben)")
    hosts = load_hosts(inv, a.hosts)
    print(f"{len(hosts)} Host(s) mit Interfaces in {inv}", file=sys.stderr)
    if a.location_tag:
        site_dir = Path(a.inventory_dir).parents[3] if a.inventory_dir else Path(f"/omd/sites/{a.site}")
        print(f"Standort aus Tag „{a.location_tag}“ für {attach_locations(hosts, site_dir, site_dir / 'tmp/run/live', a.location_tag)} von {len(hosts)} Host(s)", file=sys.stderr)
    if a.print_only:
        json.dump({"hosts": hosts}, sys.stdout)
        return 0
    if not hosts:
        return 0
    if not a.url or not a.token:
        raise SystemExit("--url und --token (oder OPP_URL/OPP_TOKEN) sind nötig")

    total = {"created": 0, "updated": 0, "unchanged": 0, "errors": 0}
    failed = False
    for i in range(0, len(hosts), max(1, a.batch)):
        chunk = hosts[i:i + a.batch]
        res = post(a.url, a.token, {"hosts": chunk, "dry_run": a.dry_run, "atomic": not a.no_atomic,
                                    "site_code": a.site_code, "include_all_interfaces": a.all_interfaces},
                   a.ca_file, a.insecure)
        for k in total:
            total[k] += res["stats"].get(k, 0)
        print(f"Stapel {i // a.batch + 1}: {res['stats']} angewendet={res['applied']} übersprungen={res.get('skipped_count', 0)}", file=sys.stderr)
        for it in res["items"]:
            if it["outcome"] == "error":
                print(f"  FEHLER {it['hostname']}: {it.get('message')}", file=sys.stderr)
                failed = True
    print(("TROCKENLAUF – " if a.dry_run else "") + f"Gesamt: {total}", file=sys.stderr)
    return 1 if failed and not a.no_atomic else 0


if __name__ == "__main__":
    sys.exit(main())
