# Portwerk – Ideen und offene Punkte

Stand: 2026-11-26. Ursprünglich ein Abgleich von [docs/konzept.md](docs/konzept.md) mit dem Code (22.11.2026); die Punkte sind seitdem großteils umgesetzt.

## Offen

- **Telefonie, weitere Schritte**
  Telefone am Arbeitsplatz (Dose ↔ Switchport, Voice-VLAN, PoE),
  kritische Sonderanschlüsse (Aufzugnotruf, BMA, EMA, Fax) mit Warnung beim Trennen, SBC-Zonen und TLS-Zertifikatsablauf, Import der Nebenstellen aus der HiPath.
- **VLAN-Soll/Ist für Trunks, Voice-VLANs und andere Hersteller**
  Checkmk liefert VLANs nur für Cisco und nur Access-VLANs (Plugin `inv_cisco_vlans`). Für Trunks/Voice bräuchte es eigene Daten
  (z. B. CISCO-VTP-MIB oder ein eigenes Inventar-Plugin).
- **Webhooks nach außen** (Konzept, Etappe 4)
  Bisher gibt es nur den eingehenden OpenPlan-Webhook. Ereignisse wie „Auftrag bestätigt“ oder „LLDP-Abweichung“ an andere Systeme melden
  (signiert, mit Wiederholung) – nach dem Muster von OpenPlan.
- **Historie für Geräte-Orte und Patchfeld-Paare**
  Historisiert sind nur Verbindungen; Zeitreise und „Pfad am Datum“ zeigen Orte und Durchschleifungen mit dem heutigen Stand.
- **Sicherungsziel SFTP**
  Externe Ziele gibt es für Verzeichnis (NAS), S3 und WebDAV; SFTP bräuchte ein zusätzliches Paket (`paramiko`).

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
| Autorouting: fehlende Patchungen zwischen Quell- und Zielport automatisch planen, neues Gerät als „geplant“ anlegen | #26 |
| Strecken-Editor: Umstecken (Ziel ändern) | #26 |
| Externe Sicherungsziele (NAS-Verzeichnis, S3, WebDAV), optional verschlüsselt, Wiederherstellung vom Ziel | #26 |
| Filter für Locations bei Racks & Schränke und bei den Standorten | #26 |
| Dark Mode: Standard-Textfarbe, Audit-Log lesbar | #26 |
| Checkmk: ausstehende Änderungen anzeigen und aus Portwerk aktivieren (nur ohne fremde Änderungen) | #26 |
| Aufräumen: vorläufige Kabel, von LLDP nicht gesehene Verbindungen, abgelaufene Reservierungen, liegengebliebene Aufträge, geplante Geräte ohne Auftrag; wöchentlicher Bericht an die Admins | #27 |
| Abwesenheiten aus OpenPlan übernehmen, Standard-Vertretung (OpenPlan: `GET /api/absences`, Token-Freigabe „Abwesenheiten“) | #28 |
| Geräte aus OpenPlan übernehmen (Geräte-Rollouts → geplante Geräte, Rückverweis in OpenPlan) | #29 |
| „Nicht gesehen seit …“: LLDP-Verlauf je Verbindung (zuletzt gesehen, fehlt seit) in Soll/Ist und Aufräumbericht | #30 |
| Änderungen anderer bemerken (Revision, Hinweis „Neu laden“) | #31 |
| Light Mode in Graustufen | #32 |
| Untertitel „Portwerk – so isses.“ | #33 |
| Englisch, Etappe 1: Grundgerüst (`i18n.js`, `locales/`), Sprachwahl im Profil und auf der Anmeldeseite, Rahmen und Übersicht | #34 |
| Englisch, Etappe 2: Bestand (Standorte, Geräte, Racks, Strecken, Geräte-Assistent) | #35 |
| Englisch, Etappe 3: Patchaufträge (Liste, Detail, mobile Ansicht, Patchliste, Etiketten, Reservierungen, Kabel-Assistenten) | #36 |
| Englisch, Etappe 4: Analyse (Soll/Ist, Kapazität, Zeitreise, Aufräumen, VLANs, WAN, Katalog) | #37 |
| Englisch, Etappe 5: Verwaltung und Import (Oberfläche vollständig) | #38 |
| Handbuch und Hilfe auf Englisch; Handbuch aktualisiert | #39 |
| Englisch für Mails (Sprache des Empfängers), PDF, CSV und Etikettenformate – Portwerk vollständig zweisprachig | #40 |
| Tests unter Python 3.9 (CI prüft 3.9 und 3.12); Warnung bei Checkmk-Anbindung ohne HTTPS | #41 |
| Telefonie: Gerätetypen und Port-Medien (HiPath), SIP-Trunks mit SBC/TK-Anlage/WAN, Aufträge; WAN und Telefonie nur mit Freigabe | #42 |
| Telefonie: Rufnummernplan (Blöcke, Durchwahlen frei/reserviert/vergeben, Suche, CSV) | (dieser PR) |
