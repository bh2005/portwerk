# Portwerk – Ideen und offene Punkte

Stand: 2026-11-23. Ursprünglich ein Abgleich von [docs/konzept.md](docs/konzept.md) mit dem Code (22.11.2026); die Punkte sind seitdem großteils umgesetzt.

## Offen

- **VLAN-Soll/Ist über Checkmk**
  Manche Switches liefern VLANs im Inventar mit; daraus einen Abgleich mit der dokumentierten Port-Konfiguration bauen (wie beim LLDP-Abgleich).
- **Webhooks nach außen** (Konzept, Etappe 4)
  Bisher gibt es nur den eingehenden OpenPlan-Webhook. Ereignisse wie „Auftrag bestätigt“ oder „LLDP-Abweichung“ an andere Systeme melden
  (signiert, mit Wiederholung) – nach dem Muster von OpenPlan.
- **Geräte aus OpenPlan als Importquelle** (Konzept, Abschnitt 6, Richtung 3)
  Neue Geräte aus Geräte-Rollouts (Hostname, Standort, Typ) übernehmen, damit ein geplanter Switch ohne Doppelerfassung im Bestand erscheint.
- **Historie für Geräte-Orte und Patchfeld-Paare**
  Historisiert sind nur Verbindungen; Zeitreise und „Pfad am Datum“ zeigen Orte und Durchschleifungen mit dem heutigen Stand.
- **Benachrichtigung „zur Bestätigung vorgeschlagen“**
  Wenn die LLDP-Prüfung einen ausgeführten Auftrag als stimmig meldet, die Freigeber per E-Mail informieren (bisher Karte auf der Übersicht).

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
| VLAN/Portprofil als Attribut (Katalog, Profile, Port-Konfiguration mit Historie, Aufträge) | (dieser PR) |
