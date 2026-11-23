# Portwerk

Verwaltung und Planung von **Verkabelung/Patchungen** (Switchport ↔ Patchfeld ↔ Dose ↔ Endgerät) im Browser.
Schlank (ein Container: FastAPI + SQLite, Vue 3 + Tailwind), deutsche Oberfläche.

**Schwerpunkt ist der Ablauf, nicht die Bestandsliste:** Patchauftrag planen → freigeben → ausführen → bestätigen, mit Historie.
Per **Soll/Ist-Abgleich** (LLDP/CDP aus Checkmk) wird geprüft, ob die dokumentierte Verbindung wirklich so steckt. Eine feste Schnittstelle zu
[OpenPlan](https://github.com/bh2005/openplan) verbindet Patchaufträge mit der Projektplanung.

> **Stand:** Etappen 1–3 des [Konzepts](docs/konzept.md) sind umgesetzt, aus Etappe 4 die Beschriftungsetiketten; 267 Backend-Tests.
> Offene Ideen: [Ideen.md](Ideen.md).

## Funktionen

**Bestand**
- Standorte, Gebäude/Etagen/Räume, Racks mit Höheneinheiten (vorne/hinten, hochkant, Hutschiene), Rack-Ansicht
- Geräte mit Ports, Patchfelder mit Vorder-/Rückseite, Dosen; Gerätekatalog und Assistenten (Gerät, Kabel, Massenverkabelung, Standort)
- **Import** aus Checkmk (Inventar inkl. LLDP/CDP-Nachbarn, per Skript), CSV (mit Spaltenzuordnung), JSON und API – Trockenlauf, atomar, idempotent
- WAN-Leitungsverzeichnis (Provider, Leitungs-ID, Bandbreite, Vertrag)
- **Verbindungs-Historie:** jede Verbindung mit Zeitraum, wer/welcher Auftrag sie hergestellt und getrennt hat
- **Zeitreise:** Stand der Verkabelung zu einem Zeitpunkt, Vergleich zweier Zeitpunkte (neu, entfernt, umgesteckt, zwischenzeitlich)
- **Pfad-Tracer:** ganze Strecke über Patchfelder und Dosen als Grafik, mit Kabelfarben und LLDP-Abgleich der Enden – auch für einen früheren Zeitpunkt
- **Kapazität:** freie/belegte/verplante/reservierte Ports je Kategorie und freie HE je Rack, Engpässe unter einer Schwelle
- **Port-Reservierungen:** Ports für Projekte freihalten; doppelt verplante Ports lösen eine Rückfrage aus

**Ablauf**
- **Patchaufträge** (herstellen, trennen, umstecken, Gerät ein-/ausbauen, WAN) mit Konfliktprüfung, automatischem Rückbau-Auftrag bei belegten Ports und Historie
- **Vier-Augen-Prinzip:** wer anlegt/einreicht, gibt nicht frei; wer ausführt, bestätigt nicht – Administratoren können mit Begründung übersteuern (Audit-Log)
- **Arbeitsanweisung als PDF** (nach Ort gruppiert, Höheneinheit, Abhak-Kästchen, Unterschriftenfeld, QR-Code), CSV, Patchliste über mehrere Aufträge, Versand per E-Mail
- **Kabeletiketten mit QR-Code** (Band 12/19/24 mm, A4-Bögen); der Code führt zur Kabelseite – auch vor der Bestätigung und nach dem Umstecken
- **Mobile Techniker-Ansicht** (`/m`): Positionen am Rack abhaken, Etikett scannen, starten und fertigmelden
- **LLDP-Prüfung ausgeführter Aufträge** nach jedem Checkmk-Import; stimmt alles, wird der Auftrag zur Bestätigung vorgeschlagen
- **OpenPlan:** Aufträge als Vorgänge im Projektplan, Status- und Fortschrittsabgleich, Webhook zurück ([docs/openplan.md](docs/openplan.md))

**Verwaltung**
- Benutzer und Rollen (Administrator, Planer, Freigeber, Techniker, Betrachter), auch je Standort; lokal und AD/LDAP
- API-Zugänge (Tokens), Audit-Log, E-Mail (SMTP), Server-Zertifikat per ACME
- **Sicherung und Wiederherstellung** (täglich automatisch, Download, Wiederherstellen mit Prüfung)
- Hilfe-Panel (`F1`), Handbuch, Schnellsuche (`Strg+K`), Dark Mode

## Betrieb mit Docker

```bash
docker compose up -d --build                        # Oberfläche und API unter http://localhost:8084
docker compose logs portwerk | grep -i passwort     # Start-Passwort, wenn OPP_ADMIN_PASSWORD leer war
```

- **Daten** liegen im Volume `opp-data` (SQLite, TLS-Dateien). **Sicherungen** (Verwaltung → Sicherung, täglich automatisch) liegen im selben Volume unter
  `/data/backups` – für eine Kopie außerhalb des Servers herunterladen oder abholen: `docker compose cp portwerk:/data/backups ./backups`.
  Die Uhrzeit der automatischen Sicherung ist die Serverzeit (im Container UTC).
- **HTTPS:** Das Zertifikat lässt sich in der Verwaltung per ACME ausstellen; `TLS_PORT=8443` (siehe `docker-compose.yml`) startet den HTTPS-Listener.
  Für die mobile Ansicht gilt: Kamera-Scan im Browser und QR-Codes auf Etiketten/PDF, die auf dem Handy aufgehen sollen, brauchen eine echte Adresse
  mit HTTPS (nicht `localhost`). Etiketten und heruntergeladene PDFs verwenden die Adresse, unter der die Oberfläche geöffnet ist;
  Links in E-Mails und das PDF im E-Mail-Anhang die „Öffentliche URL der Anwendung“ (Verwaltung → E-Mail).
- **Build hinter einem TLS-inspizierenden Proxy:** Die Proxy-CA muss beim Build für `npm`, `pip` und `apt` (Schrift für die PDFs) bekannt sein.
- **Checkmk:** `tools/checkmk_export.py` überträgt Inventar und LLDP/CDP-Nachbarn – siehe [docs/checkmk-import.md](docs/checkmk-import.md).
  Jeder Import löst den Soll/Ist-Abgleich und die LLDP-Prüfung ausgeführter Aufträge aus.

### Konfiguration

Umgebungsvariablen (Präfix `OPP_`):

| Variable | Bedeutung |
|---|---|
| `OPP_DATA_DIR` | Datenverzeichnis (SQLite, TLS, Sicherungen); im Container `/data` |
| `OPP_ADMIN_USERNAME`, `OPP_ADMIN_PASSWORD` | Start-Administrator, nur beim ersten Start; leer = Zufallspasswort im Log |
| `OPP_SESSION_TTL_HOURS` | Gültigkeit einer Anmeldung (Standard 8) |
| `OPP_MIN_PASSWORD_LEN` | Mindestlänge lokaler Passwörter (Standard 8) |
| `OPP_BACKUP_BACKGROUND` | `0` schaltet die tägliche automatische Sicherung ab (Standard an) |
| `OPP_CORS_ORIGINS` | nur Entwicklung: erlaubte Ursprünge (Vite-Dev-Server) |
| `TLS_PORT` | zusätzlicher HTTPS-Listener, sobald ein Zertifikat vorliegt |
| `FORCE_HTTPS` | `1` leitet HTTP auf HTTPS um, aber erst wenn der HTTPS-Listener wirklich läuft (Ausnahmen: ACME-HTTP-01, `/health`); nur ohne vorgeschalteten TLS-Proxy |
| `PUBLIC_HTTPS_PORT` | Port in der Weiterleitung (Standard `443`) |

## Entwicklung

```bash
cd backend
python -m venv .venv && . .venv/bin/activate        # Python 3.12
pip install -r requirements-dev.txt
python -m pytest -q                                   # Tests
OPP_ADMIN_PASSWORD=ChangeMe-123 uvicorn app.main:app --reload    # API und Swagger unter http://localhost:8000/api/docs

cd ../frontend && npm install && npm run dev          # Oberfläche mit Hot Reload auf http://localhost:5173 (Proxy auf :8000)
```

Datenbankänderungen sind SQL-Migrationen unter `backend/migrations/` (werden beim Start angewendet). Die CI (GitHub Actions) führt die Backend-Tests aus
und baut die Oberfläche.

## Dokumentation

- [docs/konzept.md](docs/konzept.md) – Datenmodell, Ablauf, Rollen, Etappen und Stand der Umsetzung
- [docs/checkmk-import.md](docs/checkmk-import.md) – Import aus Checkmk
- [docs/openplan.md](docs/openplan.md) – Anbindung an OpenPlan
- [Ideen.md](Ideen.md) – umgesetzte und offene Ideen
- In der Anwendung: Hilfe-Panel (`F1`) und Handbuch

## Lizenz

MIT – siehe [LICENSE](LICENSE).
