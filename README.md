# Portwerk

Verwaltung und Planung von **Verkabelung/Patchungen** (Switchport ↔ Patchfeld ↔ Dose ↔ Endgerät) im Browser.
Schlank (ein Container: FastAPI + SQLite, Vue 3 + Tailwind), deutsche Oberfläche.

**Schwerpunkt ist der Ablauf, nicht die Bestandsliste:** Patchauftrag planen → freigeben → ausführen → bestätigen, mit Historie.
Per **Soll/Ist-Abgleich** (LLDP) wird geprüft, ob die dokumentierte Verbindung wirklich so steckt. Eine feste Schnittstelle zu
[OpenPlan](https://github.com/bh2005/openplan) verbindet Patchaufträge mit der Projektplanung.

> **Status: Etappe 1 (Stammdaten, Import, Oberfläche).** Standorte/Racks, Geräte mit Ports, Rack-Ansicht, Import (CSV, JSON, API, Checkmk),
> Benutzer/Rollen, API-Zugänge, Audit-Log, Hilfe-Panel (`F1`) und Handbuch sind implementiert (56 Tests). Patchaufträge und die
> OpenPlan-Anbindung folgen – siehe [docs/konzept.md](docs/konzept.md) (Datenmodell, Ablauf, Etappen) und
> [docs/checkmk-import.md](docs/checkmk-import.md).

## Betrieb mit Docker

```bash
docker compose up -d --build         # Oberfläche und API unter http://localhost:8084
docker compose logs portwerk | grep -i passwort    # Start-Passwort, wenn OPP_ADMIN_PASSWORD leer war
```

Die Daten liegen im Volume `opp-data` (SQLite). Sicherungen (Verwaltung → Sicherung, täglich automatisch) liegen im selben Volume unter `/data/backups` – für eine Kopie
außerhalb des Servers herunterladen oder das Verzeichnis abholen, z. B. `docker compose cp portwerk:/data/backups ./backups`. Hinter einem TLS-inspizierenden Proxy müssen die Proxy-CA-Zertifikate beim Build bekannt sein.

## Schnellstart (Entwicklung)

```bash
cd backend
python -m venv .venv && . .venv/bin/activate        # Python 3.12
pip install -r requirements-dev.txt
python -m pytest -q                                   # Tests
OPP_ADMIN_PASSWORD=ChangeMe-123 uvicorn app.main:app --reload    # API und Swagger unter http://localhost:8000/api/docs

cd ../frontend && npm install && npm run dev          # Oberfläche mit Hot Reload auf http://localhost:5173 (Proxy auf :8000)
```

Konfiguration über Umgebungsvariablen (Präfix `OPP_`): `OPP_DATA_DIR` (SQLite, Standard `./data`), `OPP_ADMIN_USERNAME`,
`OPP_ADMIN_PASSWORD` (Start-Admin, nur beim ersten Start; leer = Zufallspasswort im Log), `OPP_SESSION_TTL_HOURS`.

## Geplante Funktionen

- **Import** von Geräten und Ports aus **Checkmk** (Inventar, per Skript), **CSV** (mit Spaltenzuordnung), **JSON** und per **API** (Trockenlauf, atomar, idempotent) ✔
- **Patchaufträge** mit Konfliktprüfung, Freigabe, Arbeitsanweisung (Druck/CSV/PDF) und Historie
- **Soll/Ist-Abgleich** über LLDP-Nachbarn
- **OpenPlan-Schnittstelle:** Aufträge ↔ Vorgänge, Statusrückmeldung, Webhooks
- Benutzer und Rollen (lokal, optional AD/LDAP), Audit-Log, Hilfe-Panel (`F1`), Dark Mode

## Lizenz

MIT – siehe [LICENSE](LICENSE).

## WAN-Verbindungen

Das Menü „WAN“ führt das Leitungsverzeichnis (Provider, Leitungs-ID, Technik, Bandbreite, Vertrag, Endpunkte mit optionalem Port). Inbetriebnahme, Änderung und
Kündigung laufen als Positionen in Patchaufträgen (`wan_activate`, `wan_change`, `wan_terminate`); der Bestand ändert sich beim Bestätigen. API: `/api/wan`.
