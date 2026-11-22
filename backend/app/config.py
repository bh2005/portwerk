"""Konfiguration über Umgebungsvariablen (Präfix OPP_)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPP_", env_file=".env", extra="ignore")

    data_dir: str = "./data"            # SQLite-DB (opp.db) und Uploads; muss beschreibbar sein
    admin_username: str = "admin"       # Start-Admin: wird nur angelegt, solange es noch keinen Benutzer gibt
    admin_password: str = ""            # leer = Zufallspasswort im Log
    session_ttl_hours: int = 8
    min_password_len: int = 8
    static_dir: str = ""                # gebaute Oberfläche (leer = frontend/dist bzw. /app/static automatisch suchen)
    cors_origins: str = ""              # kommagetrennt, nur für die Entwicklung (Vite-Dev-Server)
    backup_background: bool = True      # tägliche automatische Sicherung im Hintergrund (in Tests aus)


settings = Settings()
