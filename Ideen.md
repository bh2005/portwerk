# Portwerk – Ideen und offene Punkte

Stand: 2026-11-22. Abgleich von [docs/konzept.md](docs/konzept.md) mit dem aktuellen Code.

## Lücken gegenüber dem Konzept

1. **Verbindungs-Historie** ✔ *(umgesetzt: Tabelle `cable_history`, API `/api/cable-history`, Anzeige auf der Geräteseite)*
   Die Tabelle `links` hat kein `valid_from`/`valid_to`; getrennte Verbindungen werden gelöscht. Die Frage „Was steckte am 3. März
   an Gi1/0/12?“ lässt sich nur über das Audit-Log beantworten. Betrifft das Datenmodell und wird mit wachsendem Bestand teurer –
   daher zuerst angehen.
2. **Vier-Augen-Prinzip** ✔ *(umgesetzt: immer; Administratoren können mit Begründung übersteuern)*
   Die Rolle `freigeber` genügt; niemand wird daran gehindert, den eigenen Auftrag freizugeben (offener Punkt 5 im Konzept:
   immer, je Auftrag oder ab Priorität?).
3. **Arbeitsanweisung als PDF** ✔ *(umgesetzt: Auftrag und Patchliste, E-Mail-Anhang, QR-Code zum Auftrag)*
   Im Konzept vorgesehen (Druck/CSV/PDF), PDF ist nicht umgesetzt.
4. **Backup/Restore** ✔ *(umgesetzt: Verwaltung → Sicherung, ZIP mit DB + TLS, täglich automatisch, Wiederherstellung mit Prüfung)*
   Fehlt in der Oberfläche. Bei SQLite im Volume für den Betrieb wichtig (z. B. Download einer konsistenten Sicherung per
   `VACUUM INTO`, Einspielen mit Prüfung der Schema-Version).
5. **Etappe 4 (Ausbau)**
   - Webhooks nach außen (bisher nur der eingehende OpenPlan-Webhook)
   - Geräte aus OpenPlan als Importquelle (Richtung 3)
   - Beschriftungsetiketten
   - Abweichungsbericht Soll/Ist als eigener Bericht
6. **Dokumentation/Technik**
   - Konzept nennt TypeScript und PWA – das Frontend ist reines JavaScript ohne Manifest.
   - README-Status („Etappe 1“) und Konzept („Konzeptphase, noch kein Code“) sind veraltet.

## Neue Feature-Ideen

- **Kabeletiketten mit QR-Code** ✔ *(umgesetzt: Band 12/19/24 mm, A4-Bögen; QR mit Kabelnummer, Scan-Ziel /q/k/…)*
  Druckbares Etikett je Verbindung (Formate für Brother-/Dymo-Bänder). Der QR-Code führt zur Port-Detailseite, damit der
  Techniker vor Ort mit dem Handy scannen kann.
- **Mobile Techniker-Ansicht** ✔ *(umgesetzt: /m, Abhaken mit großen Knöpfen, Scannen, Einstieg über PDF-QR und Login am Handy)*
  Schlanke Seite „Mein Auftrag“ zum Abhaken der Positionen am Rack – große Schaltflächen, auch mit Handschuhen bedienbar.
- **Pfad-Tracer als Grafik** ✔ *(umgesetzt: „Pfad“ am Port und nach dem Scan, beide Richtungen, LLDP-Abgleich der Enden)*
  Die Kette Switch → Patchfeld → Dose → Endgerät gezeichnet statt als Liste, mit Soll/Ist-Status je Station.
- **Port-Reservierung** ✔ *(umgesetzt: Reservierungen mit Zweck/Frist, „verplant“ durch offene Aufträge, Rückfrage beim Verplanen)*
  Ports für geplante Aufträge oder Projekte vormerken, damit sie nicht doppelt verplant werden; fließt in die Konfliktprüfung ein.
- **Kapazitätsplanung**
  Freie Ports und Höheneinheiten je Rack bzw. Etage, Warnung bei weniger als 10 % frei.
- **Zeitreise-Ansicht** (setzt die Verbindungs-Historie voraus)
  Bestand zu einem beliebigen Datum anzeigen und zwei Zeitpunkte als Diff vergleichen.
- **Automatischer LLDP-Abgleich nach „Ausgeführt“**
  Abgleich im Checkmk-Takt, Auftrag wird automatisch zur Bestätigung vorgeschlagen.
- **VLAN/Portprofil als Attribut**
  Nur dokumentieren, nicht konfigurieren – damit Patchaufträge auch Anweisungen wie „Port auf VLAN 20“ tragen können.

## Vorgeschlagene Reihenfolge

1. ~~Verbindungs-Historie~~ ✔
2. ~~Vier-Augen-Prinzip~~ ✔
3. ~~Backup/Restore~~ ✔
4. ~~Kabeletiketten mit QR-Code~~ ✔
