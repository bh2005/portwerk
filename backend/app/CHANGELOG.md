# Änderungen

Format: `## <Version> – <Datum>`, darunter je Änderung eine Zeile `- Titel: Beschreibung`. Neueste Version zuerst. Wird in der Verwaltung unter „Releases“ angezeigt.

## 0.4.1 – 2026-11-24
- Standort-Tag beim Anlegen in Checkmk: Neue Hosts bekommen das Tag `location` (z. B. LOC026) passend zum Standort des meldenden Geräts; im Dialog änderbar, geprüft gegen die in Checkmk vorhandenen Tag-Werte.

## 0.4.0 – 2026-11-24
- Checkmk-REST-Anbindung: Unter Verwaltung → Checkmk lässt sich ein Automation-User hinterlegen. Beim Übernehmen eines unbekannten Geräts zeigt Portwerk, ob der Host in Checkmk existiert.
- In Checkmk anlegen: Fehlt der Host, legt Portwerk ihn mit reinem Host-Check (Ping, ohne Agent und SNMP) im gewählten Ordner an. Die Änderung bleibt ausstehend und wird in Checkmk aktiviert; Portwerk aktiviert nie selbst.

## 0.3.1 – 2026-11-24
- Soll/Ist: In Bestand übernehmen: Ein per LLDP/CDP gesehenes, aber unbekanntes Gerät lässt sich direkt aus dem Abgleich anlegen (Hostname, Typ-Vorschlag aus den gemeldeten Fähigkeiten, IP, Port). Optional wird die Verbindung als vorläufiges Direktkabel dokumentiert; ein unbekannter lokaler Port wird mit angelegt.

## 0.3.0 – 2026-11-24
- Soll/Ist: Verbindung übernehmen: Eine per LLDP/CDP gesehene, bisher undokumentierte Verbindung lässt sich mit einem Klick als Direktkabel dokumentieren. Sie wird als „vorläufig“ markiert; Dosen und Patchfelder können später nachgetragen werden („vollständig“ hebt die Markierung auf).
- Verbindungs-Historie als Seitenleiste: Die Historie eines Ports oder Geräts öffnet sich von rechts, im Gerätedetail und im Soll/Ist-Abgleich.
- Releases in der Verwaltung: Dieser Tab zeigt die Änderungen je Version.
- Oberfläche wird nach Updates sofort neu geladen: `index.html` wird nicht mehr vom Browser zwischengespeichert.

## 0.2.0 – 2026-11-23
- Abwesenheit und Vertretung: Im Abwesenheitszeitraum gehen Benachrichtigungen an die Vertretung; „Meine Aufgaben“ zeigt ihr die Aufträge.
- Profil-Erweiterungen: Eigene Benachrichtigungs- und Erinnerungseinstellungen im Profil.
- Mail mit Bestätigungsvorschlag: Auftragsmails enthalten einen Vorschlag zur Bestätigung.
- Arbeitsplatz-Assistent: Dose bis zum Switch patchen und VLAN setzen, als Auftrag.
- VLAN-Soll/Ist: VLAN-Abgleich gegen Checkmk neben dem Verkabelungs-Abgleich.
- VLAN-Portprofile: VLANs und Portprofile pflegen, je Port dokumentieren und per Auftrag umkonfigurieren.
- WAN-Details als Seitenleiste: Die Details einer WAN-Leitung öffnen von rechts (wiederverwendbare Komponente `SidePanel`).
- Export-Skript für Checkmk: Funktioniert mit Python ab 3.13 und Zertifikatsketten interner CAs.
- HTTP→HTTPS-Weiterleitung: Optional per `FORCE_HTTPS`; ACME-Challenge und `/health` bleiben ausgenommen.
- Haken „alle Standorte“: Benutzer können den Standortfilter auf alle ihre Standorte setzen.
- Audit-Suche: Das Audit-Log lässt sich durchsuchen und filtern.
- AD-Rollen: Manuell vergebene Rollen von AD-Konten bleiben erhalten, solange keine Gruppen zugeordnet sind.
- OpenPlan-Links: Aufträge verweisen auf die zugehörigen OpenPlan-Vorgänge.

## 0.1.0 – 2026-11-22
- Zeitreise: Stand der Verkabelung zu einem beliebigen Zeitpunkt und Vergleich zweier Zeitpunkte.
- LLDP-Bestätigung: Ausgeführte Aufträge werden nach dem Checkmk-Import gegen die gesehenen Nachbarn geprüft.
- Kapazität: Freie und belegte Ports je Standort und Gerät.
- Pfad-Tracer: Ganze Strecke über Patchfelder und Dosen bis zum Endgerät.
- Mobile Ansicht für Techniker: Etikett scannen, Aufträge abhaken.
- Port-Reservierung: Ports für einen Zweck reservieren.
- Arbeitsanweisung als PDF: Auftrag als druckbare Anweisung.
- Kabeletiketten: Etiketten drucken und per QR auflösen.
- Sicherung: Datensicherung und Wiederherstellung in der Verwaltung.
- Verbindungs-Historie und Vier-Augen-Prinzip: Jede Verbindung mit Zeitraum, Änderungen über Aufträge mit Freigabe.
