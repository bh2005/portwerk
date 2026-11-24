# Neue Benutzer und Freischaltung

Neue Benutzer haben in Portwerk zunächst **keine Rechte**. Melden sie sich an, sehen sie nur einen Hinweis, dass sie sich für Rechte an einen Administrator wenden müssen.
Das gilt vor allem für Konten, die beim ersten AD-Login automatisch angelegt werden.

## Was der neue Benutzer sieht

Nach der Anmeldung erscheint statt der Oberfläche eine Seite **„Noch keine Berechtigung“**:

> Sie sind als *Max Beispiel* (*mbeispiel*) angemeldet, haben in Portwerk aber noch keine Rechte.
> Bitte wenden Sie sich für die Vergabe von Rechten an einen **Administrator**. Nennen Sie dabei Ihren Benutzernamen und den Standort, für den Sie Zugriff brauchen.

Haben die **globalen Administratoren** eine Hinweis-Mail bekommen, steht auf der Seite zusätzlich: *„Die globalen Administratoren wurden per E-Mail über Ihre Anmeldung informiert.“*
Das erscheint nur, wenn die Mail tatsächlich versendet wurde (E-Mail unter Verwaltung → E-Mail eingerichtet, mindestens ein Administrator mit Adresse).

Mit **Erneut prüfen** fragt die Seite den Stand ab; **Abmelden** beendet die Sitzung. Nach der Freischaltung genügt eine neue Anmeldung.
Bis dahin sieht und ändert der Benutzer nichts: Bestand, Aufträge, Verwaltung und alle Programmierschnittstellen liefern leere Listen oder verweigern den Zugriff.

## Hinweis-Mail an die globalen Administratoren

Meldet sich ein Konto ohne Rechte zum ersten Mal an, bekommen **alle aktiven globalen Administratoren mit E-Mail-Adresse** eine Mail:

> **Betreff:** [Portwerk] Neuer Benutzer wartet auf Freischaltung: Max Beispiel
> Max Beispiel (mbeispiel, max@example.test) hat sich bei Portwerk angemeldet und hat noch keine Rechte. Der Benutzer sieht nur den Hinweis, sich für Rechte an einen Administrator zu wenden.
> Bitte unter Verwaltung → Benutzer eine Rolle oder Standort-Rechte vergeben. *(Link zu Portwerk)*

- **Nur einmal je Konto:** Weitere Anmeldungen lösen keine Mail aus. Ging der Versand schief (z. B. SMTP nicht erreichbar), wird bei einer späteren Anmeldung erneut versucht, frühestens nach einer Stunde.
- **Abwesenheit:** Ist ein Administrator abwesend, geht die Mail an seine Vertretung, sofern diese selbst globaler Administrator ist.
- **Abbestellen:** Globale Administratoren können die Mail im Profil unter *Benachrichtigungen* ausschalten („Ein neuer Benutzer ohne Rechte hat sich angemeldet“).
- **Voraussetzung:** Die E-Mail-Einstellungen (Verwaltung → E-Mail) sind aktiv. Ohne sie wird keine Mail verschickt und der Hinweis auf der Seite des Benutzers entfällt.

## Workflow für Administratoren

1. **Verwaltung → Benutzer**: Konten ohne Rechte tragen die Markierung **wartet auf Freischaltung**.
2. **Bearbeiten** am Konto: eine globale Rolle vergeben (nur globale Administratoren) oder Rechte für einen Standort (auch Standort-Administratoren für ihre Standorte).
3. Speichern. Die Sitzungen des Benutzers werden beendet; er meldet sich neu an und sieht die Oberfläche.

Beispiel: `mbeispiel` bittet um Zugriff auf das Werk `NR1`. Sie öffnen das Konto, wählen unter *Standort-Rechte* `NR1` mit der Rolle *Planer* und speichern.

## Einstellung für AD-Anmeldung

Verwaltung → **AD / LDAP** → *Rolle ohne passende Gruppe*:

| Wert | Wirkung für Benutzer ohne passende AD-Gruppe |
|---|---|
| **keine – Konto ohne Rechte, Hinweis zur Freischaltung** (Standard) | Das Konto wird angelegt, der Benutzer sieht den Hinweis; ein Administrator schaltet frei. |
| eine Rolle (z. B. *Betrachter*) | Das Konto bekommt diese Rolle sofort. |

Diese Einstellung betrifft **nur Konten ohne Rechte**. Konten, die über AD-Gruppen oder vom Administrator Rechte haben, behalten sie. Wer gar nicht angemeldet werden soll, wird über die **Pflichtgruppe**
(*Anmeldung nur für Mitglieder dieser Gruppe*) ausgeschlossen; das Konto entsteht dann gar nicht erst. Ist *Konto beim ersten Login automatisch anlegen* aus, kommt ein unbekannter Benutzer nicht über „Anmeldung abgelehnt“ hinaus.

> **Hinweis zu AD-Gruppen → Rollen:** Sobald Gruppen Rollen zugeordnet sind, gilt bei **jeder** Anmeldung das Verzeichnis. Fällt ein Benutzer aus allen Gruppen, hat sein Konto danach ebenfalls keine Rechte und zeigt den Hinweis.

## Konten ohne Rechte finden

```bash
curl -H "X-Auth-Token: $TOKEN" https://opp.example.test/api/users | jq '.[] | select((.roles|length)==0 and (.scopes|length)==0) | .username'
```

Das Audit-Log zeigt die Anlage als `user.create` mit dem Vermerk *keine Rechte – wartet auf Freischaltung*.
