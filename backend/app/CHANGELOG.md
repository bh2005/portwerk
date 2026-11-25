# Änderungen

Format: `## <Version> – <Datum>`, darunter je Änderung eine Zeile `- Titel: Beschreibung`. Neueste Version zuerst. Wird in der Verwaltung unter „Releases“ angezeigt.

## 0.18.0 – 2026-11-25
- Englisch (Etappe 4, Analyse): Soll/Ist-Abgleich (Verkabelung und VLANs, „In Bestand übernehmen“, Checkmk-Anlage und -Aktivierung), Kapazität, Zeitreise, Aufräumen, VLANs & Portprofile, WAN und Katalog sind übersetzt, dazu rund 40 Server-Meldungen (Checkmk, Katalog, Zeitreise) und die Kapazitätskategorien. Auswahl- und Reiterbeschriftungen aus Listen erscheinen jetzt überall in der eingestellten Sprache.

## 0.17.0 – 2026-11-25
- Englisch (Etappe 3, Patchaufträge): Auftragsliste und -detail (Freigabe-Ablauf, Zuweisung, LLDP-Prüfung, OpenPlan), mobile Techniker-Ansicht mit Scanner, Patchliste, Kabeletiketten, Kabel-Scanseite, Reservierungen, Kabel-, Massenverkabelungs-, Arbeitsplatz- und Autorouting-Assistent sowie Versand- und OpenPlan-Dialoge sind übersetzt, dazu rund 120 Server-Meldungen und die LLDP-Prüftexte. Rückfragen bei belegten, reservierten oder verplanten Ports erscheinen auf Englisch, auch wenn sie mehrere Ports nennen. Vom Server gelieferte Beschriftungen (Auftragsstatus, Aktionen, Entfernungen) werden übersetzt. Zusätzlich übersetzt: Texte in Ausdrücken der Vorlagen (z. B. „Prüfe …“/„Jetzt prüfen“) in allen Ansichten.

## 0.16.0 – 2026-11-25
- Englisch (Etappe 2, Bestand): Standorte mit Struktur-Assistent, Geräte, Gerätedetail (Ports, Reservierung, VLAN, Verbindungs-Historie), Racks & Schränke, Geräte-Assistent, Port-Zuordnung, Strecken-Editor, Pfadgrafik und „Geräte aus OpenPlan“ sind übersetzt, ebenso rund 100 Server-Meldungen aus diesen Bereichen. Auswahllisten für Gerätetyp, Status, Ortsart, Quelle und Rolle erscheinen jetzt überall in der eingestellten Sprache.

## 0.15.0 – 2026-11-25
- Englisch (Etappe 1): Die Oberfläche lässt sich auf Englisch umstellen – im Profil unter „Persönliche Einstellungen → Sprache“ (gilt auf allen Geräten) oder vor der Anmeldung mit „English“ auf der Anmeldeseite. Übersetzt sind bisher Navigation, Anmeldung, Profil mit Abwesenheiten, Übersicht, Schnellsuche, Hinweise und Dialoge sowie die Gerätetypen, Status, Orte und Rollen in allen Ansichten; Fehlermeldungen des Servers zu Anmeldung, Rechten, Benutzern und Abwesenheiten erscheinen ebenfalls auf Englisch. Die übrigen Ansichten, das Handbuch, Mails und PDFs folgen in weiteren Etappen und bleiben bis dahin deutsch.

## 0.14.2 – 2026-11-25
- Untertitel „Portwerk – so isses.“: in der Seitenleiste, auf der Anmeldeseite (darunter weiter „Patchplanung“) und im Browser-Tab. Der hessische Spruch passt zum Soll/Ist-Abgleich: Portwerk zeigt, wie es wirklich *is*.

## 0.14.1 – 2026-11-25
- Light Mode in Graustufen: Statt reinem Weiß sind Karten, Tabellen und Dialoge hellgrau, der Seitenhintergrund und die Eingabefelder etwas dunkler – augenfreundlicher. Der Dark Mode und der Druck (Etiketten, Arbeitsanweisung) bleiben unverändert.

