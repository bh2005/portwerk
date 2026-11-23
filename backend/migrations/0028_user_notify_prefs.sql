-- Persönliche Benachrichtigungen je Benutzer (JSON, z. B. {"confirm_suggest": false}); leer/fehlender Schlüssel = an
ALTER TABLE users ADD COLUMN notify_prefs TEXT NOT NULL DEFAULT '';
