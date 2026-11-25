/** Übersetzungen der Server-Meldungen (Text wie im Backend; Platzhalter aus f-Strings als %s → {1}, {2} …).
 *  Unbekannte Meldungen bleiben deutsch – die Liste wächst mit jeder Etappe der Übersetzung. */
export const enApi = [
  // Allgemein und Rechte
  ['Fehler', 'Error'],
  ['Nicht gefunden', 'Not found'],
  ['Nicht angemeldet', 'Not logged in'],
  ['Sitzung abgelaufen', 'Session expired'],
  ['Sitzung nicht mehr gültig', 'Session no longer valid'],
  ['Ungültiger Token', 'Invalid token'],
  ['Ungültiger API-Zugang', 'Invalid API token'],
  ['Ungültiger oder abgelaufener API-Zugang', 'Invalid or expired API token'],
  ['Keine Berechtigung für diesen Standort', 'No permission for this site'],
  ['Keine Berechtigung für diese Aktion', 'No permission for this action'],
  ['Nur für Administratoren', 'Administrators only'],
  ['Nur für angemeldete Benutzer', 'Logged-in users only'],
  ['Nur mit globaler Berechtigung', 'Requires a global permission'],
  ['Nur für Administratoren oder API-Zugänge mit Umfang „write“', 'Only for administrators or API tokens with scope “write”'],
  ['Nur für Administratoren, Bereichs-Administratoren oder API-Zugänge mit Umfang „write“', 'Only for administrators, site administrators or API tokens with scope “write”'],
  ['Fehlende Rolle (erforderlich: %s)', 'Missing role (required: {1})'],
  ['Standort nicht gefunden', 'Site not found'],
  ['Standort %s nicht gefunden', 'Site {1} not found'],
  ['Benutzer nicht gefunden', 'User not found'],
  ['API-Zugang nicht gefunden', 'API token not found'],
  ['%s: Datum im Format JJJJ-MM-TT erwartet', '{1}: date expected as YYYY-MM-DD'],
  // Anmeldung und Profil
  ['Anmeldung fehlgeschlagen', 'Login failed'],
  ['Ungültige Anmeldedaten', 'Invalid credentials'],
  ['Für dieses Konto gibt es noch keinen Zugang – bitte einen Administrator fragen', 'This account has no access yet – please ask an administrator'],
  ['Aktuelles Passwort falsch', 'Current password is wrong'],
  ['Passwort muss mindestens %s Zeichen haben', 'Password must have at least {1} characters'],
  ['Das Passwort dieses Kontos wird im Verzeichnisdienst geändert', 'The password of this account is changed in the directory service'],
  ['Verzeichnisdienst-Benutzer haben kein lokales Passwort', 'Directory users have no local password'],
  ['Startseite unbekannt', 'Unknown start page'],
  ['Sprache unbekannt', 'Unknown language'],
  // Benutzerverwaltung
  ['Benutzername existiert bereits', 'Username already exists'],
  ['Benutzername: 1–64 Zeichen (Buchstaben, Ziffern, . _ - @)', 'Username: 1–64 characters (letters, digits, . _ - @)'],
  ['Das eigene Konto kann nicht gelöscht werden', 'You cannot delete your own account'],
  ['Der letzte aktive Administrator kann nicht geändert werden', 'The last active administrator cannot be changed'],
  ['Mindestens eine Rolle ist erforderlich', 'At least one role is required'],
  ['Mindestens eine globale Rolle oder eine Berechtigung für einen Standort ist erforderlich', 'At least one global role or a permission for a site is required'],
  ['Globale Rollen vergeben nur globale Administratoren – bitte Rechte für einen Standort wählen', 'Only global administrators assign global roles – please choose permissions for a site'],
  ['Globale Rollen ändern nur globale Administratoren', 'Only global administrators change global roles'],
  ['Rechte dürfen nur für Standorte vergeben werden, für die du Administrator bist', 'You can only grant permissions for sites you administer'],
  ['Dieser Benutzer gehört auch zu anderen Bereichen – nur globale Administratoren dürfen das', 'This user also belongs to other areas – only global administrators may do that'],
  ['Dieser Benutzer gehört auch zu anderen Bereichen – nur globale Administratoren dürfen ihn löschen', 'This user also belongs to other areas – only global administrators may delete them'],
  ['Dieser Benutzer gehört auch zu anderen Bereichen – Sperren nur durch globale Administratoren', 'This user also belongs to other areas – only global administrators may lock them'],
  ['Unbekannte Rolle: %s (erlaubt: %s)', 'Unknown role: {1} (allowed: {2})'],
  ['Unbekannte Rolle(n): %s (erlaubt: %s)', 'Unknown role(s): {1} (allowed: {2})'],
  ["Umfang muss 'read' oder 'write' sein", "Scope must be 'read' or 'write'"],
  // Abwesenheit und Vertretung
  ['Zeitraum: Datum als JJJJ-MM-TT', 'Period: date as YYYY-MM-DD'],
  ['Das Ende liegt vor dem Beginn', 'The end is before the start'],
  ['Der Zeitraum liegt in der Vergangenheit', 'The period is in the past'],
  ['Man kann sich nicht selbst vertreten', 'You cannot be your own deputy'],
  ['Vertretung nicht gefunden', 'Deputy not found'],
  ['Abwesenheit nicht gefunden', 'Absence not found'],
  ['Diese Abwesenheit kommt aus %s – bitte dort ändern oder löschen', 'This absence comes from {1} – please change or delete it there'],
  // zuletzt: allgemeine Muster (spezifischere stehen oben)
  ['%s nicht gefunden', '{1} not found'],
]

const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const exact = new Map()
const patterns = []
for (const [de, en] of enApi) {
  if (/%[sdr]/.test(de)) patterns.push({ re: new RegExp('^' + esc(de).replace(/%[sdr]/g, '(.+?)') + '$', 's'), en })
  else exact.set(de, en)
}

/** Server-Meldung ins Englische übersetzen (unbekannte Texte bleiben unverändert). */
export function translateApi(msg) {
  const e = exact.get(msg)
  if (e) return e
  for (const { re, en } of patterns) {
    const m = re.exec(msg)
    if (m) return en.replace(/\{(\d+)\}/g, (_, i) => m[Number(i)] ?? '')
  }
  return msg
}
