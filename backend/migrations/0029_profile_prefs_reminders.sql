-- Persönliche Bedienung (JSON: Standard-Standort, Startseite) und Erinnerung vor Ablauf einer Reservierung
ALTER TABLE users ADD COLUMN ui_prefs TEXT NOT NULL DEFAULT '';
ALTER TABLE port_reservations ADD COLUMN reminded_at REAL;            -- Erinnerung verschickt (wird bei Fristverlängerung zurückgesetzt)
