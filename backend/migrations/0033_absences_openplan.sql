-- Abwesenheiten aus OpenPlan: übernommene Einträge (source = 'openplan', external_id = ID in OpenPlan) werden beim Abgleich ersetzt
-- und sind in Portwerk nur lesbar. Sie haben keine eigene Vertretung – es gilt die Standard-Vertretung des Benutzers.
ALTER TABLE user_absences ADD COLUMN source TEXT NOT NULL DEFAULT '';
ALTER TABLE user_absences ADD COLUMN external_id TEXT NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN default_deputy_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
