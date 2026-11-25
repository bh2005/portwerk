// Handbuch: Abschnitte mit Überschrift und HTML-Inhalt (Seite /handbuch).
export const sections = [
  { id: 'einstieg', title: 'Einstieg', html: `
<p>Portwerk verwaltet den Bestand für die Verkabelung: Standorte, Räume und Racks, Geräte mit Ports sowie Patchfelder und Dosen. Der Schwerpunkt liegt auf der <b>Planung</b>: Änderungen an der Verkabelung laufen später als Auftrag (planen → freigeben → ausführen → bestätigen).</p>
<p>In dieser Ausbaustufe stehen die Stammdaten und der Import zur Verfügung.</p>
<h3>Typischer Start</h3>
<ol><li>Unter <b>Standorte</b> Standorte, Gebäude, Räume und Racks anlegen – oder beim Import anlegen lassen.</li>
<li>Unter <b>Import</b> Geräte und Ports aus CSV, JSON oder Checkmk einlesen.</li>
<li>Unter <b>Racks</b> die Belegung prüfen, unter <b>Geräte</b> Details und Ports pflegen.</li></ol>` },

  { id: 'bedienung', title: 'Bedienung', html: `
<ul><li><b>Hilfe:</b> F1 oder ? öffnet die Hilfe zur aktuellen Seite. Das Fragezeichen-Symbol neben Feldern zeigt einen Kurztipp.</li>
<li><b>Dunkelmodus</b> und <b>Profil</b> (Passwort ändern) findest du unten in der Seitenleiste.</li>
<li>Die Seitenleiste lässt sich über das Menü-Symbol einklappen.</li></ul>` },

  { id: 'standorte', title: 'Standorte und Racks', html: `
<p>Die Struktur ist hierarchisch: <b>Standort → Gebäude → Etage → Raum → Rack</b>. Jede Ebene ist eine „Location“. Racks haben eine Höhe in Höheneinheiten (HE).</p>
<p>Standorte und Locations lassen sich nur löschen, wenn sie leer sind. Beim Import reicht ein Pfad wie <code>SITE-A/Gebäude 1/Raum 2/Rack 3</code>; fehlende Ebenen werden angelegt. Wird nur ein Standortcode angegeben, landet das Gerät in der Location „Allgemein“.</p>` },

  { id: 'geraete', title: 'Geräte und Ports', html: `
<p>Gerätetypen: Switch, Router, Firewall, Access Point, Server, Patchfeld, Dose, Endgerät, Sonstiges. Der Status ist <i>geplant</i>, <i>aktiv</i> oder <i>außer Betrieb</i>.</p>
<ul><li><b>HE-Position und Höhe</b> sind nur in einem Rack möglich. Überschneidungen und Überschreiten der Rackhöhe werden abgewiesen.</li>
<li><b>Ports</b> lassen sich einzeln oder gesammelt anlegen (Präfix, Start, Anzahl).</li>
<li><b>Patchfelder:</b> jeder Port kann mit einer Gegenseite verknüpft werden (Durchschleifung).</li>
<li><b>Pfad:</b> „Pfad“ in der Portzeile (bzw. „Ganzen Pfad anzeigen“ nach dem Scannen eines Etiketts) zeigt die komplette Strecke als Grafik – Switch, Patchfelder (vorn ◂ / hinten ▸), Dose, Endgerät – mit Kabelnummer, Art, Länge und Kabelfarbe, Ort und HE, geplanten Änderungen und Reservierungen. Offene Enden (z. B. Patchfeld ohne hinterlegte Gegenseite) werden markiert; an durchgängigen Strecken zeigt der LLDP/CDP-Abgleich, ob die Enden sich wirklich sehen.</li>
<li><b>Mobile Techniker-Ansicht</b> (<code>/m</code>, auf dem Handy auch über „Mobile Ansicht zum Abhaken“ im Auftrag oder den QR-Code der PDF-Arbeitsanweisung): freigegebene und laufende Aufträge, Positionen nach Ort mit Höheneinheit, große Knöpfe „Erledigt“/„Abweichung“, Starten und Fertigmelden. „Scannen“ (Android/Chrome, nur über HTTPS) springt zur Position mit der gescannten Kabelnummer; auf dem iPhone die Kamera-App nutzen – das Etikett öffnet die Kabelseite mit „Im Auftrag abhaken“.</li>
<li><b>Port-Reservierungen:</b> auf der Geräteseite Ports ankreuzen → „Reservieren“ (Zweck, optional Frist). Reservierte Ports und Ports, die ein anderer offener Auftrag schon verbinden will („verplant“), gelten in den Assistenten nicht als frei; wer sie trotzdem verwendet, bekommt eine Rückfrage – die Reservierung wird dabei freigegeben (Audit-Log). Eine Reservierung für einen bestimmten Auftrag gilt dort nicht als Konflikt und endet mit dessen Bestätigung. Übersicht unter <b>Reservierungen</b>.</li>
<li><b>Mein Profil</b> (Personensymbol unten in der Seitenleiste): E-Mail-Benachrichtigungen einzeln an/aus – Zuweisung, Statusänderung eigener Aufträge (freigegeben, abgelehnt, Nacharbeit, bestätigt), LLDP-Abweichung bei eigener Ausführung, Ablauf eigener Reservierungen (3 Tage vorher), zur Bestätigung vorgeschlagen (Freigeber). Außerdem Standard-Standort (belegt Filter vor), Startseite nach dem Login und „Alle anderen abmelden“ (z. B. nach Verlust eines Geräts). Unter <b>Abwesenheit und Vertretung</b> trägst du Zeiträume mit Vertretung ein: Dann gehen deine Benachrichtigungen an die Vertretung (sofern sie dafür berechtigt ist – bei Bestätigungsvorschlägen muss sie Freigeber am Standort sein), und sie sieht deine Aufträge unter „Meine Aufgaben“. Zuweisungen bleiben bei dir; Administratoren können Abwesenheiten auch für andere eintragen. Ist der Abgleich mit OpenPlan eingeschaltet, erscheinen dort eingetragene Abwesenheiten automatisch (Hinweis „aus OpenPlan“, nur dort änderbar); für sie gilt deine <b>Standard-Vertretung</b>. Alles gilt auf allen Geräten; den E-Mail-Versand insgesamt steuert die Verwaltung.</li>
<li><b>Geräte aus OpenPlan:</b> Geräte → „Aus OpenPlan …“ (wenn die OpenPlan-Anbindung aktiv ist). Projekt wählen: Portwerk listet die Geräte-Vorgänge des Rollouts und ordnet Standort (Location-Code oder Name), Ort (Rack aus „Rack / HE“, sonst Raum), Typ und Katalogmodell zu. Ausgewählte Geräte entstehen als <b>geplant</b> – mit Ports aus dem Katalogmodell und auf der HE, wenn sie frei ist; fehlt der Ort, wählst du ihn in der Liste. Ein vorhandenes Gerät gleichen Namens wird nur verknüpft. In OpenPlan erhält der Vorgang den Verweis „portwerk“ auf das Gerät; ein erneuter Abruf zeigt bereits Übernommenes an. Dürfen: Planer am Standort und Bereichs-Administratoren.</li>
<li><b>Arbeitsplatz-Assistent:</b> auf der Geräteseite einer Dose „Arbeitsplatz“ (oder Patchaufträge → „+ Arbeitsplatz“). Portwerk verfolgt die Strecke bis zum Patchfeld-Port, an dem das Patchkabel fehlt, schlägt einen freien Switchport vor (zuerst im selben Rack, dann in der Nähe, dann am Standort; nicht reservierte, nicht verplante Ports), übernimmt Profil/VLAN und legt daraus einen Patchauftrag an – optional mit dem Anschluss des Endgeräts. Ist die Dose schon bis zum Switch verbunden, entsteht nur „Port umkonfigurieren“.</li>
<li><b>VLAN / Portprofil:</b> nur Dokumentation – Portwerk konfiguriert keine Switches. Unter <b>VLANs &amp; Profile</b> den VLAN-Katalog (je Standort oder für alle) und Portprofile pflegen (z. B. „Büro-PC“: Access 10 + Voice 30, „Access Point“: Trunk). Am Port zeigt die Geräteseite die Konfiguration („VLAN“ in der Portzeile, mit Historie). Im Ablauf: Auftragsaktion <b>Port umkonfigurieren</b> oder bei „herstellen/umstecken“ eine Ziel-Konfiguration (gilt standardmäßig für das Switch-Ende); sie steht in Arbeitsanweisung, CSV und mobiler Ansicht und wird beim Bestätigen am Port dokumentiert.</li>
<li><b>VLAN-Soll/Ist (Checkmk):</b> Soll/Ist → Reiter „VLANs (Checkmk)“ vergleicht die dokumentierte VLAN-Konfiguration mit den VLANs aus dem Checkmk-Inventar. Checkmk liefert sie nur für Cisco und nur als Access-VLAN; Trunks und Voice-VLANs meldet es nicht (ein dokumentierter Trunk ohne Meldung gilt daher als „plausibel“). Gemeldete, aber nicht dokumentierte VLANs lassen sich mit „Ist übernehmen“ in die Doku eintragen – gut für die Erstbefüllung.</li>
<li><b>LLDP-Prüfung ausgeführter Aufträge:</b> Nach jedem Checkmk-Import (und mit „Jetzt prüfen“) vergleicht Portwerk jede abgehakte Position mit den LLDP/CDP-Nachbarn: Bei „herstellen“ wird die Strecke über Patchfelder bis zu den aktiven Geräten verfolgt – sieht ein Ende das andere? Bei „trennen“ darf der alte Nachbar nicht mehr gemeldet werden. Daten zählen erst, wenn sie nach dem Abhaken gemeldet wurden. Stimmt alles, steht der Auftrag als „zur Bestätigung vorgeschlagen“ auf der Übersicht (LLDP ✓ in der Liste), und die Freigeber bekommen einmal eine E-Mail (zentral abschaltbar unter Verwaltung → E-Mail, persönlich unter „Mein Profil“ → E-Mail-Benachrichtigungen); bestätigen bleibt beim Freigeber (Vier-Augen-Prinzip).</li>
<li><b>Zeitreise:</b> „Vergleich“ zeigt, was sich zwischen zwei Zeitpunkten an der Verkabelung geändert hat – neu, entfernt, umgesteckt (ein Port vorher mit A, nachher mit B), nur zwischenzeitlich gesteckt – jeweils mit wem bzw. welchem Auftrag. „Stand am“ listet alle Verbindungen zu einem Zeitpunkt. Im Pfad-Dialog zeigt „Stand am“ die Strecke von damals. Historisiert sind die Verbindungen; Orte und Patchfeld-Gegenseiten sind der heutige Stand.</li>
<li><b>Aufräumen:</b> sammelt Stellen, die nachgepflegt werden sollten: vorläufige Kabel aus dem Soll/Ist-Abgleich (im Strecken-Editor Dosen/Patchfelder nachtragen und „Strecke vollständig“ wählen), dokumentierte Verbindungen, die LLDP nicht sieht (mögliche tote Patchung; mit „fehlt seit“ ab dem ersten Import ohne die Verbindung und „zuletzt gesehen“, älteste zuerst), abgelaufene Reservierungen (gesammelt löschbar), offene Aufträge ohne Änderung seit X Tagen und geplante Geräte ohne Auftrag. Globale Administratoren bekommen montags eine Zusammenfassung per E-Mail (abbestellbar im Profil).</li>
<li><b>Kapazität:</b> freie, belegte, verplante (offene Aufträge) und reservierte Ports je Kategorie (Switchports, Patchfeld, Dosen, PDU) über die Orte zusammengezählt, dazu je Rack die freien Höheneinheiten und der größte zusammenhängende freie Block. Bereiche unter der Schwelle (Standard 10 % frei) erscheinen als Engpass – auch als Karte auf der Übersicht.</li>
<li><b>Arbeitsanweisung als PDF:</b> im Patchauftrag „Arbeitsanweisung (PDF)“, in der Patchliste „PDF“ – nach Ort gruppiert, mit Kästchen zum Abhaken, Feld für Abweichungen und Unterschrift sowie QR-Code zum Auftrag. Nicht freigegebene Aufträge tragen den Hinweis „nicht ausführen“. Beim Versand per E-Mail kann das PDF angehängt werden.</li>
<li><b>Kabeletiketten:</b> „Etiketten“ auf der Geräteseite bzw. „Kabeletiketten“ im Patchauftrag (auch vor der Bestätigung) – Formate für Band (12/19/24 mm) und A4-Bögen, wahlweise je Kabelende ein Etikett. Der QR-Code enthält die Kabelnummer: nach dem Scannen zeigt Portwerk, wo das Kabel steckt, ob es geplant ist und wo es früher steckte. Ohne Kabelnummer gibt es bei geplanten Positionen keinen QR-Code.</li>
<li><b>Verbindungs-Historie</b> (unten auf der Geräteseite): alle aktuellen und früheren Verbindungen mit Zeitraum, wer bzw. welcher Auftrag sie hergestellt und getrennt hat. Mit <b>Stand am</b> zeigt sie, was zu einem bestimmten Zeitpunkt steckte; <b>Historie</b> in der Portzeile filtert auf einen Port. Gelöschte Ports und Geräte bleiben mit ihrem damaligen Namen erhalten.</li></ul>` },

  { id: 'import', title: 'Import', html: `
<p>Der Import legt Geräte und Ports an und aktualisiert sie. Er ändert nie Verbindungen.</p>
<h3>Regeln</h3>
<ul><li><b>Wiedererkennung:</b> über Quell-ID, sonst über den Hostnamen (Groß-/Kleinschreibung egal). Wiederholte Importe erzeugen keine Dubletten.</li>
<li><b>Leere Felder</b> überschreiben vorhandene Werte nicht. <b>Fehlende Ports</b> werden nicht gelöscht.</li>
<li><b>Trockenlauf</b> zeigt das Ergebnis, ohne zu speichern. <b>Atomar</b> speichert bei einem Fehler nichts.</li></ul>
<h3>CSV</h3>
<p>Datei wählen, Spalten zuordnen (wird vorgeschlagen), Trockenlauf, Import. Geräte-Felder: hostname, type, vendor, model, serial, mgmt_ip, location, status, note, ext_id. Port-Felder: hostname, port, idx, medium, speed_mbps, description, admin_status, oper_status.</p>
<h3>JSON und API</h3>
<p>Das JSON-Format ist identisch zur API <code>POST /api/import/json</code>. Ein Beispiel fügt die Schaltfläche „Beispiel einfügen“ ein.</p>
<h3>Checkmk</h3>
<p>Das Skript <code>tools/checkmk_export.py</code> liest das HW/SW-Inventar und sendet es an <code>POST /api/import/checkmk</code>. Es braucht einen API-Zugang mit Schreibrecht. Ethernet-Schnittstellen werden zu Ports, ab 10 Gbit/s mit Medium SFP+. Loopbacks, VLAN-Schnittstellen und Tunnel werden nicht übernommen.</p>` },

  { id: 'verwaltung', title: 'Verwaltung', html: `
<h3>Rollen</h3>
<table><tr><th>Rolle</th><th>Darf</th></tr>
<tr><td>Administrator</td><td>alles, inkl. Import und Verwaltung</td></tr>
<tr><td>Planer</td><td>Stammdaten pflegen, Aufträge planen</td></tr>
<tr><td>Freigeber</td><td>Aufträge freigeben</td></tr>
<tr><td>Techniker</td><td>Aufträge ausführen</td></tr>
<tr><td>Betrachter</td><td>nur lesen</td></tr></table>
<p>Rollen sind kombinierbar. Der letzte aktive Administrator kann nicht entfernt werden.</p>
<h3>Vier-Augen-Prinzip</h3>
<p>Wer einen Auftrag angelegt oder eingereicht hat, darf ihn nicht selbst <b>freigeben</b>; wer ihn ausgeführt hat, darf ihn nicht selbst <b>bestätigen</b>. Ablehnen und Nacharbeit bleiben erlaubt. Administratoren können im Notfall mit <b>Begründung</b> übersteuern – die Ausnahme steht im Audit-Log und am Auftrag.</p>
<h3>Sicherung</h3>
<p>Verwaltung → <b>Sicherung</b>: „Jetzt sichern“ legt ein ZIP mit Datenbank und Server-Zertifikat an; täglich automatisch mit einstellbarer Uhrzeit und Aufbewahrung. Wiederherstellen (vom Server oder aus einer Datei) ersetzt den gesamten Bestand – vorher wird der aktuelle Stand gesichert, danach melden sich alle neu an. Sicherungen enthalten Passwort-Hashes und Zugangsdaten: vertraulich aufbewahren.</p>
<h3>API-Zugänge</h3>
<p>Tokens für Skripte (Präfix <code>opp_</code>). Umfang <i>read</i> oder <i>write</i>, optional mit Ablauf. Der Klartext wird nur einmal angezeigt; Übergabe im Header <code>Authorization: Bearer …</code> bzw. <code>X-Auth-Token</code>.</p>
<h3>Audit-Log</h3>
<p>Protokolliert Anmeldungen, Änderungen an Stammdaten, Importe sowie Benutzer- und Token-Verwaltung.</p>` },

  { id: 'assistenten', title: 'Assistenten und Logikprüfung', html: `
<p>Assistenten führen Schritt für Schritt durch häufige Aufgaben und zeigen vor dem Speichern eine Vorschau.</p>
<ul><li><b>Neuer Standort</b> (Standorte): Standort, Struktur aus Gebäude → Etage → Raum → Rack, Prüfung. Alles wird in einem Schritt gespeichert.</li>
<li><b>Gerät platzieren</b> (Geräte, Racks): Modell aus dem Katalog, Standort und HE-Position, Hostname und Daten, optional ein Kabel (z. B. Uplink), Umsetzung. Platzhalter (Kabelführung, Blindblende, Fachboden) laufen über denselben Assistenten, der Hostname ist dort optional.</li>
<li><b>Massenverkabelung</b> (Geräte → „Assistent: Massenverkabelung“): viele Kabel auf einmal. <i>Patchfeld ↔ Patchfeld</i> verbindet alle Ports (z. B. Rückseite RZ ↔ Rückseite Etage 1); <i>Datendosen → Patchfeld/Switch</i> patcht alle Dosen einer Location der Reihe nach; <i>Aus Liste</i> liest eine Excel/CSV-Zuordnung (Gerät A; Port A; Gerät B; Port B; Kabelnummer). Die Zuordnung lässt sich vorab prüfen, versetzen und zeilenweise auslassen; Kabelnummern entstehen aus einem Muster. Ergebnis: <b>ein Patchauftrag mit Arbeitsliste</b> (oder alles sofort, atomar). Belegte Ports lösen eine einzige Rückfrage zum Rückbau aus.</li>
<li><b>Schnellsuche:</b> <b>Strg+K</b> oder <b>/</b> (oder das Feld in der Seitenleiste) öffnet die Suche über Geräte (Hostname, IP, Seriennummer, Modell), Standorte, Orte, WAN-Verbindungen, Patchaufträge und Kabelnummern. Bei Geräten stehen Standort, Raum/Rack und Höheneinheit direkt im Treffer; Enter öffnet die Rack-Ansicht mit markiertem Gerät.</li>
<li><b>OpenPlan-Anbindung:</b> Patchaufträge werden zu Aufgaben im OpenPlan-Projektplan (Verwaltung → OpenPlan). Status und Fortschritt gleichen sich automatisch ab; mehrere Aufträge lassen sich auf einmal übertragen oder in ein neues Projekt aus der Vorlage „Einbau Patchfelder / Verkabelung“ einhängen.</li>
<li><b>Patchliste aus mehreren Aufträgen:</b> In „Patchaufträge“ Aufträge ankreuzen → „Patchliste aus Auswahl“: eine gemeinsame, nach Ort sortierte Arbeitsliste zum Abhaken, Exportieren und Drucken.</li>
<li><b>Kabel einbauen</b> (Geräte, Geräteansicht, Racks → freier Port „verbinden …“): Kabelart aus dem Katalog (Daten, Glasfaser, <b>Strom</b>, <b>Koax RG58</b> für NTP/DCF, seriell, Telefon), Ende A und B, Details, Umsetzung. Passt das Port-Medium nicht zur Kabelart, gibt es einen Hinweis; belegte Ports lösen die Rückfrage zum Rückbau aus.</li>
<li><b>Wandgehäuse, Schaltschränke, Maschinen und Lader:</b> Neben Racks gibt es Wandgehäuse und Schaltschränke (mit oder ohne HE), Anlagen/Maschinen und mobile Maschinen. Geräte darin werden auf <i>Hutschiene/Montageplatte</i> montiert (ohne HE-Raster, keine Kollision) oder – in Gehäusen mit HE – auf 19-Zoll-Plätzen. Typische Industrie-Typen (SPS, HMI, I/O-Modul, Antrieb, Gateway, Netzteil) und Vorlagen für die Hutschiene sind im Katalog.</li>
<li><b>Einbaulage:</b> Jedes Gerät hat eine Einbauseite (vorne, hinten, durchgehend) und eine Ausrichtung: <i>19 Zoll</i> belegt HE, <i>hochkant</i> sitzt im Seitenkanal links oder rechts (PDU, senkrechte Kabelführung) und belegt keine HE. Die Kollisionsprüfung berücksichtigt Seite und Kanal.</li>
<li><b>Patchfeld platzieren</b> (Geräte, Racks): Vorlage (Cat6A/LWL, 8/12/24 Ports, vorn und hinten verknüpft), Ort, Name und <b>Port-Zuordnung</b>: z. B. Vorderseite P1–P12 fortlaufend an Switch-Port 1–12, Kabelnummern aus einem Muster (<code>{hostname}-{nn}</code>). Mehrere Zuordnungen möglich, belegte Zielports lösen die Rückfrage zum Rückbau aus.</li>
<li><b>Umsetzung wahlweise:</b> „sofort“ schreibt direkt in den Bestand (Administratoren), „per Patchauftrag“ legt das Gerät als <i>geplant</i> an und macht Einbau und Kabel zu Positionen eines Auftrags.</li></ul>
<h3>Logikprüfung</h3>
<ul><li><b>Port belegt:</b> Der Assistent fragt, ob der alte Patch zurückgebaut werden soll. Bei „Ja“ entsteht automatisch ein <b>Rückbau-Patchauftrag</b>; der neue Auftrag startet erst, wenn dieser bestätigt ist. Im Modus „sofort“ wird der alte Patch direkt entfernt.</li>
<li><b>HE belegt:</b> Gleiche Rückfrage für das alte Gerät. Ausgebaute Geräte bleiben als „außer Betrieb“ in der Historie.</li>
<li>Hostnamen müssen eindeutig sein; Gerät und Rackhöhe werden wie beim normalen Anlegen geprüft.</li></ul>
<h3>Rechte pro Standort</h3>
<p>Benutzer können Rollen nur für einzelne Standorte erhalten und sehen dann nur diese. Bereichs-Administratoren verwalten ihren Standort samt Benutzern. Siehe Verwaltung → Benutzer.</p>` },

  { id: 'ausblick', title: 'Ausblick', html: `
<ul><li>Verbindungen und Patchaufträge mit Freigabe und Verlauf</li>
<li>Schnittstelle zu OpenPlan (Aufgaben für die Ausführung)</li>
<li>Soll/Ist-Abgleich über LLDP</li>
<li>Durchgängige Pfadansicht über Patchfelder und Dosen</li></ul>` },
]
