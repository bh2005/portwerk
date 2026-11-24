# Änderungen

Format: `## <Version> – <Datum>`, darunter je Änderung eine Zeile `- Titel: Beschreibung`. Neueste Version zuerst. Wird in der Verwaltung unter „Releases“ angezeigt.

## 0.8.1 – 2026-11-24
- Hinweis-Mail bei neuen Benutzern: Meldet sich ein Konto ohne Rechte erstmals an, erhalten die globalen Administratoren eine Mail („Neuer Benutzer wartet auf Freischaltung“); abbestellbar im Profil. Die Hinweisseite des Benutzers nennt, dass die Administratoren informiert wurden – nur wenn die Mail tatsächlich versendet wurde.

## 0.8.0 – 2026-11-24
- Neue Benutzer ohne Rechte: Ein Konto ohne Rolle und ohne Standort-Recht (z. B. beim ersten AD-Login angelegt) kann sich anmelden, sieht aber nur den Hinweis „Noch keine Berechtigung – bitte an einen Administrator wenden“ und keine Daten. In der Benutzerverwaltung steht „wartet auf Freischaltung“.
- AD-Standard geändert: „Rolle ohne passende Gruppe“ ist jetzt standardmäßig leer (Konto ohne Rechte) statt „Betrachter“; eine leere Einstellung verweigert die Anmeldung nicht mehr, sondern legt ein Konto ohne Rechte an. Bestehende Einstellungen bleiben unverändert.

## 0.7.1 – 2026-11-24
- Dark Mode, Korrektur: Die Standard-Textfarbe aus 0.7.0 griff in der App nicht (die Klasse `dark` sitzt auf dem Wurzel-Element der App, nicht auf `html`). Tabellen im Audit-Log, in der Übersicht, bei den Geräten und in der Verwaltung sind jetzt im Dark Mode lesbar; geprüft in 14 Ansichten mit dem echten Dark-Mode-Schalter.

## 0.7.0 – 2026-11-24
- Externe Sicherungsziele: Sicherungen lassen sich zusätzlich auf ein eingehängtes Verzeichnis (NAS per NFS/SMB), einen S3-kompatiblen Speicher oder WebDAV ablegen – automatisch nach jeder Sicherung, manuell über „Extern ablegen“. Je Ziel eigene Aufbewahrung, Test, Status und Liste der Sicherungen; Wiederherstellung direkt vom Ziel.
- Verschlüsselung der externen Sicherungen: Optional mit Passphrase (AES-256-GCM) vor der Übertragung.
- Dark Mode: Tabellen, u. a. das Audit-Log, waren unlesbar (dunkle Schrift auf dunklem Grund). Standard-Textfarbe und gedämpfte Detail-Spalte entsprechen jetzt dem RSYSLOG-Manager.
- Korrektur: „Jetzt sichern“ war im Ruhezustand deaktiviert.

## 0.6.1 – 2026-11-24
- Filter bei Racks & Schränke: Auswahl nach Standort, Art und Suchtext (Name, Pfad, Kennung); die Auswahl springt auf den ersten Treffer.
- Filter bei den Standorten: Suche in der Standortliste (Code, Name, Adresse) und Filter im Location-Baum nach Name, Kennung und Art – Treffer werden mit ihrem Oberbau gezeigt.

## 0.6.0 – 2026-11-24
- Umstecken im Strecken-Editor: Ein Kabelende lässt sich an einen anderen Port stecken, das Kabel behält alle Angaben; in der Historie endet die alte Verbindung, die neue beginnt.
- Änderungen in Checkmk aktivieren: Ausstehende Änderungen werden angezeigt (eigene und fremde) und lassen sich nach Rückfrage aus Portwerk aktivieren – nur wenn keine fremden Änderungen anstehen. Im Dialog „In Bestand übernehmen“ und unter Verwaltung → Checkmk.

## 0.5.0 – 2026-11-24
- Strecken-Editor: „Verbindung“ im Gerätedetail öffnet die ganze Strecke als Seitenleiste – Anfang und Ende mit LLDP/CDP-Abgleich, dazwischen Kabel und Stationen. Kabel lassen sich dort direkt bearbeiten (Label, Typ, Länge, Farbe, Messprotokoll, Notiz), lösen und neu verbinden. Auch im Soll/Ist-Abgleich über „Strecke“ erreichbar. Ersetzt den bisherigen Einzel-Dialog.
- Zwischenstation einfügen und entfernen: Patchfelder und Dosen lassen sich in ein bestehendes Kabel einfügen (aus einem vorläufigen Direktkabel wird die echte Strecke) oder wieder herausnehmen. Alles in einer Transaktion, die Verbindungs-Historie bleibt vollständig.
- „Strecke vollständig“: setzt das Kennzeichen „vorläufig“ an allen Kabeln der Strecke zurück.

## 0.4.1 – 2026-11-24
- Standort-Tag beim Anlegen in Checkmk: Neue Hosts bekommen das Tag `location` (z. B. LOC026) passend zum Standort des meldenden Geräts; im Dialog änderbar (Auswahl aus den Standortcodes); ob der Wert in Checkmk existiert, prüft Checkmk beim Anlegen. Der Automation-User braucht dafür kein Recht auf die Tag-Verwaltung.

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
