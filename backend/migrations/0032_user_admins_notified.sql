-- Konten ohne Rechte: Zeitpunkt, zu dem die globalen Administratoren per Mail informiert wurden (leer = noch nicht / nicht möglich).
ALTER TABLE users ADD COLUMN admins_notified_at REAL;