## 0.14.0 – 2026-11-25
- Änderungen anderer bemerken: Portwerk merkt sich bei jeder erfolgreichen Änderung (Anlegen, Ändern, Löschen, Import, API-Zugang), wer sie gemacht hat. Die Oberfläche fragt alle 20 Sekunden (nur bei sichtbarem Tab) ab, ob **andere** seit dem Laden etwas geändert haben. Dann erscheint oben der Hinweis „… hat Daten geändert“ mit „Neu laden“ und „Ausblenden“ – nichts wird still überschrieben, offene Formulare bleiben unberührt. Die Übersicht lädt bei fremden Änderungen von selbst nach. Eigene Änderungen lösen keinen Hinweis aus; Änderungen durch einen API-Zugang (z. B. der Checkmk-Import) zählen als fremd. Neu: GET /api/live.

## 0.13.0 – 2026-11-25
- „Nicht gesehen seit …“: Bei jedem Import der LLDP/CDP-Nachbarn merkt sich Portwerk je dokumentierter Verbindung, wann sie zuletzt bestätigt wurde und seit wann sie fehlt. Der Soll/Ist-Abgleich zeigt bei „nicht gesehen“ das Datum, der Aufräumbericht „fehlt seit X Tagen“ und „zuletzt gesehen“ (älteste zuerst, ab der gewählten Schwelle hervorgehoben). Die Wochenmail nennt, wie viele Verbindungen länger fehlen. Ändert sich das dokumentierte Gegenüber, beginnt die Zählung neu. Die Aufzeichnung beginnt mit dem ersten Import nach dem Update.

## 0.12.0 – 2026-11-24
- Geräte aus OpenPlan: Geräte → „Aus OpenPlan …“ listet die Geräte-Vorgänge eines OpenPlan-Projekts (Geräte-Rollout) und ordnet Standort, Ort (Rack/HE, sonst Raum), Typ und Katalogmodell zu. Ausgewählte Geräte werden als „geplant“ angelegt (mit Ports aus dem Katalogmodell, auf der HE, wenn frei); vorhandene Geräte gleichen Namens werden verknüpft. OpenPlan bekommt am Vorgang den Verweis „portwerk“ mit Link auf das Gerät. Erlaubt für Planer am Standort und Bereichs-Administratoren.

## 0.11.0 – 2026-11-24
- Abwesenheiten aus OpenPlan: Ist der Abgleich eingeschaltet (Verwaltung → OpenPlan), übernimmt Portwerk stündlich die persönlichen Abwesenheiten aus OpenPlan für ein Jahr im Voraus. Die Zuordnung läuft über den Benutzernamen, sonst über die E-Mail-Adresse. Übernommene Einträge sind in Portwerk nur lesbar; „krank“ erscheint nur als „abwesend“. Voraussetzung: OpenPlan ab 0.15.0, API-Zugang mit Freigabe „Abwesenheiten“.
- Standard-Vertretung im Profil: Sie gilt für Abwesenheiten aus OpenPlan und wird beim Eintragen einer Abwesenheit vorgeschlagen. Administratoren können sie auch für andere setzen.

## 0.10.0 – 2026-11-24
- Aufräumen: Neue Seite sammelt Stellen, die nachgepflegt werden sollten – vorläufige Kabel aus dem Soll/Ist-Abgleich (mit Alter, Absprung in den Strecken-Editor), dokumentierte Verbindungen, die LLDP nicht sieht (mögliche tote Patchung), abgelaufene Reservierungen (gesammelt löschbar), offene Aufträge ohne Änderung seit X Tagen und geplante Geräte ohne Auftrag. Filter nach Standort, Schwelle für „alt“ wählbar.
- Wöchentlicher Aufräumbericht: Montags eine Zusammenfassung per E-Mail an die globalen Administratoren (nur wenn es offene Punkte gibt; abbestellbar im Profil, „Bericht mailen“ sendet sofort).

## 0.9.0 – 2026-11-24
- Autorouting: Von einem Quellport (z. B. NIC eines neuen Servers) zu einem Zielport (z. B. Switchport) schlägt Portwerk die fehlenden Patchungen vor – über vorhandene Kabel, Patchfelder und Dosen (bis zu 3 Stationen), neue Patchkabel nur zwischen freien Ports im selben Raum (im selben Rack bevorzugt). Bis zu drei Vorschläge; daraus entsteht ein Patchauftrag, die Ports sind verplant.
- Neues Gerät wird bei Bedarf mit angelegt: Als „geplant“ samt Einbau-Position im Auftrag; es gilt nach der Bestätigung als eingebaut. Aufruf in der Rack-Ansicht („Autorouting“) und am Port im Gerätedetail.

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
