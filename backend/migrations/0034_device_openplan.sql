-- Geräte aus OpenPlan: Verweis auf den Geräte-Vorgang im OpenPlan-Projekt („<Projekt-ID>:<Vorgang-ID>“), leer = nicht übernommen.
-- Damit erkennt ein erneuter Abruf bereits übernommene Geräte.
ALTER TABLE devices ADD COLUMN openplan_ref TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_devices_openplan_ref ON devices(openplan_ref);
