-- Sonderbereiche (WAN, Telefonie): nur für ausdrücklich zugelassene Benutzer und API-Zugänge sichtbar (globale Admins sehen alles)
ALTER TABLE users ADD COLUMN areas TEXT NOT NULL DEFAULT '';        -- kommagetrennt: wan,telephony
ALTER TABLE api_tokens ADD COLUMN areas TEXT NOT NULL DEFAULT '';
