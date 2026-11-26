// Kontexthilfe pro Seite (F1 / ?). Schlüssel: Route, optional mit "#tab" für Seiten mit Reitern.
// Englische Fassung in helpTexts.en.js (gleiche Schlüssel); fehlt dort ein Eintrag, erscheint der deutsche Text.
import { lang } from '../i18n.js'
import { T_EN, DEFAULT_EN } from './helpTexts.en.js'

const T = {
  '/dashboard': `<h2>Übersicht</h2>
<p>Hier siehst du auf einen Blick, was im Bestand liegt: Standorte, Racks, Geräte und Ports.</p>
<ul><li><b>Geräte ohne Location</b> sind noch keinem Raum oder Rack zugeordnet – sie fehlen in der Rack-Ansicht.</li>
<li><b>Letzte Importe</b> zeigt, ob ein Import angewendet oder nur als Trockenlauf geprüft wurde.</li></ul>
<p class="help-tip">Neu hier? Lege zuerst Standorte an und importiere dann Geräte (Import).</p>`,

  '/sites': `<h2>Standorte</h2>
<p>Die Ortsstruktur ist hierarchisch: <b>Standort → Gebäude → Etage → Raum → Anlage/Maschine → Rack / Wandgehäuse / Schaltschrank</b>. Jede Ebene darf fehlen.</p>
<ul><li><b>Racks, Wandgehäuse und Schaltschränke</b> nehmen Geräte auf und haben optional eine HE-Teilung. Ein Schaltschrank ohne HE ist für Hutschienen-Geräte gedacht.</li>
<li><b>Anlage/Maschine</b> steht fest (z. B. Presse, Förderband) und kann Schaltschränke enthalten. Geräte können auch direkt in der Maschine liegen.</li>
<li><b>Mobile Maschine</b> (z. B. Lader) liegt am Standort und lässt sich mit „Verlegen“ samt Schaltkasten und Geräten an einen anderen Standort bringen. Die Änderung steht im Audit-Log.</li></ul>
<ul><li>Wähle links einen Standort, rechts erscheint seine Struktur.</li>
<li>Ein <b>Rack</b> braucht die Anzahl Höheneinheiten (HE), damit die Rack-Ansicht sie darstellen kann.</li>
<li>Standorte oder Locations mit Geräten lassen sich nicht löschen.</li></ul>
<p><b>Assistent: Neuer Standort</b> führt in drei Schritten durch Standort, Struktur und Prüfung. „Mehrere …“ legt z. B. 10 Racks mit Namensmuster <code>Rack {n}</code> auf einmal an. Mit „Struktur-Assistent“ ergänzt du einen vorhandenen Standort.</p>
<p class="help-tip">Beim Import genügt ein Pfad wie <code>SITE-A/Gebäude 1/Raum 2/Rack 3</code> – fehlende Ebenen werden angelegt.</p>`,

  '/admin#ldap': `<h2>AD / LDAP</h2>
<p>Hier schaltest du die <b>Anmeldung über Active Directory</b> ein. Standard ist <b>aus</b>; lokale Konten bleiben immer als Notzugang erhalten.</p>
<ul><li><b>Server</b>: ldaps:// bevorzugen; mehrere Server dienen der Ausfallsicherung.</li>
<li><b>Anmeldung prüfen</b>: entweder direkt als <code>benutzer@domain</code> (Domain eintragen) oder über einen Service-Account mit Benutzerfilter.</li>
<li><b>Rollen</b>: je Rolle eine AD-Gruppe (DN). Die Rollen werden bei jeder Anmeldung neu aus den Gruppen berechnet. Ohne passende Gruppe gilt die „Rolle ohne passende Gruppe“ – leer heißt: kein Zugang.</li>
<li><b>Verbindung testen</b> zeigt Schritt für Schritt, was klappt, und listet die Gruppen des Test-Benutzers – die DNs kannst du direkt übernehmen.</li></ul>
<p class="help-tip">Passwörter von AD-Benutzern werden nie gespeichert und nur im Verzeichnis geändert.</p>`,

  '/admin#mail': `<h2>E-Mail</h2>
<p>SMTP-Zugang für den Versand von Aufträgen und Patchlisten sowie Zuweisungs-Benachrichtigungen. Standard ist <b>aus</b>.</p>
<ul><li><b>Erlaubte Domains</b> begrenzen die Empfänger – empfohlen, damit keine Auftragsdaten an fremde Adressen gehen.</li>
<li>Die <b>öffentliche URL</b> erzeugt die Links in den Mails.</li>
<li>Mit „Testnachricht“ prüfst du die gespeicherten Einstellungen. Jeder Versand steht im Audit-Log.</li></ul>`,

  '/admin#openplan': `<h2>OpenPlan</h2>
<p>Anbindung an die Projektplanung OpenPlan (Standard: <b>aus</b>). Dafür in OpenPlan ein Dienstkonto mit API-Token anlegen (Umfang write, Rolle Bearbeiter) und es im Projekt als Mitglied eintragen.</p>
<ul><li><b>Verbindung testen</b> zeigt das Dienstkonto und die sichtbaren Projekte.</li>
<li><b>Automatisch abgleichen:</b> Jede Statusänderung und jedes Abhaken meldet Status und Fortschritt an die verknüpfte Aufgabe. Ein Ausfall von OpenPlan stört den Patchauftrag nie; „Jetzt abgleichen“ holt es nach.</li>
<li><b>Webhook (optional):</b> OpenPlan meldet Änderungen an der Aufgabe zurück; der Status erscheint am Auftrag. Geheimnis und Adresse stehen auf dieser Seite.</li>
<li><b>Abwesenheiten (optional):</b> übernimmt stündlich die persönlichen Abwesenheiten aus OpenPlan; für sie gilt die Standard-Vertretung aus dem Profil. Der API-Zugang in OpenPlan braucht die Freigabe „Abwesenheiten“.</li></ul>`,

  '/admin#tls': `<h2>Zertifikat (ACME)</h2>
<p>Die App fordert ihr Server-Zertifikat selbst von einer ACME-CA an (z. B. interne step-ca) und erneuert es automatisch.</p>
<ul><li>Trage <b>Directory-URL</b> und <b>Domains</b> ein (Empfehlung: Kurzname, FQDN und IP). Die CA prüft per HTTP-01 – Port 80 muss zur App weitergeleitet werden.</li>
<li>Nutzt die CA eine <b>eigene PKI</b>, die CA-Kette (Root + Intermediate) hinterlegen oder per URL laden und die Fingerabdrücke prüfen.</li>
<li>Der <b>HTTPS-Listener</b> startet, sobald <code>TLS_PORT</code> gesetzt ist; ein erneuertes Zertifikat wird ohne Neustart übernommen.</li></ul>`,

  '/compare': `<h2>Soll/Ist-Abgleich</h2>
<p>Vergleicht die dokumentierte Verkabelung (<b>Soll</b>, auch über Patchfelder und Dosen hinweg) mit den per LLDP/CDP gemeldeten Nachbarn (<b>Ist</b>).</p>
<ul><li><b>stimmt</b> · <b>anderer Port</b> (richtiges Gerät, falscher Port) · <b>anderes Gerät</b> · <b>nicht gesehen</b> (dokumentiert, aber kein Nachbar gemeldet) · <b>nicht dokumentiert</b> (Nachbar gesehen, kein Kabel erfasst).</li>
<li>Bei „nicht gesehen“ steht, seit wann die Verbindung fehlt (ab dem ersten Import ohne sie).</li>
<li>Die Nachbardaten kommen mit dem Checkmk-Import; jeder Import ersetzt die Daten der enthaltenen Geräte. Reine MAC-Adressen (Telefone, Kameras) werden ignoriert.</li>
<li><b>Verbindung übernehmen</b> dokumentiert eine gesehene, aber nicht erfasste Verbindung als vorläufiges Direktkabel; <b>In Bestand übernehmen</b> legt ein unbekanntes Nachbargerät an.</li>
<li>Die Chips filtern; CSV-Export für Berichte.</li></ul>`,

  '/wan': `<h2>WAN-Verbindungen</h2>
<p>Das Leitungsverzeichnis: Verbindungen zwischen Standorten oder ins Internet mit Provider, Leitungs-ID, Technik, Bandbreite und Vertrag.</p>
<ul><li><b>Gegenstelle:</b> ein eigener Standort oder Freitext (z. B. Internet). <b>Ports</b> an Router/Firewall sind optional; ein Port gehört höchstens einer aktiven Verbindung.</li>
<li><b>Änderungen laufen als Auftrag:</b> „In Betrieb nehmen“, „Ändern per Auftrag“ und „Kündigen“ legen einen Patchauftrag an. Der Status bzw. die neuen Werte gelten erst, wenn der Auftrag bestätigt ist.</li>
<li><b>Direkt bearbeiten</b> (Administratoren): zum Erfassen vorhandener Leitungen.</li>
<li>Der Filter „Vertrag läuft in 90 Tagen aus“ zeigt Kündigungs- und Verlängerungstermine; CSV-Export für Auswertungen.</li>
<li>Laufen <b>SIP-Trunks</b> über die Leitung, stehen sie in den Details – beim Kündigen oder Ändern ist dann die Telefonie betroffen.</li>
<li>Sichtbar nur mit Freigabe „WAN“ (Verwaltung → Benutzer → Zusätzliche Bereiche); Administratoren sehen den Bereich immer.</li></ul>`,

  '/telephony': `<h2>Telefonie: SIP-Trunks</h2>
<p>Verzeichnis der SIP-Trunks: Provider, Trunk-Kennung, Registrar, Anbindung (Registrierung oder statisch/IP-Peering), Kanäle, Rufnummernblöcke und Vertrag.</p>
<ul><li><b>SBC:</b> das Gerät, an dem der Trunk ankommt (Typ SBC, Sprach-Gateway, Gateway, Router oder Firewall) – am selben Standort. <b>TK-Anlage:</b> Gerät vom Typ TK-Anlage, z. B. die HiPath. <b>WAN-Leitung:</b> eine Leitung dieses Standorts.</li>
<li><b>Änderungen laufen als Auftrag:</b> „In Betrieb nehmen“, „Ändern per Auftrag“ und „Kündigen“ legen einen Patchauftrag an; Status und neue Werte gelten erst nach der Bestätigung.</li>
<li><b>Direkt bearbeiten</b> (Administratoren): zum Erfassen vorhandener Trunks. Rufnummern je Zeile ein Block, z. B. <code>+49 6181 1234-0…99</code>; die Suche findet auch einzelne Rufnummern.</li>
<li><b>Rufnummernplan</b> (zweiter Reiter): Blöcke mit Präfix und Durchwahlbereich; je Durchwahl frei, reserviert (mit Frist) oder vergeben an Person, Funktion, Sammelruf, Fax oder Sonderanschluss, optional mit Endgerät. „Nächste freie vergeben …“ nimmt die erste freie Durchwahl. Vergeben dürfen Planer und Administratoren des Standorts; Blöcke legen Administratoren an.</li>
<li>Sichtbar nur mit Freigabe „Telefonie“ (Verwaltung → Benutzer → Zusätzliche Bereiche); Administratoren sehen den Bereich immer.</li></ul>`,

  '/workorders': `<h2>Patchaufträge</h2>
<p>Änderungen an Verkabelung und Geräten laufen als Auftrag: <b>Entwurf → Einreichen → Freigeben → Ausführen → Bestätigen</b>. Erst die Bestätigung ändert den Bestand.</p>
<ul><li>Positionen: Verbindung herstellen, trennen, umstecken sowie <b>Gerät einbauen</b> und <b>Gerät zurückbauen</b>; für WAN-Verbindungen <b>in Betrieb nehmen</b>, <b>ändern</b> und <b>kündigen</b>; <b>Port umkonfigurieren</b> für VLAN/Profil.</li>
<li><b>Belegter Port:</b> Wird ein neuer Patch auf einen belegten Port geplant, fragt die Oberfläche „Alten Patch zurückbauen?“. Bei <b>Ja</b> entsteht automatisch ein <b>Rückbau-Auftrag</b>; der neue Auftrag kann erst starten, wenn der Rückbau bestätigt ist.</li>
<li>Gleiches gilt für <b>belegte Höheneinheiten</b>: Das alte Gerät wird per Rückbau-Auftrag ausgebaut (Kabel getrennt, Status „außer Betrieb“, HE frei).</li>
<li><b>Arbeitsliste:</b> Große Aufträge (z. B. aus der Massenverkabelung) sind eine Liste mit einer Position je Kabel. Fortschritt, Filter und <b>Mehrfachauswahl</b> („Auswahl abhaken“, „Abweichung …“, „Zurücksetzen“) erleichtern die Ausführung; „Arbeitsliste (CSV)“ öffnet sich direkt in Excel.</li>
<li><b>Patchliste aus mehreren Aufträgen:</b> In der Auftragsliste Aufträge ankreuzen und „Patchliste aus Auswahl“ wählen. Die gemeinsame Liste ist nach Ort (Rack/Raum) sortiert – so arbeitet man einen Raum nach dem anderen ab – oder nach Auftrag. Abhaken, CSV-Export und Drucken (mit Kästchen zum Abhaken auf Papier) sind möglich.</li>
<li><b>OpenPlan:</b> Ist die Anbindung eingerichtet, verbindest du einen Auftrag mit einer Aufgabe im OpenPlan-Projektplan (neu anlegen oder vorhandene wählen). Status und Fortschritt wandern automatisch dorthin, in OpenPlan steht die Referenz <code>portwerk: PA-…</code> mit Link zurück. In der Auftragsliste überträgt „In OpenPlan …“ mehrere Aufträge auf einmal oder legt ein <b>neues Projekt aus der Vorlage „Einbau Patchfelder / Verkabelung“</b> an.</li>
<li><b>Senden …</b> schickt den Auftrag (oder eine Patchliste) per E-Mail an Benutzer und/oder beliebige Adressen – mit Link, Positionsliste und der Arbeitsliste als CSV-Anhang. Benutzer werden nur angeboten, wenn sie den Auftrag sehen dürfen.</li>
<li><b>Zuweisen …</b> macht einen Benutzer verantwortlich; der Auftrag erscheint bei ihm auf der Übersicht unter „Meine Aufgaben“ (Filter „Mir zugewiesen“ in der Liste). Auf Wunsch kommt eine E-Mail.</li>
<li>Mit Rechten nur für einen Standort siehst du nur die Aufträge deines Standorts.</li></ul>`,

  '/catalog': `<h2>Katalog</h2>
<p>Hier pflegst du, <b>was eingebaut werden darf</b>: Gerätemodelle und Kabelarten.</p>
<ul><li><b>Gerätemodelle</b> sind Vorlagen mit Hersteller, Typ, Höhe und Port-Layout (z. B. 48× RJ45 + 4× SFP+). Die Assistenten erzeugen daraus Ports automatisch.</li>
<li>Für <b>Patchfelder</b> die Portgruppe auf „dual“ stellen: je Port entstehen Vorder- und Rückseite, bereits verknüpft.</li>
<li>Auch Zubehör ohne Ports (USV, Funkuhr, PDU) gehört in den Katalog.</li></ul>
<p class="help-tip">Ein Modell, das schon von Geräten verwendet wird, lässt sich nur deaktivieren, nicht löschen.</p>`,

  '/catalog#models': `<h2>Gerätemodelle</h2>
<p>Vorlagen für Switches, Patchfelder, Zeitserver, PDUs und mehr. Das Port-Layout besteht aus <b>Portgruppen</b>: Präfix (z. B. <code>Gi1/0/</code>), Startnummer, Anzahl und Medium.</p>
<ul><li>Deaktivierte Modelle erscheinen nicht mehr in den Assistenten, bestehende Geräte behalten die Verknüpfung.</li></ul>`,

  '/catalog#cables': `<h2>Kabelarten</h2>
<p>Neben Cat- und LWL-Kabeln sind <b>Strom</b>, <b>Koax (RG58 für NTP/DCF)</b>, <b>seriell/Signal</b> und <b>Telefon-Kupfer</b> mitgeliefert. Eigene Arten legst du frei an.</p>
<ul><li>Das <b>Zählfeld</b> (Fasern, Adern oder Paare) erscheint beim Erfassen eines Kabels dieser Art.</li>
<li>Der <b>Name</b> lässt sich nicht ändern, weil bestehende Kabel darauf verweisen. Nicht mehr benötigte Arten werden deaktiviert.</li>
<li>Nur Administratoren pflegen Kabelarten.</li></ul>`,

  '/devices': `<h2>Geräte</h2>
<p>Alle Geräte mit Ports: Switches, Router, Firewalls, Access Points, Server, Patchfelder und Dosen.</p>
<ul><li>Filter nach Suchtext, Typ, Status, Quelle und Standort sind kombinierbar.</li>
<li><b>Quelle</b> zeigt, woher das Gerät kommt (manuell, CSV, Checkmk, OpenPlan …).</li>
<li>Klick auf einen Hostnamen öffnet Details und Ports.</li>
<li><b>Aus OpenPlan …</b> übernimmt Geräte aus einem Geräte-Rollout in OpenPlan als „geplant“ (wenn die Anbindung aktiv ist).</li></ul>`,

  '/racks': `<h2>Racks</h2>
<p>Schrankansicht mit Höheneinheiten (HE). Die HE 1 ist unten.</p>
<ul><li>Geräte mit HE-Position werden an ihrer Stelle gezeigt, mehrhöhige Geräte über mehrere HE.</li>
<li>Geräte im Rack ohne HE-Position stehen darunter in der Liste „Ohne Position“.</li>
<li><b>Klick auf ein Gerät</b> öffnet rechts die <b>Portbelegung</b>: je Port, womit er verbunden ist (Gerät:Port, Kabelnummer, Kabelart) oder „frei“. Mit dem Filter siehst du nur belegte oder freie Ports.</li>
<li><b>Klick auf einen freien Platz</b> fragt, ob dort ein neues Gerät platziert werden soll – der Assistent startet mit Rack und HE vorbelegt. Auch Platzhalter (Kabelführung, Blindblende, Fachboden) lassen sich so einplanen.</li>
<li>Graue Balken sind Platzhalter, orange Geräte sind nur „geplant“, rote Balken PDUs.</li>
<li><b>Vorderseite / Rückseite:</b> Oben rechts schaltest du die Ansicht um. Geräte sind <i>vorne</i>, <i>hinten</i> oder <i>durchgehend</i> (beide Seiten) montiert – ein Gerät nur vorne und eines nur hinten dürfen sich dieselbe HE teilen.</li>
<li><b>Hochkant-Geräte</b> (z. B. PDU, senkrechte Kabelführung) sitzen in den schmalen <b>Seitenkanälen links und rechts</b> und belegen keine 19-Zoll-HE. Ein Klick in den Kanal platziert eines; links/rechts gelten aus Sicht der gerade gezeigten Ansicht.</li></ul>
<p class="help-tip">Ist die gewählte HE belegt, fragt der Assistent, ob das alte Gerät zurückgebaut werden soll. Per Patchauftrag wird dafür automatisch ein Rückbau-Auftrag angelegt.</p>`,

  '/import': `<h2>Import</h2>
<p>Geräte und Ports lassen sich aus CSV, JSON oder Checkmk einlesen. Der Import ändert nur Geräte und Ports, nie Verbindungen.</p>
<ul><li><b>Trockenlauf</b> berechnet alles und zeigt das Ergebnis, ohne zu speichern.</li>
<li><b>Atomar</b>: bei einem Fehler wird nichts gespeichert.</li>
<li>Wiederholte Importe sind sicher: Geräte werden über Hostname oder Quell-ID wiedererkannt. Leere Felder überschreiben nichts, fehlende Ports werden nicht gelöscht.</li></ul>`,
  '/import#csv': `<h2>CSV-Import</h2>
<p>Datei wählen, Spalten zuordnen, Trockenlauf prüfen, dann importieren. Die Zuordnung wird vorgeschlagen; passe sie bei Bedarf an.</p>
<ul><li><b>Geräte</b>: Pflichtfeld Hostname.</li><li><b>Ports</b>: Pflichtfelder Hostname und Port.</li></ul>`,
  '/import#json': `<h2>JSON-Import</h2>
<p>Dasselbe Format nutzt die API (<code>POST /api/import/json</code>) für Skripte. Ein Beispiel steht unter dem Eingabefeld.</p>`,
  '/import#checkmk': `<h2>Checkmk-Import</h2>
<p>Das Skript <code>tools/checkmk_export.py</code> liest das HW/SW-Inventar aus Checkmk und sendet es an die API. Dafür brauchst du einen API-Zugang mit Schreibrecht (Verwaltung → API-Zugänge).</p>`,

  '/admin': `<h2>Verwaltung</h2>
<p>Benutzer, API-Zugänge und Audit-Log. Nur für Administratoren.</p>`,
  '/admin#users': `<h2>Benutzer und Rechte</h2>
<ul><li>Rollen sind kombinierbar: Administrator, Planer, Freigeber, Techniker, Betrachter.</li>
<li><b>Globale Rollen</b> gelten für alle Standorte; wer eine hat, sieht alles.</li>
<li><b>Rechte pro Standort</b>: eine Rolle nur für einen Standort (mehrere Zeilen = mehrere Standorte). Wer <i>keine</i> globale Rolle hat, sieht nur diese Standorte – samt Locations, Geräten, Kabeln und Aufträgen.</li>
<li>Ein <b>Bereichs-Administrator</b> (Rolle Administrator an einem Standort) verwaltet Stammdaten und Benutzer seines Standorts, aber keine API-Zugänge, AD, Zertifikat, Katalog oder Import. Benutzer, die auch zu anderen Standorten gehören, sperrt oder löscht er nicht.</li>
<li>Bei AD-Benutzern kommen Rollen und Standort-Rechte aus den AD-Gruppen (Reiter „AD / LDAP“); sie werden bei jeder Anmeldung neu gesetzt.</li>
<li>„Abwesenheit“ trägt für einen Benutzer eine Abwesenheit mit Vertretung ein (Administratoren).</li>
<li>„Sitzungen beenden“ meldet den Benutzer überall ab.</li>
<li>Der letzte aktive Administrator kann nicht entfernt oder entzogen werden.</li></ul>`,
  '/admin#tokens': `<h2>API-Zugänge</h2>
<p>Tokens für Skripte und Integrationen (z. B. Checkmk, OpenPlan). Der Klartext wird <b>nur einmal</b> bei der Erstellung angezeigt.</p>
<ul><li><b>read</b>: nur lesen. <b>write</b>: lesen und schreiben (Import).</li></ul>`,
  '/admin#audit': `<h2>Audit-Log</h2>
<p>Wer hat wann was geändert: Anmeldungen, Stammdaten, Importe, Benutzer- und Token-Verwaltung.</p>`,

  '/handbuch': `<h2>Handbuch</h2><p>Das Handbuch beschreibt alle Funktionen ausführlich. Über das Inhaltsverzeichnis springst du zu den Abschnitten.</p>`,
}

const DEFAULT = '<h2>Hilfe</h2><p>Für diese Seite gibt es keinen eigenen Hilfetext. Das Handbuch erklärt alle Funktionen.</p>'

export function getHelp(path, ctx = '') {
  const base = path.startsWith('/devices/') ? '/devices' : path.startsWith('/workorders/') ? '/workorders' : path === '/patchlist' ? '/workorders' : path
  const keys = [ctx && `${base}#${ctx}`, base].filter(Boolean)
  if (lang.value === 'en') {
    for (const k of keys) if (T_EN[k]) return T_EN[k]
    for (const k of keys) if (T[k]) return T[k]
    return DEFAULT_EN
  }
  for (const k of keys) if (T[k]) return T[k]
  return DEFAULT
}
