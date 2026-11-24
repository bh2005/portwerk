# Anbindung an OpenPlan

Portwerk kann seine **Patchaufträge** als Vorgänge in einen OpenPlan-Projektplan hängen. Status und Fortschritt gleichen sich automatisch ab,
und aus einer Projektvorlage lässt sich ein ganzes **Einbauprojekt** (Patchfelder, Verkabelung, Messung, Abnahme) anlegen. Standardmäßig ist die Anbindung **aus**.

## Einrichten
1. In OpenPlan ein Dienstkonto mit API-Token anlegen (Umfang `write`, Rolle Bearbeiter) und es in den Projekten als Mitglied (Bearbeiter) eintragen.
2. In Portwerk: Verwaltung → **OpenPlan**: Adresse, Token, „Verbindung testen“, aktivieren. Optional CA-Kette für `https://`.
   Erreicht Portwerk OpenPlan unter einer anderen Adresse als die Benutzer (z. B. im Docker-Netz `http://openplan:8080`), zusätzlich die
   **OpenPlan-Adresse für Links** eintragen – sonst zeigen Links in Portwerk auf die interne Adresse.

   Voraussetzung auf OpenPlan-Seite: **Version 0.14.0** oder neuer (Projektart „Einbau Patchfelder / Verkabelung“, Referenzsystem `portwerk`).
3. Optional (Rückrichtung): In OpenPlan einen Webhook auf `<Adresse dieser Anwendung>/api/integrations/openplan/webhook` (Ereignis `task.status`) anlegen und das Geheimnis eintragen.
4. Optional (Abwesenheiten, ab OpenPlan **0.15.0**): In OpenPlan beim API-Zugang die Freigabe **„Abwesenheiten“** setzen (Verwaltung → API-Zugänge),
   in Portwerk „Abwesenheiten übernehmen“ einschalten und „jetzt abgleichen“.

## Benutzung
- **Patchauftrag → Aufgabe:** Im Auftrag „Mit OpenPlan verbinden …“: neue Aufgabe anlegen (unter dem Abschnitt „Patchaufträge (aus Portwerk)“) oder eine vorhandene verknüpfen.
  In OpenPlan steht die Referenz `portwerk: PA-…` mit Link zurück.
- **Mehrere Aufträge:** In der Auftragsliste ankreuzen → „In OpenPlan …“: Vorgänge in einem bestehenden Projekt anlegen oder ein **neues Projekt aus der Vorlage** erzeugen.
- **Abgleich:** Jede Statusänderung und jedes Abhaken meldet Status/Fortschritt an die Aufgabe (Entwurf bis freigegeben = offen; in Ausführung = Prozent erledigter Positionen, höchstens 99;
  bestätigt = erledigt; abgelehnt = blockiert). Ein Ausfall von OpenPlan stört den Auftrag nie – „Jetzt abgleichen“ holt es nach.
- **Rückrichtung:** Ändert jemand den Status der Aufgabe in OpenPlan, zeigt der Auftrag den neuen Status (Webhook).
- **Abwesenheiten:** Portwerk holt stündlich die persönlichen Abwesenheiten aller OpenPlan-Benutzer für ein Jahr im Voraus (`GET /api/absences`).
  Die Zuordnung läuft über den Benutzernamen (Groß-/Kleinschreibung egal), sonst über eine eindeutige E-Mail-Adresse. Benutzer ohne Gegenstück zeigt die Verwaltung an.
  Übernommene Einträge ersetzen bei jedem Abgleich die vorigen und sind in Portwerk nur lesbar. Für sie gilt die **Standard-Vertretung** aus dem Profil, denn OpenPlan kennt keine Vertretung.
  Selbst eingetragene Abwesenheiten bleiben unberührt. Schlägt der Abruf fehl, bleibt der alte Stand; Ausschalten entfernt die übernommenen Einträge.

## Technik
API-Aufrufe und Statuszuordnung: `backend/app/openplan.py`, Routen `backend/app/routers/openplan.py`, Tests `backend/tests/test_openplan.py` (gegen eine simulierte OpenPlan-API).
Der Vertrag auf OpenPlan-Seite steht in dessen `docs/integration-api.md` (Abschnitt 7: Abwesenheiten). Abgleich der Abwesenheiten: `openplan.sync_absences`, Tests `backend/tests/test_openplan_absences.py`.
