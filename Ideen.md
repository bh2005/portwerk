# Portwerk – Ideen und offene Punkte

Stand: 2026-11-24. Ursprünglich ein Abgleich von [docs/konzept.md](docs/konzept.md) mit dem Code (22.11.2026); die Punkte sind seitdem großteils umgesetzt.

## Offen

- **VLAN-Soll/Ist für Trunks, Voice-VLANs und andere Hersteller**
  Checkmk liefert VLANs nur für Cisco und nur Access-VLANs (Plugin `inv_cisco_vlans`). Für Trunks/Voice bräuchte es eigene Daten
  (z. B. CISCO-VTP-MIB oder ein eigenes Inventar-Plugin).
- **Webhooks nach außen** (Konzept, Etappe 4)
  Bisher gibt es nur den eingehenden OpenPlan-Webhook. Ereignisse wie „Auftrag bestätigt“ oder „LLDP-Abweichung“ an andere Systeme melden
  (signiert, mit Wiederholung) – nach dem Muster von OpenPlan.
- **Geräte aus OpenPlan als Importquelle** (Konzept, Abschnitt 6, Richtung 3)
  Neue Geräte aus Geräte-Rollouts (Hostname, Standort, Typ) übernehmen, damit ein geplanter Switch ohne Doppelerfassung im Bestand erscheint.
- **Abwesenheiten aus OpenPlan übernehmen**
  OpenPlan führt Abwesenheiten (Urlaub, Schulung, Krankheit); diese könnten in Portwerk automatisch gelten, statt sie doppelt einzutragen.
- **Historie für Geräte-Orte und Patchfeld-Paare**
  Historisiert sind nur Verbindungen; Zeitreise und „Pfad am Datum“ zeigen Orte und Durchschleifungen mit dem heutigen Stand.
- **Kabelliste mit Filter „vorläufig“**
  `GET /api/cables?provisional=true` gibt es; eine Oberfläche, die alle noch nachzudokumentierenden Strecken auflistet, fehlt.
- **Checkmk-Anbindung über HTTPS**
  Die REST-Anbindung funktioniert mit jeder Adresse; sie sollte nach Möglichkeit über HTTPS laufen (Secret im Klartext vermeiden).
- **Sicherungsziel SFTP**
  Externe Ziele gibt es für Verzeichnis (NAS), S3 und WebDAV; SFTP bräuchte ein zusätzliches Paket (`paramiko`).
- **Tests unter Python 3.9**
  Zwei Tests (`test_timezone_offset_is_respected`, `test_workorder_pdf_content`) schlagen in der lokalen Python-3.9-Umgebung fehl; in der CI (3.12) ungeprüft.

## Umgesetzt

| Thema | PR |
|---|---|
| Verbindungs-Historie (`cable_history`, „Stand am“ auf der Geräteseite) | #1 |
| Vier-Augen-Prinzip (immer, Admin-Ausnahme mit Begründung) | #1 |
| Sicherung und Wiederherstellung (ZIP mit DB und TLS, täglich automatisch) | #2 |
| Kabeletiketten mit QR-Code (Band 12/19/24 mm, A4-Bögen, Scan-Ziel `/q/k/…`) | #3 |
| Arbeitsanweisung als PDF (Auftrag, Patchliste, E-Mail-Anhang) | #4 |
| Port-Reservierungen und Schutz vor doppelter Verplanung | #5 |
| Mobile Techniker-Ansicht (`/m`) | #6 |
| Pfad-Tracer als Grafik (beide Richtungen, LLDP-Abgleich der Enden) | #7 |
| Kapazitätsplanung (Ports je Kategorie, HE je Rack, Engpässe) | #8 |
| Zeitreise (Stand am, Vergleich, Pfad zu einem Zeitpunkt); Zeitzonen-Fehler bei „Stand am“ behoben | #9 |
| LLDP-Prüfung ausgeführter Aufträge, Vorschlag zur Bestätigung | #10 |
| README und Konzept auf den aktuellen Stand gebracht | #11 |
| VLAN/Portprofil als Attribut (Katalog, Profile, Port-Konfiguration mit Historie, Aufträge) | #19 |
| VLAN-Soll/Ist über Checkmk (Access-VLANs, Cisco), „Ist übernehmen“ | #20 |
| Arbeitsplatz-Assistent (Dose → Patchfeld → freier Switchport, Profil/VLAN, Auftrag) | #21 |
| E-Mail an Freigeber bei „zur Bestätigung vorgeschlagen“, persönliche Benachrichtigungen | #22 |
| Profil: weitere Benachrichtigungen, Standard-Standort, Startseite, alle anderen abmelden | #23 |
| Abwesenheit und Vertretung | #24 |
| Soll/Ist: „Verbindung übernehmen“ (vorläufiges Direktkabel), Verbindungs-Historie als Seitenleiste, Release-Tab, `index.html` ohne Cache | #25 |
| Soll/Ist: „In Bestand übernehmen“ für unbekannte Nachbargeräte | #26 |
| Checkmk-REST-Anbindung: Host prüfen, mit Ping und Standort-Tag anlegen (Aktivierung in Checkmk) | #26 |
| Strecken-Editor: ganze Strecke als Seitenleiste, Kabel bearbeiten, Zwischenstationen einfügen/entfernen | #26 |
| Dokumentation der Abläufe mit Beispielen (`docs/workflows/`) | #26 |
| Strecken-Editor: Umstecken (Ziel ändern) | (dieser PR) |
| Externe Sicherungsziele (NAS-Verzeichnis, S3, WebDAV), optional verschlüsselt, Wiederherstellung vom Ziel | (dieser PR) |
| Filter für Locations bei Racks & Schränke und bei den Standorten | (dieser PR) |
| Dark Mode: Standard-Textfarbe, Audit-Log lesbar | (dieser PR) |
| Checkmk: ausstehende Änderungen anzeigen und aus Portwerk aktivieren (nur ohne fremde Änderungen) | (dieser PR) |
